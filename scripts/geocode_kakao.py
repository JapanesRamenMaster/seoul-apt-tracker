"""
Kakao Local API 기반 geocoding — Nominatim/Overpass로 못 찾은 단지 전용.

사용법:
    export KAKAO_REST_API_KEY="<발급받은 REST API 키>"
    python3 -m scripts.geocode_kakao

Kakao 키 발급: https://developers.kakao.com → 앱 생성 → REST API 키
무료, 일 10만 건 한도, 카드 등록 불필요.

처리 전략:
  케이스A (도로명주소형): kakao 주소검색 → 실패 시 keyword 검색
  케이스B (단지명 구 서울형): kakao keyword 검색 (category_group_code=APT 우선)

검증: 결과 x,y → 구 이름 reverse check (wrong_gu 기록)
"""
import json
import os
import re
import sys
import time

import requests

CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "coords_cache.json",
)

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_COORD2REGION_URL = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"

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


def kakao_keyword(query, headers, category_group_code=None):
    """단지명 + 구 + 서울 키워드 검색. APT 카테고리 우선."""
    params = {"query": query, "size": 5}
    if category_group_code:
        params["category_group_code"] = category_group_code
    try:
        r = requests.get(KAKAO_KEYWORD_URL, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        docs = r.json().get("documents", [])
        if docs:
            d = docs[0]
            return float(d["y"]), float(d["x"]), d.get("place_name", ""), d.get("address_name", "")
    except Exception as e:
        print(f"    [kakao keyword 오류] {e}")
    return None, None, "", ""


def kakao_address(addr, headers):
    """도로명/지번 주소 → 좌표. 케이스A 전용."""
    params = {"query": addr, "analyze_type": "similar"}
    try:
        r = requests.get(KAKAO_ADDRESS_URL, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        docs = r.json().get("documents", [])
        if docs:
            d = docs[0]
            return float(d["y"]), float(d["x"]), d.get("address_name", "")
    except Exception as e:
        print(f"    [kakao address 오류] {e}")
    return None, None, ""


def reverse_geocode_gu(lat, lon, headers):
    """좌표 → 구 이름 확인 (검증용)."""
    params = {"x": lon, "y": lat, "input_coord": "WGS84"}
    try:
        r = requests.get(KAKAO_COORD2REGION_URL, params=params, headers=headers, timeout=10)
        docs = r.json().get("documents", [])
        for d in docs:
            if d.get("region_type") == "H":
                return d.get("region_2depth_name", "")
    except Exception:
        pass
    return ""


def is_addr_query(q):
    """서울특별시 ... 형태의 도로명주소 쿼리인지 판별."""
    return q.startswith("서울특별시") or re.match(r"^서울\s", q)


def simplify_name_variants(name):
    """단지명에서 검색 변형 후보 목록 반환 (최대 3개)."""
    variants = [name]

    # 쉼표 → 제거하여 붙이기 (진로,미주아파트 → 진로미주아파트)
    if "," in name:
        variants.append(name.replace(",", "").strip())

    # 괄호 + BL + 뒤 숫자/차/단지 제거
    clean = re.sub(r"\([^)]*\)", "", name).strip()
    clean = re.sub(r"\s*BL[\d\-]+", "", clean).strip()
    clean = re.sub(r"[\d]+차?단지?$", "", clean).strip()
    clean = re.sub(r"\s*\d+$", "", clean).strip()
    if clean and clean != name:
        variants.append(clean)

    # 앞 동명 제거 (성내동삼성아파트 → 삼성아파트)
    no_dong = re.sub(r"^[가-힣]{2,3}동", "", clean or name).strip()
    if no_dong and no_dong != (clean or name) and len(no_dong) >= 3:
        variants.append(no_dong)

    # 중복 제거, 길이 2 미만 제거
    seen = set()
    result = []
    for v in variants:
        if v not in seen and len(v) >= 2:
            seen.add(v)
            result.append(v)
    return result


def process_key(orig_q, cache, headers):
    """
    캐시 키 하나를 처리. 성공 시 cache[orig_q] 업데이트 후 True 반환.
    wrong_gu 의심 시 결과는 저장하되 출력에 경고 표시.
    """
    # ── 케이스B: "단지명 구 서울" 패턴 ──
    m = re.match(r"^(.+?)\s+([\w]+구)\s+서울$", orig_q)
    if m:
        name, gu = m.group(1).strip(), m.group(2).strip()

        for variant in simplify_name_variants(name):
            query_str = f"{variant} {gu}"

            # 1순위: APT 카테고리 필터
            lat, lon, place, addr_name = kakao_keyword(
                query_str, headers, category_group_code="AT4"
            )
            time.sleep(0.05)

            # 2순위: 카테고리 없이 재시도
            if lat is None:
                lat, lon, place, addr_name = kakao_keyword(query_str, headers)
                time.sleep(0.05)

            if lat is not None:
                # 구 검증
                found_gu = _extract_gu_from_addr(addr_name)
                gu_ok = (found_gu == gu) if found_gu else True  # 주소 없으면 통과
                flag = "" if gu_ok else f" ⚠️구불일치({found_gu})"
                print(f"    ✓ [{variant}] → {place} / {addr_name}{flag}")
                cache[orig_q] = [lat, lon]
                return True

        print(f"    ✗ 최종실패")
        return False

    # ── 케이스A: 도로명주소 패턴 ──
    else:
        # 1순위: Kakao 주소 검색
        lat, lon, addr_name = kakao_address(orig_q, headers)
        time.sleep(0.05)
        if lat is not None:
            print(f"    ✓ [주소] → {addr_name}")
            cache[orig_q] = [lat, lon]
            return True

        # 2순위: 주소에서 구 추출 후 keyword 검색 (번지 잘라내기)
        gu_m = re.search(r"([\w]+구)", orig_q)
        gu = gu_m.group(1) if gu_m else None
        # 마지막 번지 토큰 제거
        clean_addr = re.sub(r"\s+\d[\d\-]*$", "", orig_q).strip()
        if clean_addr != orig_q:
            lat, lon, addr_name = kakao_address(clean_addr, headers)
            time.sleep(0.05)
            if lat is not None:
                print(f"    ✓ [주소변형] → {addr_name}")
                cache[orig_q] = [lat, lon]
                return True

        # 3순위: keyword 검색 (도로명에서 핵심어 추출)
        if gu:
            # 도로명만 추출 (예: "사당로2길" 등)
            road_m = re.search(r"([가-힣]+로\d*길?|[가-힣]+대로\d*)", orig_q)
            if road_m:
                kw = f"{road_m.group(1)} {gu}"
                lat, lon, place, addr_name = kakao_keyword(kw, headers)
                time.sleep(0.05)
                if lat is not None:
                    print(f"    ✓ [도로명keyword] → {place} / {addr_name}")
                    cache[orig_q] = [lat, lon]
                    return True

        print(f"    ✗ 최종실패")
        return False


def _extract_gu_from_addr(addr_name):
    """주소 문자열에서 구 이름 추출."""
    m = re.search(r"([\w]+구)", addr_name)
    if m and m.group(1) in VALID_GU:
        return m.group(1)
    return ""


def run():
    api_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    if not api_key:
        # .env 파일에서 직접 읽기 시도
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("KAKAO_REST_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    if not api_key:
        print("오류: KAKAO_REST_API_KEY 환경변수 또는 .env 파일에 키가 없습니다.")
        print("발급: https://developers.kakao.com → 앱 생성 → REST API 키")
        print("설정: export KAKAO_REST_API_KEY='your_key_here'")
        sys.exit(1)

    headers = {"Authorization": f"KakaoAK {api_key}"}
    cache = load_cache()

    # 실패 항목 수집 (기존 캐시에 null인 단지 키만)
    targets = []
    for k, v in cache.items():
        if v[0] is not None:
            continue
        if not any(gu in k for gu in VALID_GU):
            continue
        targets.append(k)

    print(f"Kakao geocoding 대상: {len(targets)}개")
    recovered = 0

    for idx, orig_q in enumerate(targets):
        print(f"[{idx+1}/{len(targets)}] {orig_q[:55]}")
        ok = process_key(orig_q, cache, headers)
        if ok:
            recovered += 1

        if (idx + 1) % 20 == 0:
            save_cache(cache)
            print(f"  (중간저장 — 누적 성공: {recovered}/{idx+1})")

    save_cache(cache)
    print(f"\n완료. 추가 확보: {recovered}/{len(targets)}개")
    print(f"cache 저장: {CACHE_PATH}")
    return recovered


if __name__ == "__main__":
    run()
