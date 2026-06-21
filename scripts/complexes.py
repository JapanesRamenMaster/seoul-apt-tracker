from pathlib import Path
import pandas as pd

_COMPLEX_DICT: dict[tuple[str, str], int] = {}

DEFAULT_CSV = Path(__file__).parent.parent / "data" / "seoul_complexes.csv"
TRANSACTION_CSV = Path(__file__).parent.parent / "data" / "complexes_from_transactions.csv"


def load_complexes(csv_path: Path = None) -> dict[tuple[str, str], int]:
    """단지 목록 로드 → {(단지명, 구): 거래수 or 세대수} dict.

    우선순위:
    1. csv_path 명시 → 해당 파일
    2. data/seoul_complexes.csv 존재 → 세대수 기반 (정확)
    3. data/complexes_from_transactions.csv → 트랜잭션 프록시 (세대수 미상)
    """
    global _COMPLEX_DICT

    if csv_path is None:
        if DEFAULT_CSV.exists():
            csv_path = DEFAULT_CSV
        elif TRANSACTION_CSV.exists():
            csv_path = TRANSACTION_CSV
        else:
            raise FileNotFoundError(
                "단지 목록 파일 없음. scripts/backfill.py 또는 build_complex_list_from_transactions() 실행 필요"
            )

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # 트랜잭션 기반 파일 (컬럼: 단지명, 구, 거래수)
    if "거래수" in df.columns and "구" in df.columns:
        _COMPLEX_DICT = {
            (_normalize(row["단지명"]), row["구"]): int(row["거래수"])
            for _, row in df.iterrows()
        }
    else:
        # 서울시 공동주택현황 CSV (컬럼 자동 감지)
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
        elif col.endswith("구") and "자치구" not in mapping.values():
            mapping[col] = "자치구"
        elif "세대" in col and "세대수" not in mapping.values():
            mapping[col] = "세대수"
    return mapping
