"""
2차 재시도: 더 공격적인 키워드 단순화 + 서울 전체 Overpass 검색.
"""
import json, os, re, sys, time, warnings
import requests

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "coords_cache.json",
)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "SeoulAptMap/1.0 personal-use"}

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

def overpass_name(keyword, gu=None):
    """구 또는 서울 전역에서 이름으로 검색"""
    if len(keyword) < 3:
        return None, None
    if gu:
        area_filter = f'area["name"="{gu}"]["boundary"="administrative"]->.a;'
        in_clause = "(area.a)"
    else:
        area_filter = 'area["name"="서울특별시"]["boundary"="administrative"]->.a;'
        in_clause = "(area.a)"

    query = f"""
[out:json][timeout:15];
{area_filter}
(
  way["name"~"^{keyword}"]{in_clause};
  relation["name"~"^{keyword}"]{in_clause};
);
out center 3;
"""
    try:
        r = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=20)
        els = r.json().get("elements", [])
        for el in els:
            if "center" in el:
                return el["center"]["lat"], el["center"]["lon"]
            if "lat" in el:
                return el["lat"], el["lon"]
    except Exception:
        pass
    return None, None

def simplify_name(name):
    """이름에서 핵심어만 추출 — 여러 단계 반환"""
    variants = []
    n = name

    # 1. 쉼표 앞
    if "," in n:
        variants.append(n.split(",")[0].strip())

    # 2. 괄호 제거
    no_paren = re.sub(r"\([^)]*\)", "", n).strip()
    no_paren = re.sub(r"\s*BL[\d\-]+", "", no_paren).strip()
    if no_paren != n:
        variants.append(no_paren)

    # 3. 뒤 숫자(단독)/차/단지/지구/BL 제거
    stripped = re.sub(r"[\d]+차?단지?$", "", no_paren).strip()
    stripped = re.sub(r"[\d]+지구$", "", stripped).strip()
    stripped = re.sub(r"\s*\d+$", "", stripped).strip()  # 뒤 단독 숫자
    if stripped and stripped != no_paren:
        variants.append(stripped)

    # 4. 앞 동명 제거 (예: "성내동삼성" → "삼성", "도화동현대" → "현대")
    no_dong = re.sub(r"^[가-힣]{2,3}동", "", stripped or no_paren).strip()
    if no_dong and no_dong != (stripped or no_paren) and len(no_dong) >= 3:
        variants.append(no_dong)

    # 5. 첫 4글자 (마지막 수단)
    core = (stripped or no_paren or n)
    if len(core) > 5:
        variants.append(core[:4])

    # 중복 제거, 원본 제외, 길이 3 이상만
    seen = {n}
    result = []
    for v in variants:
        if v not in seen and len(v) >= 3:
            seen.add(v)
            result.append(v)
    return result

def retry2():
    cache = load_cache()

    still_failed = []
    for q, v in cache.items():
        if v[0] is not None:
            continue
        gu_m = re.search(r"([\w]+구)", q)
        if not gu_m or gu_m.group(1) not in VALID_GU:
            continue
        still_failed.append(q)

    print(f"2차 재시도 대상: {len(still_failed)}개")
    recovered = 0

    for idx, orig_q in enumerate(still_failed):
        # 원본 쿼리에서 단지명과 구 분리
        m = re.match(r"^(.+?)\s+([\w]+구)\s+서울$", orig_q)
        is_address = not m

        if m:
            name, gu = m.group(1).strip(), m.group(2).strip()
        else:
            gu_m2 = re.search(r"([\w]+구)", orig_q)
            gu = gu_m2.group(1) if gu_m2 else None
            name = None

        found = False

        # ── 이름 기반 쿼리 ──
        if name:
            variants = simplify_name(name)
            print(f"  [{idx+1}] {name[:20]} → 변형후보: {[v[:15] for v in variants]}")

            for v in variants:
                # Nominatim
                for q_str in [f"{v} {gu} 서울", f"{v} {gu}", f"{v} 아파트 {gu} 서울"]:
                    if cache.get(q_str, [None])[0]:
                        cache[orig_q] = cache[q_str]
                        found = True; break
                    lat, lon = nominatim(q_str)
                    time.sleep(1.1)
                    cache[q_str] = [lat, lon]
                    if lat:
                        cache[orig_q] = [lat, lon]
                        print(f"    ✓ Nominatim: {q_str[:40]}")
                        found = True; break
                if found: break

                if not found:
                    # Overpass — 구 안
                    lat, lon = overpass_name(v, gu)
                    time.sleep(1.0)
                    if lat:
                        cache[orig_q] = [lat, lon]
                        print(f"    ✓ Overpass(구): {v}")
                        found = True; break

                    # Overpass — 서울 전역 (구 안에 없는 경우 대비)
                    lat, lon = overpass_name(v, None)
                    time.sleep(1.0)
                    if lat:
                        cache[orig_q] = [lat, lon]
                        print(f"    ✓ Overpass(서울): {v}")
                        found = True; break

        # ── 주소 기반 쿼리 ──
        else:
            # 도로명주소에서 번지 앞까지만 / 마지막 단어 제거 등
            addr_variants = []
            # 번지 뒤 잘라내기
            clean = re.sub(r"\s+[가-힣\w]{3,}아파트.*$", "", orig_q).strip()
            addr_variants.append(clean)
            # 번지 포함 마지막 토큰 제거
            parts = orig_q.split()
            if len(parts) > 3:
                addr_variants.append(" ".join(parts[:-1]))
            # 도로명만 (번지 없이)
            no_num = re.sub(r"\s+\d[\d\-]*$", "", clean).strip()
            addr_variants.append(no_num)

            print(f"  [{idx+1}] 주소변형: {orig_q[:40]}")
            for aq in addr_variants:
                if aq == orig_q or not aq:
                    continue
                if cache.get(aq, [None])[0]:
                    cache[orig_q] = cache[aq]
                    found = True; break
                lat, lon = nominatim(aq)
                time.sleep(1.1)
                cache[aq] = [lat, lon]
                if lat:
                    cache[orig_q] = [lat, lon]
                    print(f"    ✓ 주소변형: {aq[:40]}")
                    found = True; break

        if found:
            recovered += 1
        else:
            print(f"  [{idx+1}] ✗ 최종실패: {orig_q[:50]}")

        if (idx + 1) % 10 == 0:
            save_cache(cache)

    save_cache(cache)
    print(f"\n2차 완료. 추가 확보: {recovered}/{len(still_failed)}개")
    return recovered


if __name__ == "__main__":
    retry2()
