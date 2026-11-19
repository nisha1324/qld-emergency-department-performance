"""Measures for the source profile (Part 1). Every function takes the tidy table
from edperf.load and returns a small DataFrame or dict, so each can be tested
on hand-made data."""
from __future__ import annotations

import numpy as np
import pandas as pd

RATES = [
    "attendances_change_pct", "seen_on_time_pct", "median_wait_min", "did_not_wait_pct",
    "left_after_treatment_pct", "admitted_pct", "admitted_within_4h_pct", "stay_within_4h_pct",
]
PCT_RATES = [r for r in RATES if r != "median_wait_min"]
TRIAGE_1_TO_5 = ["1", "2", "3", "4", "5"]
EPS = 1e-9


def hospitals(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["is_state_total"]]


def state(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["is_state_total"]]


def all_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["triage"] == "ALL"]


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per quarter: hospitals reporting, rows, and rows with no attendances."""
    h = hospitals(df)
    out = h.groupby("quarter").agg(
        hospitals=("facility_code", "nunique"),
        rows=("facility_code", "size"),
        zero_attendance_rows=("attendances", lambda s: int((s == 0).sum())),
    )
    out["attendances"] = all_rows(h).groupby("quarter")["attendances"].sum()
    return out.reset_index()


def decimal_share(df: pd.DataFrame) -> pd.Series:
    """Per quarter, the share of published percentages that are not whole numbers.
    0 means the quarter was published rounded to whole percentages."""
    def share(g: pd.DataFrame) -> float:
        vals = g[PCT_RATES].to_numpy(dtype=float).ravel()
        vals = vals[~np.isnan(vals)]
        return float((np.abs(vals - np.round(vals)) > EPS).mean())
    return df.groupby("quarter")[PCT_RATES].apply(share)


def rate_tolerance(quarter: pd.Series, whole: set[str]) -> pd.Series:
    """Half a unit of the published precision: 0.5 for whole-number quarters, else 0.05."""
    return pd.Series(np.where(quarter.isin(whole), 0.5, 0.05), index=quarter.index)


def whole_number_quarters(df: pd.DataFrame) -> set[str]:
    share = decimal_share(df)
    return set(share[share == 0].index)


def state_trend(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["quarter", "attendances", "seen_on_time_pct", "median_wait_min", "stay_within_4h_pct",
            "admitted_pct", "admitted_within_4h_pct", "did_not_wait", "left_after_treatment"]
    out = all_rows(state(df))[cols].sort_values("quarter", kind="stable").reset_index(drop=True)
    out["did_not_wait_pct"] = 100 * out["did_not_wait"] / out["attendances"]
    out["left_after_treatment_pct"] = 100 * out["left_after_treatment"] / out["attendances"]
    return out


def rolling_year(df: pd.DataFrame) -> pd.DataFrame:
    """State attendances over the four quarters ending at each quarter."""
    s = state_trend(df)[["quarter", "attendances"]].copy()
    s["attendances_4q"] = s["attendances"].rolling(4).sum()
    return s.dropna().astype({"attendances_4q": int}).reset_index(drop=True)


def triage_table(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """The state rows for one quarter, with each category's share of attendances."""
    s = state(df)
    s = s[s["quarter"] == quarter].copy()
    total = s.loc[s["triage"] == "ALL", "attendances"].iloc[0]
    s["share_pct"] = 100 * s["attendances"] / total
    cols = ["triage", "attendances", "share_pct", "seen_on_time_pct", "median_wait_min",
            "admitted_pct", "admitted_within_4h_pct", "stay_within_4h_pct"]
    return s[cols].reset_index(drop=True)


def triage_mix(df: pd.DataFrame) -> pd.DataFrame:
    """Each triage category's share of state attendances, per quarter (wide)."""
    s = state(df).pivot(index="quarter", columns="triage", values="attendances")
    return (100 * s[TRIAGE_1_TO_5].div(s["ALL"], axis=0)).reset_index()


