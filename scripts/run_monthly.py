#!/usr/bin/env python3
"""매월 1일 GitHub Actions가 실행하는 진입점."""
import os
import sys
from datetime import date
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv()

from scripts.complexes import load_complexes, is_target
from scripts.fetch_transactions import fetch_all_districts
from scripts.compute_stats import compute_monthly_avg, compute_projection
from scripts.update_sheets import get_client, append_raw, overwrite_sheet


def previous_month_yyyymm() -> str:
    prev = date.today().replace(day=1) - relativedelta(months=1)
    return prev.strftime("%Y%m")


def main(yyyymm: str = None) -> None:
    yyyymm = yyyymm or previous_month_yyyymm()
    print(f"수집 대상 연월: {yyyymm}")

    api_key = os.environ["MOLIT_API_KEY"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    complexes = load_complexes()
    print(f"500세대+ 단지 수: {len(complexes)}")

    print("실거래가 수집 중...")
    raw = fetch_all_districts(yyyymm, api_key)
    print(f"수집된 거래: {len(raw)}건")

    raw = raw[raw.apply(lambda r: is_target(r["단지명"], r["구"]), axis=1)]
    print(f"500세대+ 필터 후: {len(raw)}건")

    if raw.empty:
        print("수집된 거래 없음. 종료.")
        return

    print("Sheets 업데이트 중...")
    gc = get_client()
    append_raw(gc, spreadsheet_id, raw)

    full_raw = _load_full_raw(gc, spreadsheet_id)
    monthly_avg = compute_monthly_avg(full_raw)
    projection = compute_projection(monthly_avg)

    overwrite_sheet(gc, spreadsheet_id, "monthly_avg", monthly_avg)
    overwrite_sheet(gc, spreadsheet_id, "projection", projection)
    print(f"완료. projection 단지 수: {len(projection)}")


def _load_full_raw(gc, spreadsheet_id: str):
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
