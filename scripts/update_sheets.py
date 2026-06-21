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
    if sa_json.strip().startswith("{"):
        info = json.loads(sa_json)
    else:
        with open(sa_json) as f:
            info = json.load(f)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def append_raw(gc: gspread.Client, spreadsheet_id: str, df: pd.DataFrame) -> None:
    """raw 탭에 신규 행 append. 같은 거래년월이 이미 있으면 먼저 삭제 후 추가."""
    sh = gc.open_by_key(spreadsheet_id)
    ws = _get_or_create(sh, "raw")

    if df.empty:
        return

    yyyymm = df["거래년월"].iloc[0]
    existing = ws.get_all_values()

    if len(existing) > 1:
        headers = existing[0]
        if "거래년월" in headers:
            col_idx = headers.index("거래년월")
            rows_to_keep = [existing[0]] + [
                row for row in existing[1:] if row[col_idx] != yyyymm
            ]
            ws.clear()
            ws.update(rows_to_keep)

    if not ws.get_all_values():
        ws.append_row(df.columns.tolist())
    ws.append_rows(df.values.tolist())


def overwrite_sheet(gc: gspread.Client, spreadsheet_id: str, tab_name: str, df: pd.DataFrame) -> None:
    """탭 전체를 df로 덮어쓴다."""
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
