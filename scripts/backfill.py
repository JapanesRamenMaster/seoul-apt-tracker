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
DAILY_LIMIT = 900


def generate_months(n_years: int = 5) -> list:
    today = date.today().replace(day=1)
    months = []
    for i in range(n_years * 12, 0, -1):
        m = today - relativedelta(months=i)
        months.append(m.strftime("%Y%m"))
    return months


def load_checkpoint() -> set:
    if CHECKPOINT_FILE.exists():
        return set(CHECKPOINT_FILE.read_text().strip().splitlines())
    return set()


def save_checkpoint(done: set) -> None:
    CHECKPOINT_FILE.parent.mkdir(exist_ok=True)
    CHECKPOINT_FILE.write_text("\n".join(sorted(done)))


def main(n_years: int = 5, dry_run: bool = False) -> None:
    api_key = os.environ.get("MOLIT_API_KEY", "")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

    load_complexes()
    months = generate_months(n_years)
    done = load_checkpoint()
    remaining = [m for m in months if m not in done]

    print(f"전체 {len(months)}개월 중 완료 {len(done)}개, 남은 {len(remaining)}개")

    if not remaining:
        print("백필 완료됨.")
        return

    if not dry_run:
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
    years_args = [a for a in sys.argv[1:] if a.isdigit()]
    years = int(years_args[0]) if years_args else 5
    main(n_years=years, dry_run=dry)
