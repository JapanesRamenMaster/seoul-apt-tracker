"""
좌표 없는 단지 대상 멀티 전략 재시도.
1) Nominatim 쿼리 변형 5가지
2) Overpass API (OSM 직접 이름 검색)
"""
import json
import os
import re
import sys
import time
import warnings

import requests

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "coords_cache.json",
)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "SeoulAptMap/1.0 personal-use"}

# 서울 구 목록 (범례/레전드 행 필터용)
VALID_GU = {
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구",
    "노원구","도봉구","동대문구","동작구","마포구","서대문구","서초구",
    "성동구","성북구","송파구","양천구","영등포구","용산구","은평구",
    "종로구","중구","중랑구",
}


def load_cache():
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def nominatim(query):
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "kr"},
            headers=HEADERS, timeout=10,
        )
        results = r.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    return None, None


def overpass_by_name(name, gu):
    """Overpass API: 구 안에서 이름으로 OSM 피처 직접 검색"""
    # 검색 키워드: 괄호·숫자·특수문자 제거 후 핵심어만
    keyword = re.sub(r"\([^)]*\)", "", name)
    keyword = re.sub(r"[,\s]+$", "", keyword)
    keyword = re.sub(r"\d+차단지.*$", "", keyword)
    keyword = keyword.strip()
    if len(keyword) < 3:
        return None, None

    query = f"""
[out:json][timeout:15];
area["name"="{gu}"]["boundary"="administrative"]->.gu;
(
  way["name"~"{keyword}"](area.gu);
  relation["name"~"{keyword}"](area.gu);
  node["name"~"{keyword}"]["place"](area.gu);
);
out center;
"""
    try:
        r = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=20)
        elements = r.json().get("elements", [])
        for el in elements:
            if "center" in el:
                return el["center"]["lat"], el["center"]["lon"]
            if "lat" in el and "lon" in el:
                return el["lat"], el["lon"]
    except Exception:
        pass
    return None, None


def query_variants(original_query):
    """원본 쿼리에서 구와 단지명 분리 후 변형 쿼리 목록 생성"""
    # "이름 구 서울" 패턴인지 "서울특별시 ... 도로명주소" 패턴인지 구분
    m = re.match(r"^(.+?)\s+([\w]+구)\s+서울$", original_query)
    if m:
        name, gu = m.group(1).strip(), m.group(2).strip()
        variants = []

        # 1) 쉼표 앞만
        if "," in name:
            variants.append((name.split(",")[0].strip() + f" {gu} 서울", gu))

        # 2) 괄호 제거
        no_paren = re.sub(r"\([^)]*\)", "", name).strip()
        # BL, 동범위 패턴도 제거
        no_paren = re.sub(r"\s*BL[\d\-]+", "", no_paren).strip()
        if no_paren != name:
            variants.append((no_paren + f" {gu} 서울", gu))

        # 3) 뒤 숫자/차/단지 제거
        stripped = re.sub(r"[\d]+차?단지?$", "", name).strip()
        stripped = re.sub(r"[\d]+지구$", "", stripped).strip()
        if stripped != name and len(stripped) >= 3:
            variants.append((stripped + f" {gu} 서울", gu))

        # 4) 아파트 추가
        variants.append((name + f" 아파트 {gu} 서울", gu))

        # 5) 괄호+숫자 둘 다 제거
        clean = no_paren
        clean = re.sub(r"[\d]+차?단지?$", "", clean).strip()
        if clean != name and clean != no_paren and len(clean) >= 3:
            variants.append((clean + f" {gu} 서울", gu))

        return variants, name, gu
    else:
        # 도로명/지번 주소 형태
        # "서울특별시 구 ... 한글건물명" → 끝 건물명 제거
        no_building = re.sub(r"\s+[가-힣\w]+아파트.*$", "", original_query).strip()
        no_building2 = re.sub(r"\s+[가-힣\w]{4,}$", "", original_query).strip()

        # 구 추출 시도
        gu_match = re.search(r"([\w]+구)", original_query)
        gu = gu_match.group(1) if gu_match else None

        variants = []
        if no_building != original_query:
            variants.append((no_building, gu))
        if no_building2 != original_query and no_building2 != no_building:
            variants.append((no_building2, gu))
        return variants, None, gu


def retry_all():
    cache = load_cache()

    # 실패 목록 (유효한 구 이름 있는 것만)
    failed = []
    for q, v in cache.items():
        if v[0] is not None:
            continue
        # 범례 행 제외
        gu_in_q = re.search(r"([\w]+구)", q)
        if not gu_in_q or gu_in_q.group(1) not in VALID_GU:
            continue
        failed.append(q)

    print(f"재시도 대상: {len(failed)}개")
    recovered = 0

    for idx, orig_q in enumerate(failed):
        variants, name, gu = query_variants(orig_q)
        found = False

        # --- Nominatim 변형 시도 ---
        for vq, _ in variants:
            if vq in cache and cache[vq][0] is not None:
                cache[orig_q] = cache[vq]
                print(f"  [{idx+1}] ✓ 변형성공: {orig_q[:30]} → {vq[:30]}")
                found = True
                recovered += 1
                break
            lat, lon = nominatim(vq)
            time.sleep(1.1)
            if lat:
                cache[vq] = [lat, lon]
                cache[orig_q] = [lat, lon]
                print(f"  [{idx+1}] ✓ Nominatim변형: {orig_q[:30]} → {vq[:30]}")
                found = True
                recovered += 1
                break
            else:
                cache[vq] = [None, None]

        # --- Overpass 시도 ---
        if not found and name and gu:
            print(f"  [{idx+1}] Overpass 시도: {name} / {gu}")
            lat, lon = overpass_by_name(name, gu)
            time.sleep(1.0)
            if lat:
                cache[orig_q] = [lat, lon]
                print(f"  [{idx+1}] ✓ Overpass: {orig_q[:40]}")
                found = True
                recovered += 1
            else:
                print(f"  [{idx+1}] ✗ 실패: {orig_q[:40]}")

        if (idx + 1) % 10 == 0:
            save_cache(cache)

    save_cache(cache)
    print(f"\n완료. 추가 확보: {recovered}/{len(failed)}개")
    return recovered


if __name__ == "__main__":
    retry_all()
