import pytest
from pathlib import Path
from scripts.complexes import load_complexes

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_complexes.csv"


def test_load_complexes_returns_dict():
    result = load_complexes(FIXTURE_CSV)
    assert isinstance(result, dict)
    assert ("래미안대치팰리스", "강남구") in result
    assert result[("래미안대치팰리스", "강남구")] == 1608


def test_load_complexes_filters_500():
    result = load_complexes(FIXTURE_CSV)
    keys = set(result.keys())
    assert ("소규모단지", "강남구") not in keys  # 200세대 제외
    assert ("은마아파트", "강남구") in keys       # 4424세대 포함


def test_is_target_complex():
    from scripts.complexes import is_target
    load_complexes(FIXTURE_CSV)
    assert is_target("래미안대치팰리스", "강남구") is True
    assert is_target("소규모단지", "강남구") is False
