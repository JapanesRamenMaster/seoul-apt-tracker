# 서울 아파트 가격 추적 시스템 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서울 500세대 이상 아파트 실거래가를 매월 자동 수집하고, 5년 선형회귀 기반 다음달 프로젝션을 Google Sheets 3개 탭에 제공하는 시스템을 구축한다.

**Architecture:** Python 스크립트가 국토교통부 실거래가 API(data.go.kr)에서 서울 25개 구 월별 데이터를 가져와 500세대+ 단지로 필터링하고, gspread로 Google Sheets를 업데이트한다. GitHub Actions cron이 매월 1일 UTC 0시(한국 9시)에 자동 실행한다.

**Tech Stack:** Python 3.11+, requests, pandas, scipy(선형회귀), gspread, google-auth, python-dotenv, pytest

---

## File Map

| 파일 | 역할 |
|---|---|
| `scripts/complexes.py` | 서울시 공동주택현황 CSV 파싱 → 500세대+ 단지 dict 반환 |
| `scripts/fetch_transactions.py` | 국토교통부 실거래가 API 호출 → 거래 DataFrame |
| `scripts/compute_stats.py` | monthly_avg + projection 계산 |
| `scripts/update_sheets.py` | gspread로 Sheets 3탭 업데이트 |
| `scripts/run_monthly.py` | 월별 파이프라인 진입점 (Actions가 호출) |
| `scripts/backfill.py` | 5년치(60개월) 초기 적재 |
| `tests/test_fetch_transactions.py` | API 파싱 테스트 (mock) |
| `tests/test_compute_stats.py` | 집계·프로젝션 계산 테스트 |
| `.github/workflows/monthly.yml` | 매월 1일 자동 실행 워크플로우 |
| `data/seoul_complexes.csv` | 서울시 공동주택현황 (수동 1회 다운로드 후 커밋) |
| `requirements.txt` | 의존성 |
| `.env.example` | 환경변수 템플릿 |

---

## 사전 준비 (코드 작성 전 필요한 수동 작업)

### A. 국토교통부 API 키 발급
1. https://www.data.go.kr 접속 → 회원가입/로그인
2. "아파트매매 실거래가 자료" 검색 → 활용 신청
3. 즉시 발급된 `serviceKey` 복사 (URL 인코딩된 버전 사용)

### B. 서울시 공동주택현황 CSV 다운로드
1. https://data.seoul.go.kr 접속
2. "공동주택현황" 검색 → CSV 다운로드
3. `data/seoul_complexes.csv` 로 저장
4. 파일 열어서 단지명·자치구·세대수 컬럼명 확인 (스크립트에 맞게 조정 필요)

### C. Google 서비스 계정 생성
1. https://console.cloud.google.com → IAM → 서비스 계정 생성
2. Google Sheets API + Google Drive API 활성화
3. JSON 키 다운로드
4. Google Sheets 파일 열기 → 공유 → 서비스 계정 이메일에 편집자 권한 부여

---

## Task 1: 프로젝트 초기화

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `tests/__init__.py`
- Create: `scripts/__init__.py`

- [ ] **Step 1: requirements.txt 생성**

```
requests==2.31.0
pandas==2.2.2
scipy==1.13.0
gspread==6.1.2
google-auth==2.29.0
python-dotenv==1.0.1
pytest==8.2.0
pytest-mock==3.14.0
```

- [ ] **Step 2: .env.example 생성**

```
MOLIT_API_KEY=여기에_국토교통부_API_키
GOOGLE_SERVICE_ACCOUNT_JSON=서비스_계정_JSON_경로_또는_전체_JSON_문자열
SPREADSHEET_ID=Google_Sheets_URL에서_복사한_ID
```

- [ ] **Step 3: 빈 init 파일 생성**

```bash
mkdir -p scripts tests data
touch scripts/__init__.py tests/__init__.py
```

