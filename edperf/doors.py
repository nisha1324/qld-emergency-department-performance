"""Front door versus back door (Part 4).

Part 3 says which hospitals' 4-hour rate moved. This module asks where in the
ED the movement sits, using three things the source publishes per triage
category:

front door   waiting to be seen: patients seen within the recommended time,
             and patients who gave up and left before being seen (did not wait)
admitted     patients who leave the ED for a hospital bed: their 4-hour rate
not admitted everyone else (mostly sent home): their 4-hour rate is not
             published, but three published figures imply it (edperf.mix)

Each triage category is cut into the two streams, giving ten cells. The change
in a hospital's 4-hour rate then splits exactly into four parts:

    change = triage mix                 the five categories' shares moved
           + admission share            within a category, the admitted share moved
           + admitted stream            admitted patients' own rate moved
           + not-admitted stream        everyone else's own rate moved

The first is Part 2's mix effect, unchanged. The other three add up to Part 2's
within-category effect. Each stream effect gets the same chance bar as Part 3.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import mix as M
from . import scorecard as SC
from .profile import TRIAGE_1_TO_5

STAY = "stay_within_4h_pct"
STREAMS = ("admitted", "not admitted")
CELLS = pd.MultiIndex.from_product([TRIAGE_1_TO_5, STREAMS], names=["triage", "stream"])
# counts the source publishes per category, as a share of attendances
COUNTS = ("did_not_wait", "left_after_treatment")
TOL = 0.05  # the two quarters compared are published to one decimal place


def stream_cells(df: pd.DataFrame, tol: float = TOL) -> pd.DataFrame:
    """Two rows per quarter x facility x triage category 1-5: the admitted and
    the not-admitted patients, each with a head count (`weight`) and a 4-hour
    rate. The not-admitted rate is the one implied by

        stay = a * admitted_4h + (1 - a) * not_admitted_4h      a = admitted share

    It is left as implied (it can sit a hair outside 0-100 because the inputs
    are rounded) so that the ten cells add back to the published category rate.

    `rounding` is how far the cell's rate could be off if every published
    percentage behind it were wrong by `tol` points in the worst direction
    (first order): `tol` for a published rate, more for an implied one, and
    much more where nearly everyone in the category is admitted.
    """
    d = df[df["triage"].isin(TRIAGE_1_TO_5)]
    att = d["attendances"].astype(float)
    a = (d["admitted_pct"] / 100).where(att > 0, 0.0)
    adm = d[["quarter", "facility_code", "triage"]].copy()
    adm["stream"] = "admitted"
    adm["weight"] = att * a
    adm["rate"] = d["admitted_within_4h_pct"]
    adm["rounding"] = tol
    non = d[["quarter", "facility_code", "triage"]].copy()
    non["stream"] = "not admitted"
    non["weight"] = att * (1 - a)
    with np.errstate(divide="ignore", invalid="ignore"):
        implied = (d[STAY] - a * d["admitted_within_4h_pct"].fillna(0.0)) / (1 - a)
    non["rate"] = implied.where(a < 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        gap = (d["admitted_within_4h_pct"].fillna(0.0) - implied).abs()
        non["rounding"] = ((tol * (1 + a) + tol / 100 * gap) / (1 - a)).where(a < 1)
    return pd.concat([adm, non], ignore_index=True)


def count_cells(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Cells in the shape edperf.mix expects, for a published count (did not
    wait, left after treatment) as a percentage of the category's attendances."""
    if column not in COUNTS:
        raise ValueError(f"not a count column: {column!r}")
    d = df[df["triage"].isin(TRIAGE_1_TO_5)]
    out = d[["quarter", "facility_code", "triage"]].copy()
    out["weight"] = d["attendances"].astype(float)
    out["rate"] = (100 * d[column] / d["attendances"]).where(d["attendances"] > 0)
    return out.reset_index(drop=True)


def unit(sc: pd.DataFrame, quarter: str, code: int) -> pd.DataFrame:
    """The ten cells of one facility in one quarter, indexed by (triage, stream)."""
    u = sc[(sc["quarter"] == quarter) & (sc["facility_code"] == code)].set_index(["triage", "stream"])
    return u.reindex(CELLS)[["weight", "rate", "rounding"]]


