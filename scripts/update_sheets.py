import os
import gspread
import pandas as pd
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_DEFAULT_KEY_PATH = "/Users/trive/.claude/google-sheets-key.json"
IMPERSONATE_SUBJECT = "juseong.maeng@thetrive.com"


def get_client() -> gspread.Client:
    import json as _json
    sa_val = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", _DEFAULT_KEY_PATH)
    # JSON 문자열이면 직접 파싱, 파일 경로면 파일 읽기
    if sa_val.strip().startswith("{"):
        info = _json.loads(sa_val)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
    else:
        creds = service_account.Credentials.from_service_account_file(
            sa_val, scopes=SCOPES
        )
    return gspread.Client(auth=creds.with_subject(IMPERSONATE_SUBJECT))


RAW_COLUMNS = ["거래년월", "구", "법정동", "단지명", "전용면적", "면적구간", "거래금액", "층"]


def append_raw(gc: gspread.Client, spreadsheet_id: str, df: pd.DataFrame) -> None:
    """raw 탭에 신규 행 append. 같은 거래년월이 있으면 먼저 삭제 후 추가.
    항상 헤더를 첫 행으로 유지한다.
    """
    sh = gc.open_by_key(spreadsheet_id)
    ws = _get_or_create(sh, "raw")

    if df.empty:
        return

    yyyymm = df["거래년월"].iloc[0]
    existing = ws.get_all_values()

    # 기존 데이터에서 같은 연월 제거 (헤더 제외)
    if existing:
        # 헤더 여부 판단: 첫 행에 숫자만 있으면 헤더 없는 것
        has_header = existing[0][0] == "거래년월"
        data_rows = existing[1:] if has_header else existing
        kept = [row for row in data_rows if row[0] != yyyymm]
    else:
        kept = []

    # 헤더 + 기존 데이터 + 신규 데이터 전체 덮어쓰기
    all_rows = [RAW_COLUMNS] + kept + df.values.tolist()
    ws.clear()
    ws.update(all_rows)


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
