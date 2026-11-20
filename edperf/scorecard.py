"""Hospital scorecard (Part 3).

Two questions per hospital, each asked against hospitals of a similar size:

level   Where does its 4-hour rate sit among its peers once every hospital is
        given the same triage mix (direct standardisation to the peer group's
        pooled mix)? "Below peers" means the lowest quarter of the group.
trend   Did its rate move within triage categories between two quarters (the
        within-category effect from edperf.mix), by more than the number of
        patients behind the figures could explain by chance?

The chance bar treats each category's patients as independent yes/no outcomes
(binomial). Real ED stays are not independent (a crowded day delays everyone),
so the bar is a floor, not a full confidence interval: a change inside it is
noise, a change outside it is worth a look.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import mix as M
from .profile import TRIAGE_1_TO_5

Z = 2.58  # two-sided 99%: with about 100 hospitals, about one false flag by chance

# name, lowest attendances in the quarter, upper bound (exclusive)
SIZE_BANDS = (("large", 10_000, None), ("medium", 2_500, 10_000), ("small", 0, 2_500))
GROUPS = [b[0] for b in SIZE_BANDS]


def peer_group(attendances: float) -> str:
    for name, lo, hi in SIZE_BANDS:
        if attendances >= lo and (hi is None or attendances < hi):
            return name
    raise ValueError(f"no size band for {attendances!r}")


def reference_shares(c: pd.DataFrame, quarter: str, codes) -> pd.Series:
    """The triage mix of several hospitals added together (shares sum to 1)."""
    w = M.pool(c, quarter, codes)["weight"]
    if w.sum() <= 0:
        raise M.Incomplete("no patients in the reference group")
    return w / w.sum()


def _variance(rate: pd.Series, n: pd.Series) -> pd.Series:
    """Binomial variance of a percentage, in points squared; 0 where n is 0."""
    return (rate * (100 - rate) / n.where(n > 0)).fillna(0.0)


def standardised(u: pd.DataFrame, s_ref: pd.Series) -> dict:
    """The hospital's rate if it had the reference mix. A category in which the
    hospital saw nobody is left out and the other reference shares are scaled
    up; `covered` is the share of the reference mix that was not left out."""
    u = M._checked(u)
    present = u["weight"] > 0
    covered = float(s_ref[present].sum())
    s = (s_ref.where(present, 0.0) / covered)
    r = u["rate"].where(present, 0.0)
    rate = float((s * r).sum())
    se = math.sqrt(float((s ** 2 * _variance(r, u["weight"].where(present, 0.0))).sum()))
    return {"rate": rate, "se": se, "covered": covered}


def within_se(u0: pd.DataFrame, u1: pd.DataFrame) -> float:
    """Chance-only standard error of the within-category effect, in points.
    A category with nobody in one of the two periods adds nothing to the
    effect (see mix.decompose), so it adds nothing here either."""
    u0, u1 = M._checked(u0), M._checked(u1)
    s0 = u0["weight"] / u0["weight"].sum()
    s1 = u1["weight"] / u1["weight"].sum()
    both = (u0["weight"] > 0) & (u1["weight"] > 0)
    avg = ((s0 + s1) / 2).where(both, 0.0)
    var = _variance(u0["rate"], u0["weight"]) + _variance(u1["rate"], u1["weight"])
    return math.sqrt(float((avg ** 2 * var).sum()))


def direction(value: float, se: float, z: float = Z) -> str:
    """'up', 'down' or 'flat': flat when the value is inside z standard errors of zero."""
    if value is None or np.isnan(value):
        return "n/a"
    if value > z * se:
        return "up"
    if value < -z * se:
        return "down"
    return "flat"


def level(row, z: float = Z) -> str:
    """'below peers' = in the lowest quarter of the peer group on the
    standardised rate and further below the peer median than chance allows;
    'above peers' is the mirror image; everything else is 'in line'."""
    side = direction(row.vs_peers, row.standardised_se, z)
    if side == "down" and row.standardised <= row.peer_q25:
        return "below peers"
    if side == "up" and row.standardised >= row.peer_q75:
        return "above peers"
    return "in line"


TREND = {"up": "improving", "down": "slipping", "flat": "no clear change", "n/a": "new"}


def scorecard(df: pd.DataFrame, measure: str, q0: str, q1: str, q_mid: str | None = None,
              z: float = Z) -> pd.DataFrame:
    """One row per hospital reporting in q1. Peer groups come from q1
    attendances. A hospital that did not report in q0 gets a level but no trend."""
    c = M.cells(df, measure)
    a = df[(df["triage"] == "ALL") & ~df["is_state_total"]].set_index(["quarter", "facility_code"])
    end = a.xs(q1, level="quarter")
    start_codes = set(a.xs(q0, level="quarter").index)
    groups = end["attendances"].map(peer_group)
    ref = {g: reference_shares(c, q1, groups[groups == g].index) for g in GROUPS if (groups == g).any()}

    rows = []
    for code in sorted(end.index):
        g = groups[code]
        u1 = M.unit(c, q1, code)
        std = standardised(u1, ref[g])
        row = {
            "facility_code": code, "facility_name": end.loc[code, "facility_name"], "peer_group": g,
            "attendances": int(end.loc[code, "attendances"]), "published_1": float(end.loc[code, measure]),
            "standardised": std["rate"], "standardised_se": std["se"], "mix_covered": std["covered"],
            "published_0": np.nan, "change": np.nan, "mix": np.nan, "within": np.nan, "within_se": np.nan,
            "within_first": np.nan, "within_second": np.nan,
        }
        if code in start_codes:
            u0 = M.unit(c, q0, code)
            d = M.decompose(u0, u1)
            row.update(published_0=float(a.loc[(q0, code), measure]), change=d["change"], mix=d["mix"],
                       within=d["within"], within_se=within_se(u0, u1))
            if q_mid is not None and (q_mid, code) in a.index:
                um = M.unit(c, q_mid, code)
                row.update(within_first=M.decompose(u0, um)["within"], within_second=M.decompose(um, u1)["within"])
        rows.append(row)
    out = pd.DataFrame(rows)

    out["peer_median"] = out.groupby("peer_group")["standardised"].transform("median")
    out["vs_peers"] = out["standardised"] - out["peer_median"]
    grp = out.groupby("peer_group")["standardised"]
    out["peer_q25"], out["peer_q75"] = grp.transform(lambda s: s.quantile(0.25)), grp.transform(lambda s: s.quantile(0.75))
    out["level"] = [level(r, z) for r in out.itertuples(index=False)]
    out["trend"] = [TREND[direction(v, se, z)] for v, se in zip(out["within"], out["within_se"])]
    out["bar"] = z * out["within_se"]
    # roughly how many of the latest quarter's patients the within-category change represents
    out["patients_equivalent"] = out["within"] / 100 * out["attendances"]
    order = {g: i for i, g in enumerate(GROUPS)}
    out["_g"] = out["peer_group"].map(order)
    out = out.sort_values(["_g", "within", "facility_code"], kind="stable", na_position="last")
    return out.drop(columns="_g").reset_index(drop=True)


def group_summary(df: pd.DataFrame, card: pd.DataFrame, measure: str, q0: str, q1: str) -> pd.DataFrame:
    """Per peer group: size, pooled rates and the pooled split for hospitals with both quarters."""
    c = M.cells(df, measure)
    total = card["attendances"].sum()
    rows = []
    for g in GROUPS:
        k = card[card["peer_group"] == g]
        both = k[k["within"].notna()]
        if both.empty:
            continue
        d = M.decompose(M.pool(c, q0, both["facility_code"]), M.pool(c, q1, both["facility_code"]))
        rows.append({
            "peer_group": g, "hospitals": len(k), "with_both_quarters": len(both),
            "attendances": int(k["attendances"].sum()), "attendance_share": 100 * k["attendances"].sum() / total,
            "pooled_rate_1": M.rebuilt(M.pool(c, q1, k["facility_code"])),
            "median_standardised": float(k["standardised"].median()),
            "min_standardised": float(k["standardised"].min()), "max_standardised": float(k["standardised"].max()),
            "pooled_change": d["change"], "pooled_mix": d["mix"], "pooled_within": d["within"],
            "slipping": int((k["trend"] == "slipping").sum()), "improving": int((k["trend"] == "improving").sum()),
            "no_clear_change": int((k["trend"] == "no clear change").sum()),
            "below_peers": int((k["level"] == "below peers").sum()), "above_peers": int((k["level"] == "above peers").sum()),
        })
    return pd.DataFrame(rows)
