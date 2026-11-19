from pathlib import Path

import pandas as pd
import pytest

from edperf import load

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def snapshot() -> pd.DataFrame:
    return load.read_snapshot(ROOT / "data" / "ed_quarterly.csv")


def make_rows(quarter, code, name, att, **cols):
    """Six tidy rows (triage 1-5 + ALL) for one facility-quarter. `att` lists
    attendances for categories 1-5; other columns take one value per row or a scalar."""
    tri = ["1", "2", "3", "4", "5", "ALL"]
    df = pd.DataFrame({
        "quarter": quarter, "facility_code": code, "facility_name": name,
        "is_state_total": code == load.STATE_CODE, "triage": tri,
        "attendances": list(att) + [sum(att)],
    })
    defaults = {"did_not_wait": 0, "left_after_treatment": 0, "attendances_change_pct": float("nan"),
                "seen_on_time_pct": 80.0, "median_wait_min": 10.0, "did_not_wait_pct": 0.0,
                "left_after_treatment_pct": 0.0, "admitted_pct": 20.0, "admitted_within_4h_pct": 40.0,
                "stay_within_4h_pct": 70.0}
    for col, default in defaults.items():
        df[col] = cols.get(col, default)
    return df[load.TIDY]
