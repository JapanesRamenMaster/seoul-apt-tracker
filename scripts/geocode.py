"""
Nominatim(OpenStreetMap) 기반 geocoding.
단지정보 탭의 도로명주소 → 위경도 변환, data/coords_cache.json에 캐시.
"""
import json
import os
import sys
import time
import warnings

import requests

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHEETS_ID = "1MXsCwDJcJ5eY2Ll2N3miyUfSelw3GOcwIomj0MhuaAo"
CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "coords_cache.json")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "SeoulAptMap/1.0 personal-use"}


def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def nominatim_query(query: str):
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "kr"}
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"  [오류] {query}: {e}")
    return None, None


def geocode_all(force: bool = False) -> dict:
    from scripts.update_sheets import get_client

    cache = load_cache()

    gc = get_client()
    sh = gc.open_by_key(SHEETS_ID)

    # 단지정보: 단지명 → 도로명주소, kaptCode
    ws_info = sh.worksheet("단지정보")
    info_rows = ws_info.get_all_values()
    addr_by_name: dict[str, dict] = {}
    for r in info_rows[1:]:
        name, gu, kapt, units, built, addr, link = (r + [""] * 7)[:7]
        addr_by_name[name.strip()] = {"addr": addr.strip(), "kapt": kapt, "gu": gu}

    # 내 예산 범위: 데이터 행
    ws_budget = sh.worksheet("내 예산 범위")
    budget_rows = ws_budget.get_all_values()
    data_rows = [r for r in budget_rows[4:] if r[1].strip() and r[2].strip().endswith("구")]

    complexes = []
    need_geocode = []

    for r in data_rows:
        name = r[1].strip()
        gu = r[2].strip()
        area = r[3].strip()
        current_price = r[4].strip()
        proj_price = r[5].strip()
        period_change = r[6].strip()
        budget_diff = r[7].strip()
        units = r[8].strip()
        built = r[9].strip()
        cagr = r[12].strip()
        kapt_link = r[14].strip()

        info = addr_by_name.get(name, {})
        addr = info.get("addr", "")
        kapt = info.get("kapt", "")

        # geocoding 쿼리 결정
        if addr and addr != "-":
            geo_query = addr
        else:
            geo_query = f"{name} {gu} 서울"

        entry = {
            "name": name,
            "gu": gu,
            "area": area,
            "current_price": current_price,
            "proj_price": proj_price,
            "period_change": period_change,
            "budget_diff": budget_diff,
            "units": units,
            "built": built,
            "cagr": cagr,
            "kapt_link": kapt_link,
            "kapt": kapt,
            "geo_query": geo_query,
            "lat": None,
            "lon": None,
        }
        complexes.append(entry)

        if force or geo_query not in cache:
            need_geocode.append((len(complexes) - 1, geo_query))

    print(f"총 {len(complexes)}개 단지, 신규 geocoding 필요: {len(need_geocode)}개")

    for idx, (ci, query) in enumerate(need_geocode):
        print(f"  [{idx+1}/{len(need_geocode)}] {complexes[ci]['name']} — {query}")
        lat, lon = nominatim_query(query)
        cache[query] = [lat, lon]
        if (idx + 1) % 20 == 0:
            save_cache(cache)
        time.sleep(1.1)

    save_cache(cache)

    # 캐시에서 좌표 채우기
    found = 0
    for c in complexes:
        coords = cache.get(c["geo_query"], [None, None])
        c["lat"] = coords[0]
        c["lon"] = coords[1]
        if c["lat"]:
            found += 1

    print(f"좌표 확보: {found}/{len(complexes)}개")
    return {"complexes": complexes}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="캐시 무시하고 재geocoding")
    args = parser.parse_args()
    geocode_all(force=args.force)
    print("완료. data/coords_cache.json 저장됨.")
