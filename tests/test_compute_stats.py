import pandas as pd
import numpy as np
from scripts.compute_stats import compute_monthly_avg, compute_projection

RAW = pd.DataFrame([
    {"거래년월": "202101", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 230000},
    {"거래년월": "202101", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 240000},
    {"거래년월": "202201", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 250000},
    {"거래년월": "202301", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 260000},
    {"거래년월": "202401", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 270000},
    {"거래년월": "202501", "구": "강남구", "단지명": "래미안대치팰리스", "면적구간": "60~84㎡", "거래금액": 280000},
])


def test_compute_monthly_avg_groups_correctly():
    avg = compute_monthly_avg(RAW)
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
    sparse = RAW.head(3).copy()
    avg = compute_monthly_avg(sparse)
    proj = compute_projection(avg, min_trades=5)
    assert len(proj) == 0