- [ ] **Step 4: 의존성 설치 확인**

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```
Expected: 에러 없이 설치 완료

- [ ] **Step 5: 커밋**

```bash
git init
git add requirements.txt .env.example scripts/__init__.py tests/__init__.py
git commit -m "chore: 프로젝트 초기화"
```

---

## Task 2: 단지 목록 모듈 (complexes.py)

서울시 공동주택현황 CSV를 파싱해 `{(단지명, 구): 세대수}` dict를 반환한다. 500세대 이상 단지 집합도 반환.

**Files:**
- Create: `scripts/complexes.py`
- Create: `tests/test_complexes.py`
- Requires: `data/seoul_complexes.csv` (사전 준비 B 완료 후)

- [ ] **Step 1: 테스트용 샘플 CSV 생성**

`tests/fixtures/sample_complexes.csv` 생성:
```
자치구,단지명,세대수
강남구,래미안대치팰리스,1608
강남구,은마아파트,4424
강남구,소규모단지,200
서초구,반포자이,3410
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_complexes.py`:
```python
import pytest
from pathlib import Path
from scripts.complexes import load_complexes, COMPLEX_500_SET

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_complexes.csv"


def test_load_complexes_returns_dict():
    result = load_complexes(FIXTURE_CSV)
    assert isinstance(result, dict)
    assert ("래미안대치팰리스", "강남구") in result
    assert result[("래미안대치팰리스", "강남구")] == 1608


def test_load_complexes_filters_500():
    result = load_complexes(FIXTURE_CSV)
    keys = set(result.keys())
    assert ("소규모단지", "강남구") not in keys  # 200세대 제외
    assert ("은마아파트", "강남구") in keys       # 4424세대 포함


def test_is_target_complex():
    from scripts.complexes import is_target
    load_complexes(FIXTURE_CSV)
    assert is_target("래미안대치팰리스", "강남구") is True
    assert is_target("소규모단지", "강남구") is False
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/test_complexes.py -v
```
Expected: FAIL (ImportError or AttributeError)

- [ ] **Step 4: complexes.py 구현**

`scripts/complexes.py`:
```python
from pathlib import Path
import pandas as pd

_COMPLEX_DICT: dict[tuple[str, str], int] = {}

DEFAULT_CSV = Path(__file__).parent.parent / "data" / "seoul_complexes.csv"


def load_complexes(csv_path: Path = DEFAULT_CSV) -> dict[tuple[str, str], int]:
    """CSV 로드 → {(단지명, 구): 세대수} dict (500세대 이상만)"""
    global _COMPLEX_DICT
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # 컬럼명이 다를 수 있어 유연하게 처리
    col_map = _detect_columns(df.columns.tolist())
    df = df.rename(columns=col_map)

    df["세대수"] = pd.to_numeric(df["세대수"], errors="coerce").fillna(0).astype(int)
    df = df[df["세대수"] >= 500]
    _COMPLEX_DICT = {
        (_normalize(row["단지명"]), row["자치구"]): row["세대수"]
        for _, row in df.iterrows()
    }
    return _COMPLEX_DICT


def is_target(apt_name: str, district: str) -> bool:
    return (_normalize(apt_name), district) in _COMPLEX_DICT


def _normalize(name: str) -> str:
    """공백·특수문자 정규화 (API 응답과 CSV 단지명 불일치 방지)"""
    return name.strip().replace(" ", "").replace("​", "")


def _detect_columns(cols: list[str]) -> dict[str, str]:
    """CSV 컬럼명 자동 감지 → 표준명 매핑"""
    mapping = {}
    for col in cols:
        if "단지" in col and "단지명" not in mapping.values():
            mapping[col] = "단지명"
        elif "구" in col and "자치구" not in mapping.values():
            mapping[col] = "자치구"
        elif "세대" in col and "세대수" not in mapping.values():
            mapping[col] = "세대수"
    return mapping
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_complexes.py -v
```
Expected: 3개 PASS

- [ ] **Step 6: 커밋**

```bash
git add scripts/complexes.py tests/test_complexes.py tests/fixtures/sample_complexes.csv
git commit -m "feat: 단지 목록 로더 (500세대+ 필터)"
```

---

## Task 3: 실거래가 API 클라이언트 (fetch_transactions.py)

국토교통부 API에서 지정 연월의 서울 전체 거래를 가져와 DataFrame으로 반환한다.

**Files:**
- Create: `scripts/fetch_transactions.py`
- Create: `tests/test_fetch_transactions.py`
- Create: `tests/fixtures/sample_api_response.xml`

**API 정보:**
- URL: `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`
- Method: GET
- 파라미터: `serviceKey`, `LAWD_CD`(법정동코드 5자리), `DEAL_YMD`(YYYYMM), `numOfRows`(최대 1000), `pageNo`

- [ ] **Step 1: 샘플 API 응답 XML 생성**

`tests/fixtures/sample_api_response.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
  <body>
    <items>
      <item>
        <거래금액>   285,000</거래금액>
        <건축년도>2002</건축년도>
        <년>2026</년>
        <법정동>대치동</법정동>
        <아파트>래미안대치팰리스</아파트>
        <전용면적>84.99</전용면적>
        <지번>316</지번>
        <층>12</층>
        <월>5</월>
        <일>15</일>
      </item>
      <item>
        <거래금액>   195,000</거래금액>
        <건축년도>1979</건축년도>
        <년>2026</년>
        <법정동>대치동</법정동>
        <아파트>은마아파트</아파트>
        <전용면적>76.79</전용면적>
        <지번>350</지번>
        <층>8</층>
        <월>5</월>
        <일>20</일>
      </item>
    </items>
    <numOfRows>1000</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>2</totalCount>
  </body>