def pool(sc: pd.DataFrame, quarter: str, codes) -> pd.DataFrame:
    """Several facilities in one quarter added together, cell by cell."""
    g = sc[(sc["quarter"] == quarter) & sc["facility_code"].isin(list(codes)) & (sc["weight"] > 0)]
    if g["rate"].isna().any():
        raise M.Incomplete("a cell has patients but no rate")
    g = g.assign(hits=g["weight"] * g["rate"])
    s = g.groupby(["triage", "stream"])[["weight", "hits"]].sum().reindex(CELLS)
    out = pd.DataFrame({"weight": s["weight"].fillna(0.0), "rate": s["hits"] / s["weight"]})
    return out[["weight", "rate"]]


def stream_rate(u: pd.DataFrame, stream: str) -> float:
    """The all-categories 4-hour rate of one stream (NaN if it has no patients)."""
    k = u.xs(stream, level="stream")
    w = k["weight"].fillna(0.0)
    return float((w * k["rate"].fillna(0.0)).sum() / w.sum()) if w.sum() > 0 else float("nan")


def stream_share(u: pd.DataFrame, stream: str) -> float:
    """The stream's patients as a percentage of all patients."""
    w = u["weight"].fillna(0.0)
    return float(100 * w.xs(stream, level="stream").sum() / w.sum())


def _stream_se(u0: pd.DataFrame, u1: pd.DataFrame, stream: str) -> float:
    """Chance-only standard error of one stream's effect, in points of the
    hospital's all-patients rate (same construction as scorecard.within_se).
    Implied rates are clipped to 0-100 for the variance only."""
    w0, w1 = u0["weight"].fillna(0.0), u1["weight"].fillna(0.0)
    s0, s1 = w0 / w0.sum(), w1 / w1.sum()
    both = (w0 > 0) & (w1 > 0) & (u0.index.get_level_values("stream") == stream)
    avg = ((s0 + s1) / 2).where(both, 0.0)
    var = SC._variance(u0["rate"].clip(0, 100), w0) + SC._variance(u1["rate"].clip(0, 100), w1)
    return math.sqrt(float((avg ** 2 * var).sum()))


def _stream_rounding(u0: pd.DataFrame, u1: pd.DataFrame, stream: str) -> float:
    """Worst-case effect of rounding in the published figures on one stream's
    effect, in points (NaN when the cells carry no rounding column)."""
    if "rounding" not in u0.columns or "rounding" not in u1.columns:
        return float("nan")
    w0, w1 = u0["weight"].fillna(0.0), u1["weight"].fillna(0.0)
    s0, s1 = w0 / w0.sum(), w1 / w1.sum()
    both = (w0 > 0) & (w1 > 0) & (u0.index.get_level_values("stream") == stream)
    avg = ((s0 + s1) / 2).where(both, 0.0)
    return float((avg * (u0["rounding"].fillna(0.0) + u1["rounding"].fillna(0.0))).sum())


def four_way(t0: pd.DataFrame, t1: pd.DataFrame, u0: pd.DataFrame, u1: pd.DataFrame) -> dict:
    """Split the change in the 4-hour rate between two periods.

    t0, t1  the five triage cells (edperf.mix.unit on the stay measure)
    u0, u1  the ten triage x stream cells (unit or pool in this module)

    Returns the four effects (they add up to `change`), each stream's
    chance-only standard error and worst-case rounding, and each stream's own
    rate and share at both ends.
    """
    d5 = M.decompose(t0, t1)
    d10 = M.decompose(u0, u1)
    by = d10["by_category"]
    stream = by.index.get_level_values("stream")
    adm = float(by.loc[stream == "admitted", "within"].sum())
    non = float(by.loc[stream == "not admitted", "within"].sum())
    return {
        "rate_0": d10["rate_0"], "rate_1": d10["rate_1"], "change": d10["change"],
        "triage_mix": d5["mix"],
        "admission_share": d10["change"] - d5["mix"] - adm - non,
        "admitted": adm, "not_admitted": non,
        "admitted_se": _stream_se(u0, u1, "admitted"), "not_admitted_se": _stream_se(u0, u1, "not admitted"),
        "admitted_rounding": _stream_rounding(u0, u1, "admitted"),
        "not_admitted_rounding": _stream_rounding(u0, u1, "not admitted"),
        "admitted_rate_0": stream_rate(u0, "admitted"), "admitted_rate_1": stream_rate(u1, "admitted"),
        "not_admitted_rate_0": stream_rate(u0, "not admitted"), "not_admitted_rate_1": stream_rate(u1, "not admitted"),
        "admitted_share_0": stream_share(u0, "admitted"), "admitted_share_1": stream_share(u1, "admitted"),
        "rebuild_gap": d10["change"] - d5["change"],
    }


