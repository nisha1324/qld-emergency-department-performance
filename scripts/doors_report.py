"""Part 4: front door versus back door. Writes results/FRONT_VS_BACK_DOOR.md, CSVs and charts 10-12.

    python scripts/doors_report.py

Reads only the committed snapshot in data/ (no download needed).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from edperf import doors as D, load, mix as M, scorecard as SC  # noqa: E402
from scripts import mix_report as R2, profile_source as B, scorecard_report as R3  # noqa: E402

DATA, RESULTS, CHARTS = B.DATA, B.RESULTS, B.CHARTS
BLUE, ORANGE, INK, INK_2, MUTED, GRID = B.BLUE, B.ORANGE, B.INK, B.INK_2, B.MUTED, B.GRID
qname, sg, table = B.qname, R2.sg, R2.table
BAND, TRENDS = R3.BAND, R3.TRENDS
S = load.STATE_CODE
WALK = ["rising", "no clear change", "falling"]
ZERO_WAIT, STEP_WAIT = 1, 5  # minutes: "recorded as seen on arrival", and a wait that is clearly no longer that
EFFECTS = ["triage_mix", "admission_share", "admitted", "not_admitted"]


def analyse(df: pd.DataFrame) -> dict:
    """Everything the report, CSVs and charts are built from."""
    r3 = R3.analyse(df)
    q0, q1 = r3["q0"], r3["q1"]
    d = D.doors(df, q0, q1)
    k = r3["card"].merge(d.drop(columns=["facility_name", "change", "rate_0", "rate_1"]), on="facility_code",
                         validate="one_to_one")
    assert len(k) == len(d) == int(r3["card"]["within"].notna().sum())
    k["wait_step"] = (k["median_wait_0"] <= ZERO_WAIT) & (k["median_wait_1"] >= STEP_WAIT)
    new = r3["card"][r3["card"]["within"].isna()]
    # Part 2's split of the state figure into admitted / not admitted, without triage
    a_state = df[(df["triage"] == "ALL") & df["is_state_total"]].set_index("quarter")
    part2 = M.decompose(M.admitted_split(a_state.loc[q0]), M.admitted_split(a_state.loc[q1]))["by_category"]["within"]

    def pooled_row(label: str, codes) -> dict:
        row = {"group": label, "hospitals": len(codes), **D.pooled(df, q0, q1, codes)}
        for col, short in (("did_not_wait", "dnw"), ("left_after_treatment", "left")):
            c = D.pooled_count(df, col, q0, q1, codes)
            row.update({f"{short}_rate_0": c["rate_0"], f"{short}_rate_1": c["rate_1"], f"{short}_within": c["within"]})
        return row

    rows = [pooled_row("state", [S])]
    rows[0]["hospitals"] = len(k)
    rows += [pooled_row(g, list(k.loc[k["peer_group"] == g, "facility_code"])) for g in SC.GROUPS]
    groups = pd.DataFrame(rows).drop(columns=["rebuild_gap", "admitted_rounding", "not_admitted_rounding"])

    # did-not-wait rate per quarter for the same hospitals, by peer group
    a = df[(df["triage"] == "ALL") & df["facility_code"].isin(k["facility_code"])]
    a = a.merge(k[["facility_code", "peer_group"]], on="facility_code")
    by_q = a.groupby(["quarter", "peer_group"])[["attendances", "did_not_wait", "left_after_treatment"]].sum().reset_index()
    by_q["did_not_wait_pct"] = 100 * by_q["did_not_wait"] / by_q["attendances"]
    by_q["left_after_treatment_pct"] = 100 * by_q["left_after_treatment"] / by_q["attendances"]
    n_q = a.groupby("facility_code")["quarter"].nunique()
    assert (n_q == len(r3["quarters"])).all(), "every scored hospital should report in every quarter"

    lg = k[k["peer_group"] == "large"]
    return {**{x: r3[x] for x in ("q0", "q1", "quarters")}, "k": k, "groups": groups, "walkouts": by_q,
            "new": list(new["facility_name"]), "part2_within": part2,
            "stream_corr": float(np.corrcoef(lg["admitted"], lg["not_admitted"])[0, 1]),
            "max_gap": float(d["rebuild_gap"].abs().max())}


# ------------------------------------------------------------------ charts
def chart_streams(k: pd.DataFrame, q0: str, q1: str, path: Path) -> None:
    lg = k[k["peer_group"] == "large"].copy()
    lg["both"] = lg["admitted"] + lg["not_admitted"]
    lg = lg.sort_values(["both", "facility_code"], kind="stable").reset_index(drop=True)
    n = len(lg)
    fig, ax = plt.subplots(figsize=(8.5, 8.4))
    h = 0.34
    for i, row in enumerate(lg.itertuples(index=False)):
        y = n - 1 - i
        for off, v, bar, colour in ((h / 2 + 0.02, row.admitted, row.admitted_bar, ORANGE),
                                    (-h / 2 - 0.02, row.not_admitted, row.not_admitted_bar, BLUE)):
            clear = abs(v) > bar
            ax.barh(y + off, v, height=h, color=colour, alpha=1.0 if clear else 0.3, linewidth=0)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks(range(n), list(lg["facility_name"])[::-1], fontsize=9)
    ax.set_xlim(-6.5, 7.5)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_xlabel("Contribution to the change in the hospital's 4-hour rate, percentage points")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=ORANGE), plt.Rectangle((0, 0), 1, 1, color=BLUE),
               plt.Rectangle((0, 0), 1, 1, color=MUTED, alpha=0.3)]
    fig.legend(handles, ["Admitted patients", "Patients not admitted (implied rate)", "Pale: inside the chance bar"],
               loc="upper left", bbox_to_anchor=(0.012, 0.945), ncol=3, frameon=False, fontsize=9, labelcolor=INK_2)
    slip = lg[lg["trend"] == "slipping"]
    n_non = int((slip["not_admitted_trend"] == "slipping").sum())
    fig.suptitle(f"{n_non} of the {len(slip)} slipping large hospitals slowed for patients who were not admitted",
                 x=0.02, y=0.985, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.02, 0.952, f"Large hospitals, {qname(q0)} to {qname(q1)}: each stream's own 4-hour rate, same triage category "
             "compared with itself", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


GROUP_LABEL = {"state": "Queensland", "large": "Large hospitals", "medium": "Medium hospitals", "small": "Small hospitals"}
EFFECT_LABEL = {"triage_mix": "Triage mix", "admission_share": "Admission share", "admitted": "Admitted patients slower",
                "not_admitted": "Patients not admitted slower"}
EFFECT_STYLE = {"triage_mix": (MUTED, 1.0), "admission_share": (MUTED, 0.45), "admitted": (ORANGE, 1.0),
                "not_admitted": (BLUE, 1.0)}


def chart_four_way(groups: pd.DataFrame, q0: str, q1: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    h = 0.19
    n = len(groups)
    for i, g in enumerate(groups.itertuples(index=False)):
        y = n - 1 - i
        for j, e in enumerate(EFFECTS):
            v = getattr(g, e)
            yy = y + (1.5 - j) * (h + 0.015)
            colour, alpha = EFFECT_STYLE[e]
            ax.barh(yy, v, height=h, color=colour, alpha=alpha, linewidth=0)
            ax.text(v + (0.03 if v >= 0 else -0.03), yy, sg(v, 2), va="center", ha="left" if v >= 0 else "right",
                    fontsize=8.5, color=INK)
        ax.text(-2.12, y, f"{GROUP_LABEL[g.group]}\n{g.rate_0:.1f}% to {g.rate_1:.1f}% ({sg(g.change, 1)})",
                va="center", ha="right", fontsize=9, color=INK)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks([])
    ax.set_xlim(-2.1, 0.6)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlabel("Contribution to the change in stays within 4 hours, percentage points")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=EFFECT_STYLE[e][0], alpha=EFFECT_STYLE[e][1]) for e in EFFECTS]
    fig.legend(handles, [EFFECT_LABEL[e] for e in EFFECTS], loc="upper left", bbox_to_anchor=(0.012, 0.905), ncol=4,
               frameon=False, fontsize=9, labelcolor=INK_2)
    fig.suptitle("The fall is in both streams at large hospitals, and mostly in the mix at medium ones",
                 x=0.02, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.02, 0.915, f"Change in stays within 4 hours split four ways, {qname(q0)} to {qname(q1)}", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


def chart_walkouts(by_q: pd.DataFrame, path: Path) -> None:
    quarters = sorted(by_q["quarter"].unique())
    x = range(len(quarters))
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    look = {"large": (ORANGE, "-"), "medium": (BLUE, "-"), "small": (MUTED, "--")}
    ends = {}
    for g in SC.GROUPS:
        s = by_q[by_q["peer_group"] == g].set_index("quarter").reindex(quarters)["did_not_wait_pct"]
        colour, ls = look[g]
        ax.plot(x, s.values, color=colour, linestyle=ls, linewidth=2)
        ends[g] = float(s.iloc[-1])
    # end labels, pushed apart where two lines finish close together
    y_label, last = {}, None
    for g in sorted(ends, key=ends.get):
        y_label[g] = ends[g] if last is None else max(ends[g], last + 0.3)
        last = y_label[g]
    for g in SC.GROUPS:
        ax.text(len(quarters) - 0.85, y_label[g], f"{BAND[g]} {ends[g]:.1f}%", va="center", fontsize=9, color=look[g][0])
    ax.set_xticks(list(x), [B.qshort(q) for q in quarters], fontsize=8.5)
    ax.set_xlim(-0.3, len(quarters) + 1.2)
    ax.set_ylim(0, 6)
    ax.set_ylabel("% of attendances")
    B.style(ax, "Did-not-wait is lower than two years ago, but it is not a steady fall",
            "Patients who did not wait to be seen, by hospital size (the same 104 hospitals in every quarter)")
    fig.tight_layout()
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


# ------------------------------------------------------------------ report
def flag(v: float, bar: float, nd: int = 1) -> str:
    """A signed effect, in bold when it is outside its chance bar."""
    text = sg(v, nd)
    return f"**{text}**" if abs(v) > bar else text


def stream_rows(k: pd.DataFrame) -> list[list[str]]:
    rows = []
    for x in k.itertuples(index=False):
        adm_rates = (f"{x.admitted_rate_0:.1f}% to {x.admitted_rate_1:.1f}%"
                     if pd.notna(x.admitted_rate_0) and pd.notna(x.admitted_rate_1) else "n/a")
        rows.append([x.facility_name, x.trend, sg(x.change, 1), sg(x.triage_mix, 1), sg(x.admission_share, 1),
                     flag(x.admitted, x.admitted_bar), flag(x.not_admitted, x.not_admitted_bar), x.pattern,
                     adm_rates, f"{x.not_admitted_rate_0:.1f}% to {x.not_admitted_rate_1:.1f}%"])
    return rows


STREAM_HEAD = ["Hospital", "4-hour trend (Part 3)", "Change (points)", "Triage mix", "Admission share",
               "Admitted stream", "Not-admitted stream", "Slipping in", "Admitted: within 4 h",
               "Not admitted: within 4 h (implied)"]


def names(frame: pd.DataFrame) -> str:
    """'A', 'A and B' or 'A, B and C'."""
    x = list(frame["facility_name"])
    return x[0] if len(x) == 1 else ", ".join(x[:-1]) + " and " + x[-1]


def build_report(r: dict) -> tuple[str, dict[str, pd.DataFrame]]:
    q0, q1 = r["q0"], r["q1"]
    k, groups = r["k"], r["groups"].set_index("group")
    st = groups.loc["state"]
    L: list[str] = []
    A = L.append

    A("# Front door versus back door: where in the ED did the 4-hour rate fall?\n")
    A("*Generated by `scripts/doors_report.py` from the snapshot in `data/`. Do not edit by hand.*\n")
    A("Part 3 says which hospitals' rate of emergency department (ED) stays within 4 hours slipped. This part asks where "
      "in the ED the slip sits: at the **front door** (waiting to be seen), among patients who leave for a **hospital "
      "bed**, or among patients who are **not admitted** and mostly go home. The three point to different fixes: "
      "triage and first assessment, inpatient beds and discharge, or the ED's own tests, decisions and discharges.\n")

    A("## 1. Method\n")
    A("- **Two streams.** Every triage category is cut into patients who were admitted and patients who were not. The "
      "admitted stream's 4-hour rate is published. The not-admitted stream's rate is not: it is the rate implied by the "
      "published stay rate, admitted share and admitted 4-hour rate, and is labelled *implied* throughout.")
    A(f"- **A four-way split.** The change in a hospital's 4-hour rate from {qname(q0)} to {qname(q1)} is split exactly "
      "into: **triage mix** (Part 2's mix effect, unchanged), **admission share** (within a triage category, a different "
      "share of patients was admitted), the **admitted stream** (admitted patients' own rate moved) and the "
      "**not-admitted stream** (everyone else's own rate moved). The last three add up to Part 2's within-category "
      "effect. Stream effects are in points of the hospital's all-patients rate, so the two can be compared directly.")
    A("- **Chance bar.** As in Part 3: a stream is **slipping** or **improving** only if its effect is outside ±2.58 "
      "standard errors, treating patients as independent. The bar is a floor, not a full margin of error. Figures in "
      "**bold** are outside it.")
    flagged_non = k[k["not_admitted_trend"] != "no clear change"]
    weak = flagged_non[~flagged_non["not_admitted_robust"]]
    flagged_adm = k[k["admitted_trend"] != "no clear change"]
    weak_adm = flagged_adm[~flagged_adm["admitted_robust"]]
    big = k[k["peer_group"] == "large"]
    assert len(weak) < 0.25 * len(flagged_non) and big["not_admitted_rounding"].max() < 0.5
    A(f"- **Rounding.** The implied rate also carries the rounding of three published percentages, which the chance bar "
      f"does not include. If every one were off by 0.05 points in the worst direction, a large hospital's not-admitted "
      f"effect would move by {big['not_admitted_rounding'].median():.2f} points at the median (at most "
      f"{big['not_admitted_rounding'].max():.2f}). Adding that worst case to the bar, {len(flagged_non) - len(weak)} of the "
      f"{len(flagged_non)} not-admitted verdicts stand; the {len(weak)} that would not are {names(weak)}. "
      + (f"All {len(flagged_adm)} admitted verdicts stand." if weak_adm.empty else
         f"{len(flagged_adm) - len(weak_adm)} of the {len(flagged_adm)} admitted verdicts stand (not {names(weak_adm)})."))
    A("- **Front door.** Patients seen within the recommended time (Part 3's verdict), the median wait, and patients who "
      "**did not wait** to be seen, as a share of attendances. Did-not-wait is scored like the 4-hour rate: its "
      "within-category change against a chance bar, where *rising* is the bad direction.")
    assert len(r["new"]) == 1
    A(f"- **Coverage.** The {len(k)} hospitals that reported in both quarters, in Part 3's three size groups. "
      f"{r['new'][0]}, which first reports in {qname(q1)}, is left out.")
    assert r["max_gap"] < 1e-9
    A("- **Check.** For every hospital the ten cells (five triage categories, two streams) add back to the same 4-hour "
      "rate as the five categories do, and the four effects add up to the change with nothing left over.\n")

    A("## 2. Queensland: both streams are slower\n")
    rows = [[GROUP_LABEL[g], f"{x.rate_0:.1f}%", f"{x.rate_1:.1f}%", sg(x.change), sg(x.triage_mix), sg(x.admission_share),
             sg(x.admitted), sg(x.not_admitted)] for g, x in groups.iterrows()]
    A(table(["", f"Within 4 h, {qname(q0)}", f"Within 4 h, {qname(q1)}", "Change (points)", "Triage mix", "Admission share",
             "Admitted stream", "Not-admitted stream"], rows) + "\n")
    within = st.admission_share + st.admitted + st.not_admitted
    adm_part, non_part = 100 * st.admitted / within, 100 * st.not_admitted / within
    assert st.admitted < 0 and st.not_admitted < 0 and abs(st.admission_share) < 0.1
    A(f"- Statewide the rate fell {abs(st.change):.2f} points. Triage mix is {abs(st.triage_mix):.2f} of that (Part 2). Of "
      f"the remaining {abs(within):.2f}, admitted patients leaving later account for {abs(st.admitted):.2f} points "
      f"({adm_part:.0f}%) and patients who were not admitted for {abs(st.not_admitted):.2f} ({non_part:.0f}%). The "
      f"admission share within categories barely moved ({sg(st.admission_share)}).")
    A(f"- **Admitted patients carry more than their share of the fall, but not most of it.** They are "
      f"{st.admitted_share_1:.1f}% of attendances and {adm_part:.0f}% of the within-category fall. Their own 4-hour rate "
      f"went from {st.admitted_rate_0:.1f}% to {st.admitted_rate_1:.1f}%; the implied rate for everyone else went from "
      f"{st.not_admitted_rate_0:.1f}% to {st.not_admitted_rate_1:.1f}%.")
    p2 = r["part2_within"]
    assert p2["not admitted"] < st.not_admitted < 0 and abs(p2["admitted"] - st.admitted) < 0.1
    A(f"- This refines Part 2, which split the same fall into admitted and not admitted without holding triage fixed and "
      f"put {abs(p2['not admitted']):.2f} points on patients who were not admitted and {abs(p2['admitted']):.2f} on admitted "
      f"patients. With triage held fixed the not-admitted part is {abs(st.not_admitted):.2f} points: the rest of the "
      "earlier figure was a more urgent triage mix among patients who were not admitted.")
    lg, md, sm = groups.loc["large"], groups.loc["medium"], groups.loc["small"]
    assert lg.not_admitted < lg.admitted < 0 and abs(md.not_admitted) < 0.2 and md.admitted < -0.3
    assert abs(md.triage_mix) > 0.7 * abs(md.change)
    A(f"- **The size groups differ.** At the large hospitals both streams fell and the not-admitted stream fell more "
      f"({sg(lg.not_admitted)} against {sg(lg.admitted)}). At the medium hospitals, pooled, the not-admitted stream did not "
      f"move ({sg(md.not_admitted)}; section 4 shows hospitals moving both ways); what fell there is triage mix "
      f"({sg(md.triage_mix)}) and the admitted stream ({sg(md.admitted)}). At the small hospitals the effects are small ({sg(sm.admitted)} and {sg(sm.not_admitted)}).\n")
    A("![Four-way split by peer group](charts/11_four_way_split.png)\n")

    A("## 3. Large hospitals\n")
    kl = k[k["peer_group"] == "large"]
    A(table(STREAM_HEAD, stream_rows(kl)) + "\n")
    slip = kl[kl["trend"] == "slipping"]
    pc = slip["pattern"].value_counts()
    n_both, n_non, n_adm = int(pc.get("both streams", 0)), int(pc.get("not admitted only", 0)), int(pc.get("admitted only", 0))
    assert n_both + n_non + n_adm == len(slip)
    non_slip = slip[slip["not_admitted_trend"] == "slipping"]
    adm_only = slip[slip["pattern"] == "admitted only"]
    non_only = slip[slip["pattern"] == "not admitted only"]
    A(f"- **Of the {len(slip)} slipping large hospitals, {n_both} are slipping in both streams, {n_non} only among patients "
      f"who were not admitted ({names(non_only)}) and {n_adm} only among admitted patients ({names(adm_only)}).** So the "
      f"not-admitted stream is slipping at {len(non_slip)} of the {len(slip)}.")
    bigger_non = int((slip["not_admitted"] < slip["admitted"]).sum())
    A(f"- At {bigger_non} of the {len(slip)} the not-admitted stream is the larger part of the fall. The largest admitted "
      f"falls are at {names(slip.sort_values('admitted', kind='stable').head(3))}; the largest not-admitted falls are at "
      f"{names(slip.sort_values('not_admitted', kind='stable').head(3))}.")
    imp = kl[kl["trend"] == "improving"]
    assert (imp["not_admitted_trend"] == "improving").all() and (imp["not_admitted"] > imp["admitted"]).all()
    A(f"- **The {len(imp)} improving large hospitals all improved among patients who were not admitted**, and at each of "
      f"them that stream is the larger part of the gain. {int((imp['admitted_trend'] == 'improving').sum())} also improved "
      "among admitted patients.")
    corr = r["stream_corr"]
    assert corr > 0.3
    A(f"- **The two streams move together** (correlation {corr:.2f} across the {len(kl)} large hospitals). That fits one "
      "cause slowing both, such as admitted patients waiting in ED cubicles for a bed while new patients queue behind "
      "them, as well as it fits two separate problems. Quarterly totals cannot tell these apart.\n")
    A("![Streams at the large hospitals](charts/10_large_hospital_streams.png)\n")

    A("## 4. Medium hospitals\n")
    km = k[k["peer_group"] == "medium"]
    A(table(STREAM_HEAD, stream_rows(km)) + "\n")
    slip_m = km[km["trend"] == "slipping"]
    pm = slip_m["pattern"].value_counts()
    assert int(pm.get("both streams", 0)) + int(pm.get("not admitted only", 0)) == len(slip_m)
    quiet = km[(km["trend"] == "no clear change") & (km["pattern"] != "neither stream")]
    A(f"- Of the {len(slip_m)} slipping medium hospitals, {int(pm.get('both streams', 0))} are slipping in both streams and "
      f"{int(pm.get('not admitted only', 0))} only among patients who were not admitted "
      f"({names(slip_m[slip_m['pattern'] == 'not admitted only'])}).")
    opp = km[((km["admitted_trend"] == "improving") & (km["not_admitted_trend"] == "slipping"))
             | ((km["admitted_trend"] == "slipping") & (km["not_admitted_trend"] == "improving"))]
    A(f"- **A flat headline can hide a stream.** {len(quiet)} hospitals show no clear change overall yet are slipping in "
      f"one stream: {names(quiet)}." + (f" At {names(opp)} the two streams moved in opposite directions." if len(opp) else ""))
    few = km[km["admitted_share_1"] < 10]
    A(f"- Medium hospitals admit fewer patients (pooled, {md.admitted_share_1:.1f}% of attendances against "
      f"{lg.admitted_share_1:.1f}% at large hospitals), so the admitted stream's rate rests on small numbers and swings "
      f"widely: at {len(few)} of the {len(km)} fewer than 10% of patients are admitted. Read the admitted rates in the last "
      "columns with the chance bar in mind.\n")

    A("## 5. Small hospitals, and the count for all three groups\n")
    ks = k[k["peer_group"] == "small"]
    ps = ks["pattern"].value_counts()
    rows = [[BAND[g]] + [str(int((k.loc[k["peer_group"] == g, "pattern"] == p).sum())) for p in D.PATTERNS]
            + [str(int((k["peer_group"] == g).sum()))] for g in SC.GROUPS]
    rows.append(["**All**"] + [f"**{int((k['pattern'] == p).sum())}**" for p in D.PATTERNS] + [f"**{len(k)}**"])
    A(table(["Peer group", "Slipping in both streams", "Admitted only", "Not admitted only", "Neither", "Hospitals"], rows) + "\n")
    A(f"- {int(ps.get('neither stream', 0))} of the {len(ks)} small hospitals are slipping in neither stream. Pooled, "
      f"{sm.admitted_share_1:.1f}% of their patients are admitted, so the admitted stream is too thin to score hospital "
      "by hospital; the rows are in `doors_hospitals.csv`.")
    A(f"- Median chance bars for the stream effects: ±{kl['admitted_bar'].median():.1f} (admitted) and "
      f"±{kl['not_admitted_bar'].median():.1f} (not admitted) points at large hospitals, "
      f"±{ks['admitted_bar'].median():.1f} and ±{ks['not_admitted_bar'].median():.1f} at small ones.\n")

    A("## 6. The front door\n")
    rows = []
    for g, x in groups.iterrows():
        rows.append([GROUP_LABEL[g], f"{x.dnw_rate_0:.2f}%", f"{x.dnw_rate_1:.2f}%", sg(x.dnw_within),
                     f"{x.left_rate_0:.2f}%", f"{x.left_rate_1:.2f}%", sg(x.left_within)])
    A(table(["", f"Did not wait, {qname(q0)}", f"Did not wait, {qname(q1)}", "Within-category change (points)",
             f"Left after treatment started, {qname(q0)}", f"Left after treatment started, {qname(q1)}",
             "Within-category change (points)"], rows) + "\n")
    assert st.dnw_within < 0 and md.dnw_within < lg.dnw_within < 0 and st.left_within > 0
    A(f"- **Fewer patients give up before being seen than two years earlier.** Statewide the did-not-wait rate fell from {st.dnw_rate_0:.2f}% to "
      f"{st.dnw_rate_1:.2f}% of attendances, and it fell within triage categories ({sg(st.dnw_within)} points), so it is "
      f"not only a mix effect. The fall is largest at the medium hospitals ({md.dnw_rate_0:.2f}% to {md.dnw_rate_1:.2f}%).")
    A(f"- Patients who left after treatment had started moved the other way, slightly: {st.left_rate_0:.2f}% to "
      f"{st.left_rate_1:.2f}% statewide. The source does not say why patients leave, so this is noted, not interpreted.\n")
    A("![Did not wait by peer group](charts/12_did_not_wait.png)\n")
    w = r["walkouts"]
    same = [q for q in r["quarters"] if q[5:] == q1[5:]]
    piv = w.pivot(index="peer_group", columns="quarter", values="did_not_wait_pct")
    tot = w.groupby("quarter")[["attendances", "did_not_wait"]].sum()
    all_rate = 100 * tot["did_not_wait"] / tot["attendances"]
    rows = [[f"All {len(k)} hospitals"] + [f"{all_rate[q]:.2f}%" for q in same]]
    rows += [[GROUP_LABEL[g]] + [f"{piv.loc[g, q]:.2f}%" for q in same] for g in SC.GROUPS]
    A("The same quarter in each year, so that the seasons do not get in the way:\n")
    A(table(["Did not wait"] + [qname(q) for q in same], rows) + "\n")
    prev = r["quarters"][-2]
    m_peak = piv.loc["medium"].idxmax()
    assert all_rate[same[-1]] < all_rate[same[-2]] < all_rate[q0] and len(same) == 4
    assert same[1] == q0 and all_rate[q0] > all_rate[same[0]]
    assert (piv.loc["medium", prev] - piv.loc["medium", q1]) > 0.5 * (piv.loc["medium", q0] - piv.loc["medium", q1])
    A(f"- Across all hospitals the rate has fallen in each of the last two {qname(q1)[:7]} quarters, but {qname(q0)} was "
      f"higher than the year before it, so the two-year fall starts from a high point.")
    A(f"- **The medium hospitals' fall is recent.** Their rate peaked at {piv.loc['medium', m_peak]:.2f}% in "
      f"{qname(m_peak)} and was still {piv.loc['medium', prev]:.2f}% in {qname(prev)}; most of the fall to "
      f"{piv.loc['medium', q1]:.2f}% happened in the latest quarter. One quarter is not a trend.\n")
    ct = pd.crosstab(k["trend"], k["dnw_trend"]).reindex(index=TRENDS, columns=WALK, fill_value=0)
    rows = [[i.capitalize()] + [str(int(v)) for v in ct.loc[i]] + [str(int(ct.loc[i].sum()))] for i in ct.index]
    rows.append(["**All**"] + [f"**{int(ct[c].sum())}**" for c in WALK] + [f"**{len(k)}**"])
    A("Each hospital's did-not-wait rate, scored against its own chance bar, next to Part 3's 4-hour verdict:\n")
    A(table(["4-hour stays ↓ / did not wait →", "Rising", "No clear change", "Falling", "All"], rows) + "\n")
    s_r, s_f = int(ct.loc["slipping", "rising"]), int(ct.loc["slipping", "falling"])
    i_r, i_f = int(ct.loc["improving", "rising"]), int(ct.loc["improving", "falling"])
    n_slip, n_imp = int(ct.loc["slipping"].sum()), int(ct.loc["improving"].sum())
    assert i_r == 0 and s_r > s_f
    A(f"- Did-not-wait is rising at {int(ct['rising'].sum())} hospitals and falling at {int(ct['falling'].sum())}. Of the "
      f"{n_slip} hospitals slipping on 4-hour stays, {s_r} have a rising did-not-wait rate and {s_f} a falling one; for "
      f"most ({int(ct.loc['slipping', 'no clear change'])}) it shows no clear change.")
    A(f"- Of the {n_imp} hospitals improving on 4-hour stays, {i_f} have a falling did-not-wait rate and none a rising one.")
    rising_l = kl[kl["dnw_trend"] == "rising"]
    A(f"- The large hospitals where it is rising: {names(rising_l)}. "
      + ("All of them are also slipping on 4-hour stays." if (rising_l["trend"] == "slipping").all() else
         f"{int((rising_l['trend'] == 'slipping').sum())} of those {len(rising_l)} are also slipping on 4-hour stays."))
    faster, slower = int((k["median_wait_1"] < k["median_wait_0"]).sum()), int((k["median_wait_1"] > k["median_wait_0"]).sum())
    fl, sl = int((kl["median_wait_1"] < kl["median_wait_0"]).sum()), int((kl["median_wait_1"] > kl["median_wait_0"]).sum())
    A(f"- The published median wait is shorter at {faster} of the {len(k)} hospitals and longer at {slower}; among the "
      f"{len(kl)} large hospitals it is shorter at {fl} and longer at {sl}. A median has no chance bar here, so these are "
      "counts, not verdicts.\n")

    A("### A caution on waits recorded as zero\n")
    zero0, zero1 = k[k["median_wait_0"] <= ZERO_WAIT], k[k["median_wait_1"] <= ZERO_WAIT]
    step = k[k["wait_step"]]
    seen_slip = k[k["seen_trend"] == "slipping"]
    step_slip = step[step["seen_trend"] == "slipping"]
    zc = zero0["peer_group"].value_counts()
    assert len(step) >= 5 and int(zc.get("large", 0)) == 0
    A(f"- In {qname(q0)}, {len(zero0)} hospitals ({int(zc.get('small', 0))} small, {int(zc.get('medium', 0))} medium) "
      f"published a median wait of 0 or 1 minute: at least half their patients are recorded as seen within a minute of "
      f"arriving. By {qname(q1)} that is {len(zero1)} hospitals.")
    A(f"- At {len(step)} of them the median had risen to {STEP_WAIT} minutes or more by {qname(q1)}: {names(step)}. "
      "A jump from zero is what a change in how the start of treatment is recorded would look like, though the data "
      "cannot confirm that.")
    A(f"- It matters for the front-door verdict: {len(step_slip)} of the {len(seen_slip)} hospitals that Part 3 marks as "
      f"slipping on patients seen on time are in this group ({names(step_slip)}). Their slip may be measurement, not "
      "service. They are marked `wait_step` in `doors_hospitals.csv`.\n")

    A("## 7. The two short lists from Part 3\n")
    pri = k[(k["level"] == "below peers") & (k["trend"] == "slipping")]
    head = ["Hospital", "Peer group", "Change (points)", "Admitted stream", "Not-admitted stream", "Slipping in",
            "Seen on time", "Did not wait", f"Median wait, {qname(q0)}", f"Median wait, {qname(q1)}"]

    def short_rows(frame: pd.DataFrame) -> list[list[str]]:
        return [[x.facility_name + (" †" if x.wait_step else ""), BAND[x.peer_group], sg(x.change, 1),
                 flag(x.admitted, x.admitted_bar), flag(x.not_admitted, x.not_admitted_bar), x.pattern, x.seen_trend,
                 x.dnw_trend, f"{x.median_wait_0:.0f} min", f"{x.median_wait_1:.0f} min"] for x in frame.itertuples(index=False)]

    A(f"### Below peers and slipping: {len(pri)} hospitals\n")
    A(table(head, short_rows(pri)) + "\n")
    pp = pri["pattern"].value_counts()
    A(f"- {int(pp.get('both streams', 0))} are slipping in both streams, {int(pp.get('not admitted only', 0))} only among "
      f"patients who were not admitted, {int(pp.get('admitted only', 0))} only among admitted patients and "
      f"{int(pp.get('neither stream', 0))} in neither.")
    pri_non = pri[pri["not_admitted_trend"] == "slipping"]
    A(f"- The not-admitted stream is slipping at {len(pri_non)} of the {len(pri)}. None of these hospitals has a problem "
      "confined to admitted patients." if int(pp.get("admitted only", 0)) == 0 else
      f"- The not-admitted stream is slipping at {len(pri_non)} of the {len(pri)}.")
    if pri["wait_step"].any():
        A(f"- † Median wait rose from {ZERO_WAIT} minute or less to {STEP_WAIT} or more: see the caution in section 6.")
    A("")
    odd = k[(k["trend"] == "slipping") & (k["seen_trend"] == "improving")]
    A(f"### Slipping on 4-hour stays while seen-on-time improves: {len(odd)} hospitals\n")
    A(table(head, short_rows(odd)) + "\n")
    op = odd["pattern"].value_counts()
    shorter = int((odd["median_wait_1"] < odd["median_wait_0"]).sum())
    odd_non = int((odd["not_admitted_trend"] == "slipping").sum())
    assert odd_non == len(odd)
    A(f"- **These {len(odd)} see patients sooner and release them later.** The median wait is shorter at {shorter} of the "
      f"{len(odd)}, and every one is slipping among patients who were not admitted ({int(op.get('both streams', 0))} in "
      "both streams). Whatever slowed them happens after the patient has been seen.")
    A(f"- Did-not-wait is falling at {int((odd['dnw_trend'] == 'falling').sum())} of them and rising at "
      f"{int((odd['dnw_trend'] == 'rising').sum())}.\n")

    A("## 8. What this means\n")
    all_slip = k[k["trend"] == "slipping"]
    as_non = int((all_slip["not_admitted_trend"] == "slipping").sum())
    as_adm = int((all_slip["admitted_trend"] == "slipping").sum())
    A(f"1. **The fall is not only a bed problem.** Of the {len(all_slip)} hospitals slipping on 4-hour stays, "
      f"{as_non} are slipping among patients who were not admitted and {as_adm} among admitted patients. A plan that "
      "only adds inpatient beds or speeds up ward discharge addresses the admitted stream; it may also help the other "
      "stream if crowding is the link, but the data cannot show that.")
    A(f"2. **It is not a front-door problem either.** Fewer patients leave without being seen than two years earlier "
      f"({st.dnw_rate_0:.2f}% to {st.dnw_rate_1:.2f}%), patients seen on time improved within category (Part 2), and "
      f"{len(odd)} hospitals improved the front door while their 4-hour rate fell. Statewide, the time is being "
      "lost between first being seen and leaving.")
    A(f"3. **Use the stream to decide who to talk to.** Where only the admitted stream slips ({names(adm_only)} among the "
      f"large hospitals), start with bed flow. Where only the not-admitted stream slips ({names(non_only)}), start "
      "inside the ED: tests, specialist reviews, decisions and discharge. Where both slip, crowding is the first thing "
      "to rule out.")
    A(f"4. **Ask the improvers about patients who go home.** All {len(imp)} improving large hospitals gained most in the "
      "not-admitted stream.")
    A(f"5. **Check how waits are recorded before judging small hospitals' front doors.** {len(zero0)} hospitals recorded a "
      f"median wait of 0 or 1 minute in {qname(q0)}, and {len(step_slip)} of the {len(seen_slip)} front-door slips are "
      "hospitals where that figure jumped.\n")

    A("## 9. Rules carried into Part 5\n")
    A("1. Report the 4-hour rate with its two streams next to it, and label the not-admitted rate as implied.")
    A("2. Keep the four effects additive: triage mix, admission share, admitted stream, not-admitted stream.")
    A("3. Carry the `wait_step` flag into any table of front-door measures.")
    A("4. Stream effects say where the time is lost, not why. Crowding can slow both streams at once.")
    A("")

    cols = ["facility_code", "facility_name", "peer_group", "attendances", "level", "trend", "change", "triage_mix",
            "admission_share", "admitted", "admitted_bar", "admitted_trend", "not_admitted", "not_admitted_bar",
            "not_admitted_trend", "pattern", "not_admitted_rounding", "not_admitted_robust", "admitted_robust", "admitted_share_0", "admitted_share_1", "admitted_rate_0", "admitted_rate_1",
            "not_admitted_rate_0", "not_admitted_rate_1", "seen_within", "seen_bar", "seen_trend", "median_wait_0",
            "median_wait_1", "wait_step", "dnw_rate_0", "dnw_rate_1", "dnw_within", "dnw_bar", "dnw_trend", "left_rate_0",
            "left_rate_1", "left_within", "left_bar", "left_trend"]
    csvs = {
        "doors_hospitals.csv": k[cols].round(4),
        "doors_peer_groups.csv": r["groups"].round(4),
        "doors_walkouts_by_quarter.csv": r["walkouts"].round(4),
    }
    return "\n".join(L), csvs


def main() -> int:
    df = load.read_snapshot(DATA / "ed_quarterly.csv")
    r = analyse(df)
    CHARTS.mkdir(parents=True, exist_ok=True)
    report, csvs = build_report(r)
    (RESULTS / "FRONT_VS_BACK_DOOR.md").write_text(report, encoding="utf-8")
    for name, frame in csvs.items():
        frame.to_csv(RESULTS / name, index=False, lineterminator="\n", float_format="%.10g")
    chart_streams(r["k"], r["q0"], r["q1"], CHARTS / "10_large_hospital_streams.png")
    chart_four_way(r["groups"], r["q0"], r["q1"], CHARTS / "11_four_way_split.png")
    chart_walkouts(r["walkouts"], CHARTS / "12_did_not_wait.png")
    print(f"wrote results/FRONT_VS_BACK_DOOR.md, {len(csvs)} CSVs, 3 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
