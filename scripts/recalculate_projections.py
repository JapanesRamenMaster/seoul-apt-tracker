"""3년 슬로프(window_months=36)로 projection 재계산 + 내 예산 범위 탭 업데이트."""
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from scripts.compute_stats import compute_monthly_avg, compute_projection
from scripts.update_sheets import get_client, overwrite_sheet

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
BUDGET = 160000  # 16억, 단위: 만원
MONTHS_TO_PROJECT = 21  # 2026-05 → 2028-02

MONTHLY_AVG_COLS = ["거래년월", "구", "단지명", "면적구간", "평균거래금액", "거래건수"]


def load_monthly_avg(gc):
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet("monthly_avg")
    data = ws.get_all_values()
    if len(data) < 2:
        return pd.DataFrame()
    rows = data[1:] if data[0][0] == "거래년월" else data
    df = pd.DataFrame(rows, columns=MONTHLY_AVG_COLS)
    df["평균거래금액"] = pd.to_numeric(df["평균거래금액"], errors="coerce").fillna(0).astype(int)
    df["거래건수"] = pd.to_numeric(df["거래건수"], errors="coerce").fillna(0).astype(int)
    return df


def fmt_ok(val_man):
    """만원 값 → '↑X.X억' 형식"""
    val_ek = val_man / 10000
    arrow = "↑" if val_ek >= 0 else "↓"
    return f"{arrow}{abs(val_ek):.1f}억"


def fmt_price(val_man, latest_yyyymm):
    """만원 값 → 'X.X억 (YYYY.MM)' 형식"""
    val_ek = val_man / 10000
    ym = f"{latest_yyyymm[:4]}.{latest_yyyymm[4:]}"
    return f"{val_ek:.1f}억 ({ym})"


def fmt_proj(val_man):
    """만원 값 → 'X.X억' 형식"""
    return f"{val_man / 10000:.1f}억"


def update_budget_tab(gc, proj_df):
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet("내 예산 범위")
    data = ws.get_all_values()

    # 헤더는 row4(index3), 데이터는 row5(index4)+
    # 컬럼(0-indexed): B=1단지명, C=2구, D=3면적, E=4현재가, F=5예상가, G=6기간변화, H=7예산대비, L=11월변동

    # projection 인덱스: (단지명, 면적구간) → row
    proj_index = {}
    for _, row in proj_df.iterrows():
        proj_index[(row["단지명"], row["면적구간"])] = row

    batch = []
    matched = 0

    for row_idx in range(4, len(data)):  # 0-indexed, row5부터
        r = data[row_idx]
        if len(r) < 4:
            continue
        name = r[1].strip()
        area = r[3].strip()
        if not name or not area:
            continue

        proj_row = proj_index.get((name, area))
        if proj_row is None:
            continue

        new_slope = int(proj_row["월평균변동"])
        latest_price = int(proj_row["최근실거래가"])
        latest_yyyymm = str(proj_row["데이터기간"]).split("~")[-1].strip()
        new_proj = latest_price + new_slope * MONTHS_TO_PROJECT
        period_change = new_slope * MONTHS_TO_PROJECT
        diff = new_proj - BUDGET

        sheet_row = row_idx + 1  # 1-indexed

        batch.extend([
            {"range": f"E{sheet_row}", "values": [[fmt_price(latest_price, latest_yyyymm)]]},
            {"range": f"F{sheet_row}", "values": [[fmt_proj(new_proj)]]},
            {"range": f"G{sheet_row}", "values": [[fmt_ok(period_change)]]},
            {"range": f"H{sheet_row}", "values": [[fmt_ok(diff)]]},
            {"range": f"L{sheet_row}", "values": [[fmt_ok(new_slope)]]},
        ])
        matched += 1

    print(f"  budget 탭 매칭: {matched}개 / {len(data) - 4}행")

    # 배치 업데이트 (1000개씩)
    for i in range(0, len(batch), 1000):
        ws.batch_update(batch[i:i+1000], value_input_option="USER_ENTERED")
    print(f"  budget 탭 업데이트 완료")


def main():
    gc = get_client()

    print("monthly_avg 로드 중...")
    monthly_avg = load_monthly_avg(gc)
    print(f"  monthly_avg: {len(monthly_avg)}행")

    print("3년 window(36개월)로 projection 재계산 중...")
    projection = compute_projection(monthly_avg, min_trades=5, window_months=36)
    print(f"  projection: {len(projection)}개 단지")

    # slope 분포 확인
    slopes = projection["월평균변동"]
    print(f"  slope 분포: 중앙값={int(slopes.median()):,}만, 평균={int(slopes.mean()):,}만")
    print(f"  상승({slopes > 0} ... ): 상승={( slopes > 0).sum()}개, 하락={(slopes < 0).sum()}개")

    print("projection 탭 업데이트 중...")
    overwrite_sheet(gc, SPREADSHEET_ID, "projection", projection)

    print("내 예산 범위 탭 업데이트 중...")
    update_budget_tab(gc, projection)

    print("완료!")


if __name__ == "__main__":
    main()