PATTERNS = ("both streams", "admitted only", "not admitted only", "neither stream")


def pattern(admitted_trend: str, not_admitted_trend: str) -> str:
    """Which stream(s) a hospital is slipping in."""
    a, n = admitted_trend == "slipping", not_admitted_trend == "slipping"
    if a and n:
        return "both streams"
    if a:
        return "admitted only"
    if n:
        return "not admitted only"
    return "neither stream"


WALKOUT = {"up": "rising", "down": "falling", "flat": "no clear change", "n/a": "new"}


def count_change(c: pd.DataFrame, q0: str, q1: str, code: int, z: float = SC.Z) -> dict:
    """Start and end rate of a count measure, its within-category change, the
    chance bar and a verdict ('rising' is worse: more patients leaving)."""
    u0, u1 = M.unit(c, q0, code), M.unit(c, q1, code)
    d = M.decompose(u0, u1)
    se = SC.within_se(u0, u1)
    return {"rate_0": d["rate_0"], "rate_1": d["rate_1"], "change": d["change"], "within": d["within"],
            "bar": z * se, "trend": WALKOUT[SC.direction(d["within"], se, z)]}


def doors(df: pd.DataFrame, q0: str, q1: str, z: float = SC.Z) -> pd.DataFrame:
    """One row per hospital that reported in both quarters: the four-way split
    of its 4-hour change, a verdict for each stream, and the walk-out measures."""
    t = M.cells(df, STAY)
    sc = stream_cells(df)
    dnw, left = count_cells(df, "did_not_wait"), count_cells(df, "left_after_treatment")
    a = df[(df["triage"] == "ALL") & ~df["is_state_total"]].set_index(["quarter", "facility_code"])
    codes = sorted(set(a.xs(q0, level="quarter").index) & set(a.xs(q1, level="quarter").index))
    rows = []
    for code in codes:
        f = four_way(M.unit(t, q0, code), M.unit(t, q1, code), unit(sc, q0, code), unit(sc, q1, code))
        w, l = count_change(dnw, q0, q1, code, z), count_change(left, q0, q1, code, z)
        row = {"facility_code": code, "facility_name": a.loc[(q1, code), "facility_name"]}
        row.update({k: v for k, v in f.items() if not k.endswith("_se")})
        row.update(
            admitted_bar=z * f["admitted_se"], not_admitted_bar=z * f["not_admitted_se"],
            admitted_trend=SC.TREND[SC.direction(f["admitted"], f["admitted_se"], z)],
            not_admitted_trend=SC.TREND[SC.direction(f["not_admitted"], f["not_admitted_se"], z)],
            # does the verdict survive the worst-case rounding added to the bar?
            admitted_robust=abs(f["admitted"]) > z * f["admitted_se"] + f["admitted_rounding"],
            not_admitted_robust=abs(f["not_admitted"]) > z * f["not_admitted_se"] + f["not_admitted_rounding"],
            median_wait_0=float(a.loc[(q0, code), "median_wait_min"]),
            median_wait_1=float(a.loc[(q1, code), "median_wait_min"]),
            dnw_rate_0=w["rate_0"], dnw_rate_1=w["rate_1"], dnw_within=w["within"], dnw_bar=w["bar"], dnw_trend=w["trend"],
            left_rate_0=l["rate_0"], left_rate_1=l["rate_1"], left_within=l["within"], left_bar=l["bar"],
            left_trend=l["trend"],
        )
        row["pattern"] = pattern(row["admitted_trend"], row["not_admitted_trend"])
        rows.append(row)
    return pd.DataFrame(rows)


def pooled(df: pd.DataFrame, q0: str, q1: str, codes) -> dict:
    """The four-way split for several hospitals added together."""
    t, sc = M.cells(df, STAY), stream_cells(df)
    return four_way(M.pool(t, q0, codes), M.pool(t, q1, codes), pool(sc, q0, codes), pool(sc, q1, codes))


def pooled_count(df: pd.DataFrame, column: str, q0: str, q1: str, codes) -> dict:
    """Start and end rate of a count measure for several hospitals together, with the split."""
    c = count_cells(df, column)
    d = M.decompose(M.pool(c, q0, codes), M.pool(c, q1, codes))
    return {"rate_0": d["rate_0"], "rate_1": d["rate_1"], "change": d["change"], "mix": d["mix"], "within": d["within"]}
