from pathlib import Path
import pandas as pd

_COMPLEX_DICT: dict[tuple[str, str], int] = {}

DEFAULT_CSV = Path(__file__).parent.parent / "data" / "seoul_complexes.csv"


def load_complexes(csv_path: Path = DEFAULT_CSV) -> dict[tuple[str, str], int]:
    """CSV 로드 → {(단지명, 구): 세대수} dict (500세대 이상만)"""
    global _COMPLEX_DICT
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
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
