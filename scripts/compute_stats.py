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


def compute_projection(monthly_avg: pd.DataFrame, min_trades: int = 5, window_months: int = 0) -> pd.DataFrame:
    """monthly_avg → 단지별 선형회귀 기반 다음달 프로젝션

    window_months: 0이면 전체 기간, N이면 최근 N개월만 회귀에 사용.
    window 내 거래가 min_trades 미만이면 전체 기간 fallback.
    """
    results = []
    groups = monthly_avg.groupby(["구", "단지명", "면적구간"])

    for (district, apt, area), group in groups:
        total_trades = group["거래건수"].sum()
        if total_trades < min_trades:
            continue

        group = group.sort_values("거래년월")

        # window 필터 (최근 N캘린더월)
        if window_months > 0:
            all_months = sorted(group["거래년월"].tolist())
            latest = all_months[-1]  # "YYYYMM"
            y, m = int(latest[:4]), int(latest[4:])
            total = y * 12 + m - window_months
            cy, cm = total // 12, total % 12
            if cm == 0:
                cy -= 1
                cm = 12
            cutoff = f"{cy:04d}{cm:02d}"
            windowed = group[group["거래년월"] >= cutoff]
            if windowed["거래건수"].sum() >= min_trades:
                group = windowed
            # min_trades 미달이면 전체 기간 그대로 사용

        months = group["거래년월"].tolist()
        prices = group["평균거래금액"].tolist()

        # 캘린더 기반 x축: YYYYMM → 절대 월수, 시작점 0 정규화
        # 데이터 공백이 있어도 실제 경과 시간을 반영
        x_abs = [int(m[:4]) * 12 + int(m[4:]) for m in months]
        x0 = x_abs[0]
        x = [xi - x0 for xi in x_abs]
        slope, intercept, _, _, _ = stats.linregress(x, prices)

        if np.isnan(slope):
            continue  # 데이터 1개월뿐이면 회귀 불가

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