</response>
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_fetch_transactions.py`:
```python
from pathlib import Path
from unittest.mock import patch, Mock
import pandas as pd
from scripts.fetch_transactions import fetch_district_month, area_bucket, SEOUL_DISTRICTS

FIXTURE_XML = (Path(__file__).parent / "fixtures" / "sample_api_response.xml").read_text()


def test_area_bucket():
    assert area_bucket(59.0) == "59㎡이하"
    assert area_bucket(59.99) == "59㎡이하"
    assert area_bucket(60.0) == "60~84㎡"
    assert area_bucket(84.99) == "60~84㎡"
    assert area_bucket(85.0) == "85~114㎡"
    assert area_bucket(115.0) == "115㎡이상"


def test_fetch_district_month_parses_xml(mocker):
    mock_resp = Mock()
    mock_resp.text = FIXTURE_XML
    mock_resp.raise_for_status = lambda: None
    mocker.patch("scripts.fetch_transactions.requests.get", return_value=mock_resp)

    df = fetch_district_month("11680", "202605", "test_key")

    assert len(df) == 2
    assert set(df.columns) >= {"거래년월", "구", "단지명", "전용면적", "면적구간", "거래금액"}
    assert df["거래년월"].iloc[0] == "202605"
    assert df["구"].iloc[0] == "강남구"
    assert df["거래금액"].iloc[0] == 285000
    assert df["면적구간"].iloc[0] == "60~84㎡"


def test_seoul_districts_count():
    assert len(SEOUL_DISTRICTS) == 25
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
pytest tests/test_fetch_transactions.py -v
```
Expected: FAIL

- [ ] **Step 4: fetch_transactions.py 구현**

`scripts/fetch_transactions.py`:
```python
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


