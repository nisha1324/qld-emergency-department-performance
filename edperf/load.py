"""Turn the raw quarterly files into one tidy table.

One row per facility x quarter x triage category. What gets cleaned up:

- Column names drift ("Triage Category" / "Triage_Category"; five quarters carry
  an extra "Median Wait Traffic Light" column, which is dropped).
- The all-categories row is "All" in one quarter and "ALL" in the others.
- Hospital names change between quarters ("Ipswich Hospital" / "Ipswich"); the
  facility code is the stable key, and the name used is the one in the latest
  quarter the facility appears in.
- Missing values come as "-", "NULL", "" or null. All become empty (NaN).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import source

STATE_CODE = 99999          # the "Queensland" total row
TRIAGE = ["1", "2", "3", "4", "5", "ALL"]
MISSING = {"-", "NULL", ""}

# raw column -> tidy column
COLUMNS = {
    "Facility/HHS Code": "facility_code",
    "Facility/HHS Desc": "facility_name",
    "Last Month in QTR": "quarter_label",
    "Triage Category": "triage",
    "Triage_Category": "triage",
    "Number of Attendances": "attendances",
    "Variation in the number of attendances (%)": "attendances_change_pct",
    "Patients Seen within clinically recommended times (%)": "seen_on_time_pct",
    "Median Waiting time to treatment (minutes)": "median_wait_min",
    "Patients who did not wait for treatment (%)": "did_not_wait_pct",
    "Patients admitted from the Emergency Department (%)": "admitted_pct",
    "Admissions to hospital within 4 hours (%)": "admitted_within_4h_pct",
    "Patients whose ED stay was within 4 hours (%)": "stay_within_4h_pct",
    "Number of patients who left after treatment commenced": "left_after_treatment",
    "Percentage of patients who left after treatment commenced (%)": "left_after_treatment_pct",
    "Number of patients who did not wait for treatment": "did_not_wait",
}
DROPPED = {"_id", "Median Wait Traffic Light"}
COUNTS = ["attendances", "did_not_wait", "left_after_treatment"]
RATES = [
    "attendances_change_pct", "seen_on_time_pct", "median_wait_min", "did_not_wait_pct",
    "left_after_treatment_pct", "admitted_pct", "admitted_within_4h_pct", "stay_within_4h_pct",
]
TIDY = ["quarter", "facility_code", "facility_name", "is_state_total", "triage"] + COUNTS + RATES


def read_raw(path: Path) -> pd.DataFrame:
    """One raw file as a table of strings (None where the portal has null)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return pd.DataFrame(payload["records"], columns=payload["fields"], dtype=object)


def _number(s: pd.Series) -> pd.Series:
    text = s.astype("string").str.strip()
    text = text.mask(text.isin(MISSING))
    return pd.to_numeric(text, errors="raise").astype(float)


def tidy_quarter(raw: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """Clean one quarter. `quarter` is its last month, YYYY-MM."""
    unknown = set(raw.columns) - set(COLUMNS) - DROPPED
    if unknown:
        raise ValueError(f"{quarter}: unexpected column(s) {sorted(unknown)}")
    df = raw.drop(columns=[c for c in raw.columns if c in DROPPED]).rename(columns=COLUMNS)
    missing = set(COLUMNS.values()) - set(df.columns)
    if missing:
        raise ValueError(f"{quarter}: missing column(s) {sorted(missing)}")

    labels = pd.to_datetime(df["quarter_label"], format="%b-%y").dt.strftime("%Y-%m").unique()
    if list(labels) != [quarter]:
        raise ValueError(f"{quarter}: file says it holds {list(labels)}")

    out = pd.DataFrame({"quarter": quarter}, index=df.index)
    out["facility_code"] = df["facility_code"].astype(int)
    out["facility_name"] = df["facility_name"].str.strip()
    out["is_state_total"] = out["facility_code"] == STATE_CODE
    out["triage"] = df["triage"].str.strip().str.upper()
    bad = set(out["triage"]) - set(TRIAGE)
    if bad:
        raise ValueError(f"{quarter}: unexpected triage value(s) {sorted(bad)}")
    for col in COUNTS + RATES:
        out[col] = _number(df[col])
    for col in COUNTS:
        if out[col].isna().any() or (out[col] % 1 != 0).any() or (out[col] < 0).any():
            raise ValueError(f"{quarter}: {col} is not a whole, non-negative number everywhere")
        out[col] = out[col].astype(int)
    if out.duplicated(["facility_code", "triage"]).any():
        raise ValueError(f"{quarter}: duplicate facility x triage rows")
    return out[TIDY]


def canonical_names(df: pd.DataFrame) -> pd.Series:
    """facility_code -> the name used in the latest quarter that facility appears in."""
    latest = df.sort_values("quarter", kind="stable").groupby("facility_code")["facility_name"].last()
    return latest


def combine(quarters: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.concat([quarters[q] for q in sorted(quarters)], ignore_index=True)
    df["facility_name"] = df["facility_code"].map(canonical_names(df))
    df["triage"] = pd.Categorical(df["triage"], categories=TRIAGE, ordered=True)
    df = df.sort_values(["quarter", "is_state_total", "facility_code", "triage"], kind="stable")
    df["triage"] = df["triage"].astype(str)
    return df.reset_index(drop=True)


def build(raw_dir: Path) -> pd.DataFrame:
    """Every pinned quarter in `raw_dir`, cleaned and stacked."""
    quarters = {}
    for quarter in source.RESOURCES:
        path = Path(raw_dir) / source.raw_name(quarter)
        quarters[quarter] = tidy_quarter(read_raw(path), quarter)
    return combine(quarters)


def name_variants(raw_dir: Path) -> pd.DataFrame:
    """Every spelling each facility code has had, for the profile."""
    rows = []
    for quarter in source.RESOURCES:
        raw = read_raw(Path(raw_dir) / source.raw_name(quarter))
        part = raw[["Facility/HHS Code", "Facility/HHS Desc"]].drop_duplicates()
        part.columns = ["facility_code", "raw_name"]
        part["facility_code"] = part["facility_code"].astype(int)
        part["quarter"] = quarter
        rows.append(part)
    allq = pd.concat(rows, ignore_index=True)
    out = (allq.groupby(["facility_code", "raw_name"], as_index=False)
           .agg(first_quarter=("quarter", "min"), last_quarter=("quarter", "max"),
                quarters=("quarter", "nunique")))
    return out.sort_values(["facility_code", "first_quarter", "raw_name"], kind="stable").reset_index(drop=True)


def read_snapshot(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"quarter": str, "triage": str, "facility_name": str})
