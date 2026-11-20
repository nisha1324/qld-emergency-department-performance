"""Mix versus performance (Part 2).

An all-categories rate is a weighted average of the five triage categories:

    R = sum_i  s_i * r_i        s_i = the category's share, r_i = its own rate

so R can move because the shares moved (mix) or because the categories' own
rates moved (performance). Between two quarters the change splits exactly as

    R1 - R0 = sum_i (s1_i - s0_i) * (r0_i + r1_i) / 2      mix effect
            + sum_i (r1_i - r0_i) * (s0_i + s1_i) / 2      within-category effect

(the symmetric, or Kitagawa, decomposition: no leftover interaction term).

Every function takes the tidy table from edperf.load, or small frames built
from it, so each can be tested on hand-made data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .profile import TRIAGE_1_TO_5

# measure -> what its percentage is a share of
WEIGHT = {
    "stay_within_4h_pct": "attendances",
    "seen_on_time_pct": "attendances",
    "admitted_pct": "attendances",
    "admitted_within_4h_pct": "admitted",     # attendances x admitted share
}


class Incomplete(ValueError):
    """A category has patients but no published rate, so the split cannot be made."""


def cells(df: pd.DataFrame, measure: str) -> pd.DataFrame:
    """One row per quarter x facility x triage category 1-5, with the weight
    the measure is a share of and the category's own rate."""
    d = df[df["triage"].isin(TRIAGE_1_TO_5)]
    if WEIGHT[measure] == "attendances":
        weight = d["attendances"].astype(float)
    else:
        weight = (d["attendances"] * d["admitted_pct"] / 100).where(d["attendances"] > 0, 0.0)
    out = d[["quarter", "facility_code", "triage"]].copy()
    out["weight"] = weight
    out["rate"] = d[measure]
    return out.reset_index(drop=True)


def unit(c: pd.DataFrame, quarter: str, code: int) -> pd.DataFrame:
    """The five category rows of one facility in one quarter, indexed by triage."""
    u = c[(c["quarter"] == quarter) & (c["facility_code"] == code)].set_index("triage")
    return u.reindex(TRIAGE_1_TO_5)[["weight", "rate"]]


def pool(c: pd.DataFrame, quarter: str, codes) -> pd.DataFrame:
    """Several facilities in one quarter added together: weights are summed and
    each category's rate is the weighted mean of the facilities' rates."""
    g = c[(c["quarter"] == quarter) & c["facility_code"].isin(list(codes))]
    rows = {}
    for t in TRIAGE_1_TO_5:
        part = g[(g["triage"] == t) & (g["weight"] > 0)]
        w = float(part["weight"].sum())
        if part["rate"].isna().any():
            rate = float("nan")
        else:
            rate = float((part["weight"] * part["rate"]).sum() / w) if w > 0 else float("nan")
        rows[t] = {"weight": w, "rate": rate}
    return pd.DataFrame.from_dict(rows, orient="index")[["weight", "rate"]]


def _checked(u: pd.DataFrame) -> pd.DataFrame:
    u = u.copy()
    u["weight"] = u["weight"].fillna(0.0)
    if (u["rate"].isna() & (u["weight"] > 0)).any():
        raise Incomplete("a category has a weight but no rate")
    if u["weight"].sum() <= 0:
        raise Incomplete("no weight at all")
    return u


def rebuilt(u: pd.DataFrame) -> float:
    """The all-categories rate implied by the categories."""
    u = _checked(u)
    return float((u["weight"] * u["rate"].fillna(0.0)).sum() / u["weight"].sum())


def decompose(u0: pd.DataFrame, u1: pd.DataFrame) -> dict:
    """Split the change in the rebuilt rate between two periods into a mix
    effect and a within-category effect. A category with no patients in one
    period borrows the other period's rate, so all of its change counts as mix."""
    u0, u1 = _checked(u0), _checked(u1)
    s0 = u0["weight"] / u0["weight"].sum()
    s1 = u1["weight"] / u1["weight"].sum()
    r0 = u0["rate"].where(u0["weight"] > 0)
    r1 = u1["rate"].where(u1["weight"] > 0)
    r0, r1 = r0.fillna(r1).fillna(0.0), r1.fillna(r0).fillna(0.0)
    by = pd.DataFrame({
        "share_0": 100 * s0, "share_1": 100 * s1, "rate_0": r0, "rate_1": r1,
        "mix": (s1 - s0) * (r0 + r1) / 2,
        "within": (r1 - r0) * (s0 + s1) / 2,
    })
    return {
        "rate_0": float((s0 * r0).sum()), "rate_1": float((s1 * r1).sum()),
        "change": float((s1 * r1).sum() - (s0 * r0).sum()),
        "mix": float(by["mix"].sum()), "within": float(by["within"].sum()),
        "by_category": by,
    }


def rounding_margin(d: dict, tol_0: float, tol_1: float) -> dict:
    """How far each effect could move if every published category rate were off
    by up to its rounding (tol_0 at the start, tol_1 at the end). Shares come
    from counts and are taken as exact."""
    by = d["by_category"]
    return {
        "within": float(tol_0 + tol_1),
        "mix": float((by["share_1"] - by["share_0"]).abs().sum() / 100 * (tol_0 + tol_1) / 2),
    }


