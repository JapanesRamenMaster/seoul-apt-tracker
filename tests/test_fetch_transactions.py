from pathlib import Path
from unittest.mock import Mock
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