def size_table(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    """Hospitals in one quarter, largest first, with the running share of attendances."""
    h = all_rows(hospitals(df))
    h = h[h["quarter"] == quarter].sort_values(
        ["attendances", "facility_code"], ascending=[False, True], kind="stable")
    cols = ["facility_code", "facility_name", "attendances", "seen_on_time_pct", "median_wait_min",
            "admitted_pct", "admitted_within_4h_pct", "stay_within_4h_pct"]
    out = h[cols].reset_index(drop=True)
    out["cum_share_pct"] = 100 * out["attendances"].cumsum() / out["attendances"].sum()
    return out


def size_summary(sizes: pd.DataFrame, threshold: int) -> pd.DataFrame:
    """Large (>= threshold attendances in the quarter) vs the rest."""
    big = sizes["attendances"] >= threshold
    rows = []
    for label, part in [(f"{threshold:,} or more", sizes[big]), (f"under {threshold:,}", sizes[~big])]:
        rows.append({
            "attendances_in_quarter": label,
            "hospitals": len(part),
            "attendances": int(part["attendances"].sum()),
            "share_pct": 100 * part["attendances"].sum() / sizes["attendances"].sum(),
            "stay_within_4h_weighted": (float(np.average(part["stay_within_4h_pct"], weights=part["attendances"]))
                                        if len(part) else float("nan")),
            "stay_within_4h_median": part["stay_within_4h_pct"].median(),
            "stay_within_4h_min": part["stay_within_4h_pct"].min(),
            "stay_within_4h_max": part["stay_within_4h_pct"].max(),
            "seen_on_time_median": part["seen_on_time_pct"].median(),
        })
    return pd.DataFrame(rows)


def missing_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per measure: empty cells, split by whether the row had any attendances."""
    rows = []
    for col in RATES:
        m = df[df[col].isna()]
        rows.append({
            "measure": col,
            "empty": len(m),
            "of_which_no_attendances": int((m["attendances"] == 0).sum()),
            "of_which_with_attendances": int((m["attendances"] > 0).sum()),
            "quarters_affected_with_attendances": int(m.loc[m["attendances"] > 0, "quarter"].nunique()),
        })
    return pd.DataFrame(rows)


def dash_for_zero(df: pd.DataFrame) -> pd.DataFrame:
    """Per quarter: of rows with attendances but nobody who left without waiting,
    how many publish that percentage as 0 and how many leave it empty."""
    z = df[(df["attendances"] > 0) & (df["did_not_wait"] == 0)]
    out = z.groupby("quarter").agg(
        rows=("did_not_wait", "size"),
        published_as_zero=("did_not_wait_pct", lambda s: int((s == 0).sum())),
        published_empty=("did_not_wait_pct", lambda s: int(s.isna().sum())),
    )
    return out.reset_index()


def check_triage_sums(df: pd.DataFrame) -> dict:
    p = df.pivot(index=["quarter", "facility_code"], columns="triage", values="attendances")
    diff = p[TRIAGE_1_TO_5].sum(axis=1) - p["ALL"]
    return {"facility_quarters": int(len(diff)), "mismatches": int((diff != 0).sum())}


def check_state_sums(df: pd.DataFrame) -> dict:
    out = {"quarters": int(df["quarter"].nunique())}
    for col in ["attendances", "did_not_wait", "left_after_treatment"]:
        a = all_rows(df)
        total = a[a["is_state_total"]].set_index("quarter")[col]
        summed = a[~a["is_state_total"]].groupby("quarter")[col].sum()
        out[f"{col}_mismatches"] = int((total != summed.reindex(total.index)).sum())
    return out


def check_rates_from_counts(df: pd.DataFrame) -> dict:
    """Do the published 'did not wait' and 'left after treatment' percentages equal
    count / attendances, to the published rounding?"""
    whole = whole_number_quarters(df)
    d = df[df["attendances"] > 0]
    tol = rate_tolerance(d["quarter"], whole)
    out = {}
    for count, rate in [("did_not_wait", "did_not_wait_pct"),
                        ("left_after_treatment", "left_after_treatment_pct")]:
        gap = (100 * d[count] / d["attendances"] - d[rate]).abs()
        ok = gap.notna()
        out[f"{rate}_compared"] = int(ok.sum())
        out[f"{rate}_mismatches"] = int((gap[ok] > tol[ok] + EPS).sum())
    return out


def change_check(df: pd.DataFrame) -> pd.DataFrame:
    """The published 'variation in attendances' against attendances four quarters
    earlier in this snapshot. One row per facility x triage x quarter where both exist."""
    whole = whole_number_quarters(df)
    quarters = sorted(df["quarter"].unique())
    earlier = dict(zip(quarters[4:], quarters[:-4]))
    key = ["facility_code", "triage"]
    prev = df[["quarter"] + key + ["attendances"]].rename(
        columns={"quarter": "prev_quarter", "attendances": "attendances_year_earlier"})
    cur = df[df["quarter"].isin(earlier)].copy()
    cur["prev_quarter"] = cur["quarter"].map(earlier)
    m = cur.merge(prev, on=["prev_quarter"] + key, how="inner")
    m = m[(m["attendances_year_earlier"] > 0) & m["attendances_change_pct"].notna()].copy()
    m["recomputed_pct"] = 100 * (m["attendances"] / m["attendances_year_earlier"] - 1)
    m["gap"] = (m["recomputed_pct"] - m["attendances_change_pct"]).abs()
    m["mismatch"] = m["gap"] > rate_tolerance(m["quarter"], whole) + EPS
    m["implied_year_earlier"] = (m["attendances"] / (1 + m["attendances_change_pct"] / 100)).round()
    cols = ["quarter", "facility_code", "facility_name", "is_state_total", "triage", "attendances",
            "attendances_year_earlier", "attendances_change_pct", "recomputed_pct", "gap",
            "mismatch", "implied_year_earlier"]
    return m[cols].reset_index(drop=True)


def check_state_rate_is_weighted(df: pd.DataFrame, col: str) -> float:
    """Largest gap, over quarters, between the state rate and the attendance-weighted
    mean of hospital rates (all triage categories)."""
    a = all_rows(df)
    h = a[~a["is_state_total"]].dropna(subset=[col])
    weighted = h.groupby("quarter")[[col, "attendances"]].apply(
        lambda g: float(np.average(g[col], weights=g["attendances"])))
    total = a[a["is_state_total"]].set_index("quarter")[col]
    return float((weighted - total).abs().max())


def simple_vs_weighted(df: pd.DataFrame, quarter: str, col: str) -> dict:
    """The state rate against the plain average of hospital rates."""
    a = all_rows(df)
    a = a[a["quarter"] == quarter]
    h = a[~a["is_state_total"]]
    return {
        "state": float(a.loc[a["is_state_total"], col].iloc[0]),
        "simple_mean_of_hospitals": float(h[col].mean()),
        "median_hospital": float(h[col].median()),
    }


def new_facilities(df: pd.DataFrame) -> pd.DataFrame:
    """Hospitals that are not in every quarter."""
    h = hospitals(df)
    n_q = h["quarter"].nunique()
    g = h.groupby(["facility_code", "facility_name"]).agg(
        first_quarter=("quarter", "min"), last_quarter=("quarter", "max"),
        quarters=("quarter", "nunique")).reset_index()
    return g[g["quarters"] < n_q].reset_index(drop=True)