def fetch_district_month(district_code: str, yyyymm: str, api_key: str) -> pd.DataFrame:
    params = {
        "serviceKey": api_key,
        "LAWD_CD": district_code,
        "DEAL_YMD": yyyymm,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    resp = requests.get(API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    return _parse_xml(resp.text, district_code, yyyymm)


def _parse_xml(xml_text: str, district_code: str, yyyymm: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    rows = []
    district = _CODE_TO_DISTRICT.get(district_code, "")
    for item in root.findall(".//item"):
        def t(tag: str) -> str:
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""
        price_raw = t("거래금액").replace(",", "").strip()
        sqm_raw = t("전용면적").strip()
        if not price_raw or not sqm_raw:
            continue
        sqm = float(sqm_raw)
        rows.append({
            "거래년월": yyyymm,
            "구": district,
            "법정동": t("법정동"),
            "단지명": t("아파트"),
            "전용면적": sqm,
            "면적구간": area_bucket(sqm),
            "거래금액": int(price_raw),
            "층": t("층"),
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
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/test_fetch_transactions.py -v
```
Expected: 3개 PASS

- [ ] **Step 6: 커밋**

```bash
git add scripts/fetch_transactions.py tests/test_fetch_transactions.py tests/fixtures/sample_api_response.xml
git commit -m "feat: 국토교통부 실거래가 API 클라이언트"
```

---

## Task 4: 집계·프로젝션 계산 (compute_stats.py)

raw DataFrame → monthly_avg DataFrame + projection DataFrame 계산.

**Files:**
- Create: `scripts/compute_stats.py`
- Create: `tests/test_compute_stats.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_compute_stats.py`:
```python
import pandas as pd
import numpy as np
from scripts.compute_stats import compute_monthly_avg, compute_projection

RAW = pd.DataFrame([
    # 래미안대치팰리스 84㎡ — 6개월치
    {"거래년월": "202101", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 230000},
    {"거래년월": "202101", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 240000},
    {"거래년월": "202201", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 250000},
    {"거래년월": "202301", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 260000},
    {"거래년월": "202401", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 270000},
    {"거래년월": "202501", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 280000},
])


def test_compute_monthly_avg_groups_correctly():
    avg = compute_monthly_avg(RAW)
    # 202101 두 건 → 평균 235000
    row = avg[(avg["단지명"] == "래미안대치팰리스") & (avg["거래년월"] == "202101")]
    assert len(row) == 1
    assert row["평균거래금액"].iloc[0] == 235000


def test_compute_monthly_avg_columns():
    avg = compute_monthly_avg(RAW)
    assert set(avg.columns) >= {"거래년월", "구", "단지명", "면적구간", "평균거래금액", "거래건수"}


def test_compute_projection_output():
    avg = compute_monthly_avg(RAW)
    proj = compute_projection(avg)
    assert len(proj) == 1
    row = proj.iloc[0]
    assert row["단지명"] == "래미안대치팰리스"
    assert row["면적구간"] == "60~84㎡"
    assert "월평균변동" in proj.columns
    assert "다음달예상가" in proj.columns
    assert "5년CAGR" in proj.columns


def test_compute_projection_excludes_low_count():
    """거래 5건 미만 제외"""
    sparse = RAW.head(3).copy()  # 3건만
    avg = compute_monthly_avg(sparse)
    proj = compute_projection(avg, min_trades=5)
    assert len(proj) == 0
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_compute_stats.py -v
```
Expected: FAIL

- [ ] **Step 3: compute_stats.py 구현**

`scripts/compute_stats.py`:
```python
import numpy as np
import pandas as pd
from scipy import stats


def compute_monthly_avg(raw: pd.DataFrame) -> pd.DataFrame:
    """raw 거래 데이터 → 단지·면적구간·월별 평균가"""
    grouped = (
        raw.groupby(["거래년월", "구", "단지명", "면적구간"])["거래금액"]
        .agg(평균거래금액="mean", 거래건수="count")
        .reset_index()
    )
    grouped["평균거래금액"] = grouped["평균거래금액"].round(0).astype(int)
    return grouped.sort_values(["단지명", "면적구간", "거래년월"])


def compute_projection(monthly_avg: pd.DataFrame, min_trades: int = 5) -> pd.DataFrame:
    """monthly_avg → 단지별 선형회귀 기반 다음달 프로젝션"""
    results = []
    groups = monthly_avg.groupby(["구", "단지명", "면적구간"])

    for (district, apt, area), group in groups:
        total_trades = group["거래건수"].sum()
        if total_trades < min_trades:
            continue

        group = group.sort_values("거래년월")
        months = group["거래년월"].tolist()
        prices = group["평균거래금액"].tolist()

        # x축: 0, 1, 2, ... (월 순서)
        x = np.arange(len(prices))
        slope, intercept, _, _, _ = stats.linregress(x, prices)

        latest_price = prices[-1]
        next_price = round(latest_price + slope)
        first_price = prices[0]
        n_years = len(months) / 12
        cagr = ((latest_price / first_price) ** (1 / n_years) - 1) * 100 if n_years > 0 and first_price > 0 else 0

        results.append({
            "구": district,
            "단지명": apt,
            "면적구간": area,
            "데이터기간": f"{months[0]}~{months[-1]}",
            "최근실거래가": latest_price,
            "월평균변동": round(slope),
            "다음달예상가": next_price,
            "5년CAGR": round(cagr, 2),
            "총거래건수": total_trades,
        })

    return pd.DataFrame(results)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_compute_stats.py -v
```
Expected: 4개 PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/compute_stats.py tests/test_compute_stats.py
git commit -m "feat: monthly_avg + projection 계산 로직"
```

---

## Task 5: Google Sheets 업데이트 (update_sheets.py)

gspread로 Sheets 3탭(raw/monthly_avg/projection)을 업데이트한다.

**Files:**
- Create: `scripts/update_sheets.py`

- [ ] **Step 1: update_sheets.py 구현**

테스트는 실제 Sheets 연결이 필요해 통합테스트로 분류. 구현만 작성.

`scripts/update_sheets.py`:
```python
import json
import os
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_client() -> gspread.Client:
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    # 파일 경로이면 파일 읽기, JSON 문자열이면 직접 파싱
    if sa_json.strip().startswith("{"):
        info = json.loads(sa_json)
    else:
        with open(sa_json) as f:
            info = json.load(f)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def append_raw(gc: gspread.Client, spreadsheet_id: str, df: pd.DataFrame) -> None:
    """raw 탭에 신규 행 append (중복 거래년월 있으면 먼저 삭제 후 추가)"""
    sh = gc.open_by_key(spreadsheet_id)
    ws = _get_or_create(sh, "raw")

    if df.empty:
        return

    yyyymm = df["거래년월"].iloc[0]
    existing = ws.get_all_values()

    if len(existing) > 1:  # 헤더 포함
        headers = existing[0]
        if "거래년월" in headers:
            col_idx = headers.index("거래년월")
            rows_to_keep = [existing[0]] + [
                row for row in existing[1:] if row[col_idx] != yyyymm
            ]
            ws.clear()
            ws.update(rows_to_keep)

    rows = df.values.tolist()
    if not ws.get_all_values():  # 헤더 없으면 추가
        ws.append_row(df.columns.tolist())
    ws.append_rows(rows)


def overwrite_sheet(gc: gspread.Client, spreadsheet_id: str, tab_name: str, df: pd.DataFrame) -> None:
    """탭 전체를 df로 덮어쓴다"""
    sh = gc.open_by_key(spreadsheet_id)
    ws = _get_or_create(sh, tab_name)
    ws.clear()
    if df.empty:
        return
    ws.update([df.columns.tolist()] + df.values.tolist())


def _get_or_create(sh: gspread.Spreadsheet, tab_name: str) -> gspread.Worksheet:
    try:
        return sh.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=tab_name, rows=100, cols=30)
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/update_sheets.py
git commit -m "feat: Google Sheets 업데이트 모듈"
```

---

## Task 6: 월별 파이프라인 진입점 (run_monthly.py)

GitHub Actions가 호출하는 메인 스크립트. 전월 데이터를 수집해 Sheets를 업데이트한다.

**Files:**
- Create: `scripts/run_monthly.py`

- [ ] **Step 1: run_monthly.py 구현**

`scripts/run_monthly.py`:
```python
#!/usr/bin/env python3
"""매월 1일 GitHub Actions가 실행하는 진입점."""
import os
import sys
from datetime import date
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv()

from scripts.complexes import load_complexes
from scripts.fetch_transactions import fetch_all_districts
from scripts.compute_stats import compute_monthly_avg, compute_projection
from scripts.update_sheets import get_client, append_raw, overwrite_sheet


def previous_month_yyyymm() -> str:
    prev = date.today().replace(day=1) - relativedelta(months=1)
    return prev.strftime("%Y%m")


def main(yyyymm: str | None = None) -> None:
    yyyymm = yyyymm or previous_month_yyyymm()
    print(f"수집 대상 연월: {yyyymm}")

    api_key = os.environ["MOLIT_API_KEY"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    # 1. 단지 목록 로드
    complexes = load_complexes()
    print(f"500세대+ 단지 수: {len(complexes)}")

    # 2. 실거래 수집
    print("실거래가 수집 중...")
    raw = fetch_all_districts(yyyymm, api_key)
    print(f"수집된 거래: {len(raw)}건")

    # 3. 500세대+ 필터
    from scripts.complexes import is_target
    raw = raw[raw.apply(lambda r: is_target(r["단지명"], r["구"]), axis=1)]
    print(f"500세대+ 필터 후: {len(raw)}건")

    if raw.empty:
        print("수집된 거래 없음. 종료.")
        return

    # 4. Sheets 업데이트
    print("Sheets 업데이트 중...")
    gc = get_client()
    append_raw(gc, spreadsheet_id, raw)

    # monthly_avg, projection은 raw 전체 기반으로 재계산
    full_raw = _load_full_raw(gc, spreadsheet_id)
    monthly_avg = compute_monthly_avg(full_raw)
    projection = compute_projection(monthly_avg)

    overwrite_sheet(gc, spreadsheet_id, "monthly_avg", monthly_avg)
    overwrite_sheet(gc, spreadsheet_id, "projection", projection)
    print(f"완료. projection 단지 수: {len(projection)}")


def _load_full_raw(gc, spreadsheet_id: str):
    """raw 탭 전체를 DataFrame으로 로드"""
    import pandas as pd
    sh = gc.open_by_key(spreadsheet_id)
    ws = sh.worksheet("raw")
    data = ws.get_all_values()
    if len(data) < 2:
        return pd.DataFrame()
    headers, rows = data[0], data[1:]
    df = pd.DataFrame(rows, columns=headers)
    df["거래금액"] = df["거래금액"].astype(int)
    df["전용면적"] = df["전용면적"].astype(float)
    return df


if __name__ == "__main__":
    yyyymm_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(yyyymm_arg)
```

- [ ] **Step 2: python-dateutil requirements에 추가**

`requirements.txt` 에 한 줄 추가:
```
python-dateutil==2.9.0
```

재설치:
```bash
pip install python-dateutil==2.9.0
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/run_monthly.py requirements.txt
git commit -m "feat: 월별 파이프라인 진입점"
```

---

## Task 7: 백필 스크립트 (backfill.py)

5년치(60개월) 과거 데이터를 1회 적재. API 일일 호출 제한(1,000건) 때문에 체크포인트 저장 후 이어서 실행 가능.

**Files:**
- Create: `scripts/backfill.py`

- [ ] **Step 1: backfill.py 구현**

`scripts/backfill.py`:
```python
#!/usr/bin/env python3
"""5년치 과거 데이터 초기 적재 (1회 실행용).
일일 API 한도(1,000건) 때문에 2일에 나눠 실행 필요.
체크포인트: data/backfill_progress.txt
"""
import os
import sys
import time
from datetime import date
from dateutil.relativedelta import relativedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from scripts.complexes import load_complexes, is_target
from scripts.fetch_transactions import fetch_all_districts, SEOUL_DISTRICTS
from scripts.update_sheets import get_client, append_raw

CHECKPOINT_FILE = Path("data/backfill_progress.txt")
DAILY_LIMIT = 900  # 안전 마진 (한도 1000)


def generate_months(n_years: int = 5) -> list[str]:
    """최근 n년치 연월 목록 (과거 → 현재 순)"""
    today = date.today().replace(day=1)
    months = []
    for i in range(n_years * 12, 0, -1):
        m = today - relativedelta(months=i)
        months.append(m.strftime("%Y%m"))
    return months


def load_checkpoint() -> set[str]:
    if CHECKPOINT_FILE.exists():
        return set(CHECKPOINT_FILE.read_text().strip().splitlines())
    return set()


def save_checkpoint(done: set[str]) -> None:
    CHECKPOINT_FILE.parent.mkdir(exist_ok=True)
    CHECKPOINT_FILE.write_text("\n".join(sorted(done)))


def main(n_years: int = 5, dry_run: bool = False) -> None:
    api_key = os.environ["MOLIT_API_KEY"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    load_complexes()
    months = generate_months(n_years)
    done = load_checkpoint()
    remaining = [m for m in months if m not in done]

    print(f"전체 {len(months)}개월 중 완료 {len(done)}개, 남은 {len(remaining)}개")

    if not remaining:
        print("백필 완료됨.")
        return

    gc = get_client()
    call_count = 0

    for yyyymm in remaining:
        if call_count + len(SEOUL_DISTRICTS) > DAILY_LIMIT:
            print(f"\nAPI 일일 한도 도달 ({call_count}회). 내일 재실행하세요.")
            print(f"완료 연월: {len(done)}개 / {len(months)}개")
            break

        print(f"수집 중: {yyyymm} ...", end=" ", flush=True)
        if not dry_run:
            raw = fetch_all_districts(yyyymm, api_key, delay=0.3)
            raw = raw[raw.apply(lambda r: is_target(r["단지명"], r["구"]), axis=1)]
            if not raw.empty:
                append_raw(gc, spreadsheet_id, raw)
            print(f"{len(raw)}건")
        else:
            print("(dry-run 스킵)")

        done.add(yyyymm)
        save_checkpoint(done)
        call_count += len(SEOUL_DISTRICTS)
        time.sleep(0.2)

    print(f"\n이번 실행 완료. 체크포인트: {CHECKPOINT_FILE}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    years = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5
    main(n_years=years, dry_run=dry)
```

- [ ] **Step 2: dry-run으로 동작 확인**

```bash
python scripts/backfill.py 1 --dry-run
```
Expected: 12개월 (dry-run 스킵) 출력, `data/backfill_progress.txt` 생성

- [ ] **Step 3: 커밋**

```bash
git add scripts/backfill.py data/.gitkeep
git commit -m "feat: 5년치 백필 스크립트 (체크포인트 지원)"
```

---

## Task 8: GitHub Actions 워크플로우

**Files:**
- Create: `.github/workflows/monthly.yml`

- [ ] **Step 1: monthly.yml 작성**

`.github/workflows/monthly.yml`:
```yaml
name: Monthly Apt Price Update

on:
  schedule:
    - cron: '0 0 1 * *'   # 매월 1일 UTC 00:00 (한국 09:00)
  workflow_dispatch:        # 수동 실행 버튼

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run monthly update
        env:
          MOLIT_API_KEY: ${{ secrets.MOLIT_API_KEY }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          SPREADSHEET_ID: ${{ secrets.SPREADSHEET_ID }}
        run: python scripts/run_monthly.py

      - name: Upload log on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: error-log
          path: '*.log'
```

- [ ] **Step 2: .gitignore 생성**

`.gitignore`:
```
.env
venv/
__pycache__/
*.pyc
.pytest_cache/
data/backfill_progress.txt
*.log
```

- [ ] **Step 3: 전체 테스트 통과 확인**

```bash
pytest tests/ -v
```
Expected: 전체 PASS

- [ ] **Step 4: 최종 커밋**

```bash
git add .github/workflows/monthly.yml .gitignore
git commit -m "feat: GitHub Actions 월별 자동화 워크플로우"
```

---

## Task 9: 초기 셋업 및 백필 실행 (실제 데이터로)

- [ ] **Step 1: .env 파일 생성 (로컬)**

```bash
cp .env.example .env
# .env 열어서 실제 키 입력
```

- [ ] **Step 2: data/seoul_complexes.csv 준비**

```
1. https://data.seoul.go.kr 접속
2. "공동주택현황" 검색 → 최신 파일 CSV 다운로드
3. data/seoul_complexes.csv 로 저장
4. python -c "import pandas as pd; df=pd.read_csv('data/seoul_complexes.csv', encoding='utf-8-sig', nrows=3); print(df.columns.tolist())"
   → 출력된 컬럼명으로 complexes.py의 _detect_columns 매핑 확인
```

- [ ] **Step 3: 단지 목록 확인**

```bash
python -c "
from scripts.complexes import load_complexes
d = load_complexes()
print(f'500세대+ 단지 수: {len(d)}')
print('샘플:', list(d.items())[:3])
"
```
Expected: 500세대+ 단지 수: 1000 이상

- [ ] **Step 4: 1개월치 테스트 수집**

```bash
python scripts/run_monthly.py 202504
```
Expected: Sheets에 데이터 적재 확인

- [ ] **Step 5: 5년치 백필 (2일에 나눠서)**

```bash
# 1일차: 약 900건 API 호출 후 자동 중단
python scripts/backfill.py 5

# 2일차: 체크포인트 이어서
python scripts/backfill.py 5
```

- [ ] **Step 6: GitHub Secrets 등록**

```
저장소 → Settings → Secrets → New repository secret:
- MOLIT_API_KEY: (발급받은 키)
- GOOGLE_SERVICE_ACCOUNT_JSON: (JSON 파일 내용 전체 붙여넣기)
- SPREADSHEET_ID: (Sheets URL에서 /d/XXXX/edit 중 XXXX 부분)
```

- [ ] **Step 7: Actions 수동 실행 테스트**

GitHub 저장소 → Actions → Monthly Apt Price Update → Run workflow → 성공 확인

---

## Self-Review

**스펙 커버리지:**
- [x] 서울 25개 구 전체 수집 → fetch_all_districts
- [x] 500세대+ 필터 → complexes.py + is_target
- [x] 매월 자동 → GitHub Actions monthly.yml
- [x] Google Sheets raw/monthly_avg/projection → update_sheets.py
- [x] 5년 선형회귀 프로젝션 → compute_stats.py
- [x] 5건 미만 제외 → compute_projection(min_trades=5)
- [x] API 일일 한도 대응 → backfill.py DAILY_LIMIT + 체크포인트
- [x] 면적구간 4단계 → area_bucket

**플레이스홀더:** 없음

**타입 일관성:** `fetch_district_month` → DataFrame, `compute_monthly_avg` → DataFrame, `compute_projection` → DataFrame 전 단계 일치.