def fixed_mix_series(c: pd.DataFrame, code: int, base_quarter: str) -> pd.DataFrame:
    """Per quarter: the rebuilt rate, and what it would have been with the
    base quarter's shares (direct standardisation)."""
    base = _checked(unit(c, base_quarter, code))
    s_base = base["weight"] / base["weight"].sum()
    rows = []
    for q in sorted(c["quarter"].unique()):
        u = _checked(unit(c, q, code))
        rows.append({"quarter": q, "rebuilt": rebuilt(u),
                     "fixed_mix": float((s_base * u["rate"].fillna(0.0)).sum())})
    return pd.DataFrame(rows)


def rebuild_gaps(df: pd.DataFrame, measure: str, code: int) -> pd.DataFrame:
    """Per quarter: the published all-categories rate against the one rebuilt
    from the five categories."""
    c = cells(df, measure)
    pub = df[(df["facility_code"] == code) & (df["triage"] == "ALL")].set_index("quarter")[measure]
    rows = []
    for q in sorted(c["quarter"].unique()):
        r = rebuilt(unit(c, q, code))
        rows.append({"quarter": q, "published": float(pub[q]), "rebuilt": r, "gap": r - float(pub[q])})
    return pd.DataFrame(rows)


def year_on_year(c: pd.DataFrame, code: int, lag: int = 4) -> pd.DataFrame:
    """The split for every quarter against the same quarter `lag` quarters earlier."""
    quarters = sorted(c["quarter"].unique())
    rows = []
    for q0, q1 in zip(quarters[:-lag], quarters[lag:]):
        d = decompose(unit(c, q0, code), unit(c, q1, code))
        rows.append({"quarter_0": q0, "quarter_1": q1, "rate_0": d["rate_0"], "rate_1": d["rate_1"],
                     "change": d["change"], "mix": d["mix"], "within": d["within"]})
    return pd.DataFrame(rows)


def hospital_table(df: pd.DataFrame, measure: str, q0: str, q1: str, codes) -> pd.DataFrame:
    """The split for each hospital in `codes` between two quarters, worst change
    first. Hospitals with a missing category rate are left out."""
    c = cells(df, measure)
    a = df[df["triage"] == "ALL"].set_index(["quarter", "facility_code"])
    rows = []
    for code in sorted(codes):
        try:
            d = decompose(unit(c, q0, code), unit(c, q1, code))
        except Incomplete:
            continue
        by = d["by_category"]
        rows.append({
            "facility_code": code, "facility_name": a.loc[(q1, code), "facility_name"],
            "attendances": int(a.loc[(q1, code), "attendances"]),
            "published_0": float(a.loc[(q0, code), measure]), "published_1": float(a.loc[(q1, code), measure]),
            "rate_0": d["rate_0"], "rate_1": d["rate_1"], "change": d["change"],
            "mix": d["mix"], "within": d["within"],
            "urgent_share_0": float(by.loc[["1", "2"], "share_0"].sum()),
            "urgent_share_1": float(by.loc[["1", "2"], "share_1"].sum()),
        })
    out = pd.DataFrame(rows)
    return out.sort_values(["change", "facility_code"], kind="stable").reset_index(drop=True)


def large_codes(df: pd.DataFrame, quarter: str, threshold: int) -> list[int]:
    a = df[(df["triage"] == "ALL") & (df["quarter"] == quarter) & ~df["is_state_total"]]
    return sorted(a.loc[a["attendances"] >= threshold, "facility_code"].tolist())


def admitted_split(row: pd.Series) -> pd.DataFrame:
    """One all-categories row seen as two groups, admitted and not admitted.
    The 4-hour rate of the patients who were not admitted is not published; it
    is what the other three published figures imply:

        stay = a * admitted_4h + (1 - a) * not_admitted_4h
    """
    a = row["admitted_pct"] / 100
    not_admitted = (row["stay_within_4h_pct"] - a * row["admitted_within_4h_pct"]) / (1 - a)
    return pd.DataFrame({"weight": [a, 1 - a], "rate": [row["admitted_within_4h_pct"], not_admitted]},
                        index=["admitted", "not admitted"])


def implied_margin(row: pd.Series, tol: float) -> float:
    """Largest error in the implied not-admitted rate if each of the three
    published inputs is off by up to `tol` points."""
    base = admitted_split(row).loc["not admitted", "rate"]
    worst = 0.0
    for da in (-tol, tol):
        for db in (-tol, tol):
            for ds in (-tol, tol):
                r = row.copy()
                r["admitted_pct"] += da
                r["admitted_within_4h_pct"] += db
                r["stay_within_4h_pct"] += ds
                worst = max(worst, abs(admitted_split(r).loc["not admitted", "rate"] - base))
    return float(worst)


def share_of_change(part: float, change: float) -> float:
    """`part` as a percentage of `change` (NaN when there is no change)."""
    return float(100 * part / change) if abs(change) > 1e-12 else float(np.nan)
