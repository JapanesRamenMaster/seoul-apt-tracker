import time
import requests
import xml.etree.ElementTree as ET
import pandas as pd

API_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"

SEOUL_DISTRICTS: dict[str, str] = {
    "강남구": "11680", "강동구": "11740", "강북구": "11305",
    "강서구": "11500", "관악구": "11620", "광진구": "11215",
    "구로구": "11530", "금천구": "11545", "노원구": "11350",
    "도봉구": "11320", "동대문구": "11230", "동작구": "11590",
    "마포구": "11440", "서대문구": "11410", "서초구": "11650",
    "성동구": "11200", "성북구": "11290", "송파구": "11710",
    "양천구": "11470", "영등포구": "11560", "용산구": "11170",
    "은평구": "11380", "종로구": "11110", "중구": "11140",
    "중랑구": "11260",
}

_CODE_TO_DISTRICT = {v: k for k, v in SEOUL_DISTRICTS.items()}

AREA_BINS = [0.0, 59.99, 84.99, 114.99, float("inf")]
AREA_LABELS = ["59㎡이하", "60~84㎡", "85~114㎡", "115㎡이상"]


def area_bucket(sqm: float) -> str:
    for label, upper in zip(AREA_LABELS, AREA_BINS[1:]):
        if sqm <= upper:
            return label
    return AREA_LABELS[-1]


_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def fetch_district_month(district_code: str, yyyymm: str, api_key: str) -> pd.DataFrame:
    params = {
        "serviceKey": api_key,
        "LAWD_CD": district_code,
        "DEAL_YMD": yyyymm,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    resp = requests.get(API_BASE, params=params, headers=_REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return _parse_xml(resp.text, district_code, yyyymm)


def _parse_xml(xml_text: str, district_code: str, yyyymm: str) -> pd.DataFrame:
    """API v2 응답 파싱 (영문 필드명: aptNm, dealAmount, excluUseAr, umdNm, floor)"""
    root = ET.fromstring(xml_text)
    rows = []
    district = _CODE_TO_DISTRICT.get(district_code, "")
    for item in root.findall(".//item"):
        def t(tag: str) -> str:
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""
        price_raw = t("dealAmount").replace(",", "").strip()
        sqm_raw = t("excluUseAr").strip()
        if not price_raw or not sqm_raw:
            continue
        sqm = float(sqm_raw)
        rows.append({
            "거래년월": yyyymm,
            "구": district,
            "법정동": t("umdNm"),
            "단지명": t("aptNm"),
            "전용면적": sqm,
            "면적구간": area_bucket(sqm),
            "거래금액": int(price_raw),
            "층": t("floor"),
        })
    return pd.DataFrame(rows, columns=["거래년월", "구", "법정동", "단지명", "전용면적", "면적구간", "거래금액", "층"])


def fetch_all_districts(yyyymm: str, api_key: str, delay: float = 0.5) -> pd.DataFrame:
    """서울 25개 구 전체 실거래 수집. delay로 API 호출 간격 조절."""
    frames = []
    for district, code in SEOUL_DISTRICTS.items():
        df = fetch_district_month(code, yyyymm, api_key)
        frames.append(df)
        time.sleep(delay)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
