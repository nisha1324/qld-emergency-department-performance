"""Part 3: hospital scorecard. Writes results/HOSPITAL_SCORECARD.md, CSVs and charts 07-09.

    python scripts/scorecard_report.py

Reads only the committed snapshot in data/ (no download needed).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from edperf import load, scorecard as SC  # noqa: E402
from scripts import mix_report as R2, profile_source as B  # noqa: E402  (shared palette, labels and chart style)

DATA, RESULTS, CHARTS = B.DATA, B.RESULTS, B.CHARTS
BLUE, ORANGE, INK, INK_2, MUTED, GRID = B.BLUE, B.ORANGE, B.INK, B.INK_2, B.MUTED, B.GRID
qname, sg, table = B.qname, R2.sg, R2.table
STAY, SEEN = R2.STAY, R2.SEEN
COLOUR = {"slipping": ORANGE, "improving": BLUE, "no clear change": MUTED, "new": MUTED}
TRENDS = ["slipping", "no clear change", "improving"]
BAND = {"large": "Large", "medium": "Medium", "small": "Small"}


def band_text(name: str) -> str:
    lo, hi = next((lo, hi) for n, lo, hi in SC.SIZE_BANDS if n == name)
    if hi is None:
        return f"{lo:,} or more"
    return f"under {hi:,}" if lo == 0 else f"{lo:,} to {hi - 1:,}"


def analyse(df: pd.DataFrame) -> dict:
    """Everything the report, CSVs and charts are built from."""
    p = R2.periods(df)
    q0, q1 = p["q0"], p["q1"]
    mids = [q for q in p["quarters"] if q[5:] == q1[5:] and q0 < q < q1]
    assert len(mids) == 1, "the two-year comparison should have exactly one quarter in the middle"
    stay = SC.scorecard(df, STAY, q0, q1, mids[0])
    seen = SC.scorecard(df, SEEN, q0, q1, mids[0])
    card = stay.merge(
        seen[["facility_code", "within", "bar", "trend"]].rename(
            columns={"within": "seen_within", "bar": "seen_bar", "trend": "seen_trend"}),
        on="facility_code", validate="one_to_one")
    state = df[df["is_state_total"] & (df["triage"] == "ALL") & (df["quarter"] == q1)]
    return {**p, "q_mid": mids[0], "card": card, "groups": SC.group_summary(df, stay, STAY, q0, q1),
            "state_rate": float(state[STAY].iloc[0])}


# ------------------------------------------------------------------ charts
def _legend_handles():
    return [plt.Line2D([], [], marker="o", linestyle="", color=COLOUR[t], markersize=6) for t in TRENDS]


def chart_large(card: pd.DataFrame, q0: str, q1: str, path: Path) -> None:
    k = card[card["peer_group"] == "large"].reset_index(drop=True)
    n = len(k)
    fig, ax = plt.subplots(figsize=(8.5, 8.2))
    for i, row in enumerate(k.itertuples(index=False)):
        y = n - 1 - i
        c = COLOUR[row.trend]
        ax.plot([row.within - row.bar, row.within + row.bar], [y, y], color=c, linewidth=2, solid_capstyle="butt")
        ax.plot(row.within, y, "o", color=c, markersize=6)
        ax.text(11.6, y, f"{row.published_0:.1f}% to {row.published_1:.1f}%", va="center", fontsize=8.5, color=INK)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks(range(n), list(k["facility_name"])[::-1], fontsize=9)
    ax.set_xlim(-11, 11)
    ax.set_ylim(-0.7, n + 0.5)
    ax.text(11.6, n - 0.15, "Stays within 4 h", fontsize=8.5, color=INK_2)
    ax.set_xlabel("Within-category change in stays within 4 hours, percentage points (line = chance bar)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    counts = k["trend"].value_counts()
    ax.legend(_legend_handles(), [f"{t.capitalize()} ({int(counts.get(t, 0))})" for t in TRENDS], loc="lower left",
              frameon=False, fontsize=9, labelcolor=INK_2)
    fig.suptitle(f"{int(counts.get('slipping', 0))} of the {n} large hospitals slipped by more than chance",
                 x=0.02, y=0.985, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.02, 0.948, f"Hospitals with {band_text('large')} attendances a quarter, {qname(q0)} to {qname(q1)}, "
             "same triage category compared with itself", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 0.86, 0.945))
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


# hospitals named on the level-against-trend chart: (dx, dy, ha) offsets in points
def chart_level_trend(card: pd.DataFrame, labels: dict[int, tuple[float, float, str]], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 4.9), sharey=True)
    for ax, g in zip(axes, ("large", "medium")):
        k = card[(card["peer_group"] == g) & card["within"].notna()]
        for t in TRENDS:
            part = k[k["trend"] == t]
            ax.scatter(part["vs_peers"], part["within"], s=30, color=COLOUR[t], linewidth=0, zorder=3)
        ax.axhline(0, color=MUTED, linewidth=1)
        ax.axvline(0, color=MUTED, linewidth=1)
        for row in k.itertuples(index=False):
            if row.facility_code in labels:
                dx, dy, ha = labels[row.facility_code]
                ax.annotate(row.facility_name, (row.vs_peers, row.within), xytext=(dx, dy), textcoords="offset points",
                            ha=ha, va="center", fontsize=8, color=INK)
        ax.set_xlim(-27, 27)
        ax.set_ylim(-12, 13)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.set_title(f"{BAND[g]} hospitals ({len(k)})", loc="left", fontsize=10, color=INK_2)
        ax.text(-26, -11.5, "lower than peers,\nand slipping", fontsize=8, color=INK_2, va="bottom")
        ax.text(26, 12.5, "higher than peers,\nand improving", fontsize=8, color=INK_2, va="top", ha="right")
    axes[0].set_ylabel("Within-category change, points")
    fig.supxlabel("Same-mix 4-hour rate, points above or below the peer group's median", fontsize=10, color=INK_2)
    fig.legend(_legend_handles(), [t.capitalize() for t in TRENDS], loc="upper left", bbox_to_anchor=(0.012, 0.9),
               ncol=3, frameon=False, fontsize=9, labelcolor=INK_2)
    fig.suptitle("Where a hospital stands and which way it is moving are different questions",
                 x=0.02, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.02, 0.905, "Each dot is a hospital: level against peers of the same size (across) and two-year change (up)",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


def chart_counts(groups: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 3.3))
    col = {"slipping": "slipping", "no clear change": "no_clear_change", "improving": "improving"}
    for i, g in enumerate(groups.itertuples(index=False)):
        y = len(groups) - 1 - i
        total = g.with_both_quarters
        left = 0.0
        for t in TRENDS:
            v = getattr(g, col[t])
            w = 100 * v / total
            ax.barh(y, w, left=left, height=0.56, color=COLOUR[t], edgecolor=B.SURFACE, linewidth=2)
            if v:
                ax.text(left + w / 2, y, str(v), ha="center", va="center", fontsize=9.5, fontweight="bold",
                        color="white" if t != "no clear change" else INK)
            left += w
        ax.text(-1.5, y, f"{BAND[g.peer_group]}\n{band_text(g.peer_group)}", ha="right", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, len(groups) - 0.4)
    ax.set_yticks([])
    ax.set_xlabel("% of the group's hospitals with both quarters (number of hospitals on each bar)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOUR[t]) for t in TRENDS]
    fig.legend(handles, [t.capitalize() for t in TRENDS], loc="upper left", bbox_to_anchor=(0.012, 0.86), ncol=3,
               frameon=False, fontsize=9, labelcolor=INK_2)
    fig.suptitle("Most large hospitals slipped; most small hospitals show no clear change",
                 x=0.02, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.02, 0.87, "Hospitals by attendances a quarter: within-category change in stays within 4 hours, against the chance bar",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0.1, 0, 1, 0.82))
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


# hospitals labelled on chart 08 (checked by eye for overlaps)
CHART_LABELS = {
    22: (6, -8, "left"),      # Queen Elizabeth II
    11: (0, 10, "center"),    # Princess Alexandra
    202: (-4, -10, "right"),  # Queensland Children's
    30: (-6, 7, "right"),     # Caboolture
    4: (7, -4, "left"),       # Prince Charles
    49: (7, 0, "left"),       # Nambour
    136: (7, 0, "left"),      # Gladstone
    211: (-7, 0, "right"),    # Atherton
    70: (7, 5, "left"),       # Kingaroy
    43: (-7, 0, "right"),     # Caloundra
    92: (7, 0, "left"),       # Dalby
}


# ------------------------------------------------------------------ report
def hospital_rows(k: pd.DataFrame) -> list[list[str]]:
    rows = []
    for x in k.itertuples(index=False):
        new = pd.isna(x.within)
        rows.append([
            x.facility_name, f"{x.attendances:,}", "n/a" if new else f"{x.published_0:.1f}%", f"{x.published_1:.1f}%",
            f"{x.standardised:.1f}%", sg(x.vs_peers, 1), x.level,
            "n/a" if new else sg(x.within, 1), "n/a" if new else f"±{x.bar:.1f}", x.trend,
            "n/a" if new else sg(x.seen_within, 1), x.seen_trend,
        ])
    return rows


def build_report(r: dict) -> tuple[str, dict[str, pd.DataFrame]]:
    q0, q1, q_mid = r["q0"], r["q1"], r["q_mid"]
    card, groups = r["card"], r["groups"].set_index("peer_group")
    both = card[card["within"].notna()]
    new = card[card["within"].isna()]
    L: list[str] = []
    A = L.append
    head = ["Hospital", f"Attendances, {qname(q1)}", f"Within 4 h, {qname(q0)}", f"Within 4 h, {qname(q1)}",
            "Same-mix rate", "Against peer median (points)", "Level", "Within-category change (points)", "Chance bar",
            "Trend", "Seen on time: within-category change", "Seen on time: trend"]

    A("# Hospital scorecard: who is slipping and who is improving on 4-hour stays\n")
    A("*Generated by `scripts/scorecard_report.py` from the snapshot in `data/`. Do not edit by hand.*\n")
    A("Part 2 showed that the state's fall in emergency department (ED) stays within 4 hours is mostly patients in the same "
      "triage category taking longer, and that the large hospitals differ widely. This part scores every hospital on two "
      "separate questions, each against hospitals of a similar size: where does it stand, and which way is it moving?\n")

    A("## 1. Method\n")
    A(f"- **Peer groups by size.** Hospitals are grouped by attendances in {qname(q1)}: large ({band_text('large')}), medium "
      f"({band_text('medium')}) and small ({band_text('small')}). These are working groups for this analysis, not Queensland "
      "Health's official peer groups.")
    A("- **Level: the same-mix rate.** A hospital with more urgent patients has a lower 4-hour rate for that reason alone. "
      "So each hospital's five category rates are weighted by its peer group's pooled triage mix, not its own. A hospital "
      "is **below peers** if that same-mix rate is in the lowest quarter of its group (and further below the group median "
      "than chance allows), **above peers** if it is in the highest quarter, and **in line** otherwise.")
    A(f"- **Trend: the within-category change**, {qname(q0)} to {qname(q1)} (Part 2's rule: the same quarter two years "
      "apart, both published to one decimal place). It is the change in the 4-hour rate with the effect of a changing "
      "triage mix taken out.")
    A(f"- **Chance bar.** A rate built from 300 patients moves from quarter to quarter by luck alone. Each change is compared "
      f"with ±{SC.Z} standard errors, treating every patient as an independent yes/no outcome. A hospital is **slipping** or "
      "**improving** only if its change is outside that bar; otherwise it is **no clear change**. With about 100 hospitals, "
      "a bar this wide should flag about one by luck. Stays in a crowded ED are not independent, so the true noise is "
      "probably larger than the bar: treat a flag as \"worth a look\", not as proof.")
    A("- **No official targets are applied.** Queensland Health's targets could not be confirmed from a primary source on "
      "the machine this was built on (its performance and budget sites refuse automated requests), so hospitals are scored "
      "against the median of their peer group instead. A peer median is a description of what similar hospitals do, not a "
      "standard of care.\n")

    A("## 2. The three peer groups\n")
    rows = []
    for g in SC.GROUPS:
        x = groups.loc[g]
        rows.append([f"{BAND[g]} ({band_text(g)})", str(int(x["hospitals"])), f"{x['attendance_share']:.1f}%",
                     f"{x['pooled_rate_1']:.1f}%", f"{x['median_standardised']:.1f}%",
                     f"{x['min_standardised']:.1f}% to {x['max_standardised']:.1f}%",
                     sg(x["pooled_change"]), sg(x["pooled_mix"]), sg(x["pooled_within"])])
    A(table([f"Peer group (attendances in {qname(q1)})", "Hospitals", "Share of attendances", "Stays within 4 h, pooled",
             "Median same-mix rate", "Range of same-mix rates", "Pooled change (points)", "Mix", "Within category"], rows) + "\n")
    lg, md, sm = groups.loc["large"], groups.loc["medium"], groups.loc["small"]
    assert lg["median_standardised"] < md["median_standardised"] < sm["median_standardised"]
    assert lg["pooled_within"] < sm["pooled_within"] < md["pooled_within"] < 0
    n_cov = int((card["mix_covered"] < 1).sum())
    note_new = (f" {new['facility_name'].iloc[0]} first reports in {qname(q1)}, so it has a level but no trend, and is left "
                "out of the pooled changes." if len(new) == 1 else "")
    A(f"- The groups are far apart: the median same-mix rate is {lg['median_standardised']:.1f}% for large hospitals, "
      f"{md['median_standardised']:.1f}% for medium and {sm['median_standardised']:.1f}% for small. Comparing a hospital with "
      "the state figure says more about its size than about how it is run.")
    A(f"- Even inside a group the spread is wide: {lg['max_standardised'] - lg['min_standardised']:.0f} points between the "
      "highest and lowest large hospital on the same mix.")
    A(f"- Pooled, the within-category change is {sg(lg['pooled_within'])} points at the large hospitals, "
      f"{sg(md['pooled_within'])} at the medium and {sg(sm['pooled_within'])} at the small.{note_new}")
    A(f"- {n_cov} hospitals saw nobody in at least one triage category (almost always category 1). That category is left "
      f"out of their same-mix rate; it is never more than {100 * (1 - card['mix_covered'].min()):.1f}% of the reference mix.\n")

    A("## 3. How many hospitals really moved?\n")
    rows = []
    for g in SC.GROUPS:
        x = groups.loc[g]
        k = both[both["peer_group"] == g]
        rows.append([BAND[g], str(len(k)), str(int(x["slipping"])), str(int(x["no_clear_change"])), str(int(x["improving"])),
                     f"±{k['bar'].median():.1f}"])
    tot = both["trend"].value_counts()
    rows.append(["**All**", f"**{len(both)}**", f"**{tot['slipping']}**", f"**{tot['no clear change']}**",
                 f"**{tot['improving']}**", f"±{both['bar'].median():.1f}"])
    A(table(["Peer group", "Hospitals with both quarters", "Slipping", "No clear change", "Improving",
             "Median chance bar (points)"], rows) + "\n")
    published_change = both["published_1"] - both["published_0"]
    raw_fell = int((published_change < 0).sum())
    sm_k = both[both["peer_group"] == "small"]
    sm_raw5 = sm_k[(sm_k["trend"] == "no clear change") & ((sm_k["published_1"] - sm_k["published_0"]).abs() >= 3)]
    assert tot["slipping"] > 2 * tot["improving"] and lg["slipping"] > lg["with_both_quarters"] / 2
    assert sm["no_clear_change"] > sm["with_both_quarters"] / 2
    A(f"- **{tot['slipping']} of {len(both)} hospitals slipped by more than chance and {tot['improving']} improved.** "
      f"{tot['no clear change']} show no clear change.")
    A(f"- On the published all-categories figure, {raw_fell} of {len(both)} fell. The chance bar removes most of the small hospitals "
      f"from that list: {int(sm['no_clear_change'])} of {int(sm['with_both_quarters'])} small hospitals show no clear change, "
      f"although {len(sm_raw5)} of them moved by 3 points or more on the published figure. A small hospital's bar is about "
      f"±{sm_k['bar'].median():.1f} points, against ±{both[both['peer_group'] == 'large']['bar'].median():.1f} for a large one.")
    A(f"- **Slipping is the norm among large hospitals**: {int(lg['slipping'])} of {int(lg['with_both_quarters'])}, against "
      f"{int(md['slipping'])} of {int(md['with_both_quarters'])} medium and {int(sm['slipping'])} of "
      f"{int(sm['with_both_quarters'])} small.\n")
    A("![Trend by peer group](charts/09_trend_by_group.png)\n")

    A("## 4. Large hospitals\n")
    kl = card[card["peer_group"] == "large"]
    A(f"Largest within-category fall first. Peer median same-mix rate: {lg['median_standardised']:.1f}%.\n")
    A(table(head, hospital_rows(kl)) + "\n")
    sl = kl[kl["trend"] == "slipping"]
    im = kl[kl["trend"] == "improving"]
    worst, best = kl.iloc[0], kl.sort_values("within", kind="stable").iloc[-1]
    lowest = kl.sort_values("standardised", kind="stable").iloc[0]
    assert worst["trend"] == "slipping" and best["trend"] == "improving"
    A(f"- **{worst.facility_name}** has the largest within-category fall ({sg(worst.within, 1)} points) and "
      f"**{best.facility_name}** the largest gain ({sg(best.within, 1)}).")
    A(f"- **{lowest.facility_name}** has the lowest same-mix rate ({lowest.standardised:.1f}%, "
      f"{abs(lowest.vs_peers):.1f} points under the peer median).")
    pe_s, pe_i = sl["patients_equivalent"].sum(), im["patients_equivalent"].sum()
    A(f"- **In patients:** at the {len(sl)} slipping large hospitals the within-category falls add up to roughly "
      f"{abs(round(pe_s, -2)):,.0f} more stays over 4 hours in the quarter than their {qname(q0)} category rates would give "
      f"(of {sl['attendances'].sum():,} attendances). The {len(im)} improving hospitals are roughly "
      f"{round(pe_i, -2):,.0f} stays better off.\n")
    A("![Large hospitals](charts/07_large_hospital_trend.png)\n")

    A("## 5. Medium hospitals\n")
    km = card[card["peer_group"] == "medium"]
    A(f"Peer median same-mix rate: {md['median_standardised']:.1f}%.\n")
    A(table(head, hospital_rows(km)) + "\n")
    mw, mb = km.iloc[0], km[km["within"].notna()].sort_values("within", kind="stable").iloc[-1]
    hi = km.sort_values("standardised", kind="stable").iloc[-1]
    A(f"- The largest fall is at **{mw.facility_name}** ({sg(mw.within, 1)} points) and the largest gain at "
      f"**{mb.facility_name}** ({sg(mb.within, 1)}).")
    A(f"- **{hi.facility_name}** is the outlier at the top: {hi.published_1:.1f}% of stays within 4 hours with "
      f"{hi.attendances:,} attendances, {hi.vs_peers:.1f} points above the peer median on the same mix. The data does not "
      "say why (it may run a different kind of service from its peers), so it is a hospital to ask about, not a benchmark "
      "to copy.")
    if len(new) == 1 and new["peer_group"].iloc[0] == "medium":
        x = new.iloc[0]
        A(f"- **{x.facility_name}** is new. Its first quarter is {x.published_1:.1f}%, the lowest same-mix rate in the group "
          f"({x.standardised:.1f}%); one quarter is too little to judge a new ED on.")
        assert x.standardised == km["standardised"].min()
    A("")

    A("## 6. Small hospitals\n")
    ks = card[card["peer_group"] == "small"]
    flagged = ks[ks["trend"].isin(["slipping", "improving"])]
    A(f"{len(ks)} hospitals; peer median same-mix rate {sm['median_standardised']:.1f}%. Only the {len(flagged)} whose change is "
      "outside the chance bar are listed. All are in `scorecard_hospitals.csv`.\n")
    A(table(head, hospital_rows(flagged)) + "\n")
    widest = ks.sort_values("bar", kind="stable").iloc[-1]
    A(f"- For the other {len(ks) - len(flagged)} the data cannot tell a real change from luck. The widest bar is "
      f"±{widest.bar:.1f} points ({widest.facility_name}, {widest.attendances:,} attendances in the quarter).")
    A("- A rate of exactly 100% or 0% in a category has no chance bar under this method, so the bar is slightly too "
      "narrow for the very smallest hospitals. Their flags deserve the most caution.\n")

    A("## 7. Level against trend\n")
    lvl = pd.crosstab(both["level"], both["trend"]).reindex(index=["below peers", "in line", "above peers"],
                                                            columns=TRENDS, fill_value=0)
    rows = [[i.capitalize()] + [str(int(v)) for v in lvl.loc[i]] + [str(int(lvl.loc[i].sum()))] for i in lvl.index]
    A(table(["Level", "Slipping", "No clear change", "Improving", "All"], rows) + "\n")
    pri = both[(both["level"] == "below peers") & (both["trend"] == "slipping")]
    hid = both[(both["level"] == "above peers") & (both["trend"] == "slipping")]
    rec = both[(both["level"] == "below peers") & (both["trend"] == "improving")]
    assert len(pri) and len(hid) and len(rec)
    A(f"### Below peers and slipping: {len(pri)} hospitals\n")
    rows = [[x.facility_name, BAND[x.peer_group], f"{x.attendances:,}", f"{x.published_0:.1f}%", f"{x.published_1:.1f}%",
             f"{x.standardised:.1f}%", f"{x.peer_median:.1f}%", sg(x.within, 1), f"±{x.bar:.1f}", x.seen_trend]
            for x in pri.itertuples(index=False)]
    A(table(["Hospital", "Peer group", f"Attendances, {qname(q1)}", f"Within 4 h, {qname(q0)}", f"Within 4 h, {qname(q1)}",
             "Same-mix rate", "Peer median", "Within-category change (points)", "Chance bar", "Seen on time: trend"], rows) + "\n")
    pc = pri["peer_group"].value_counts()
    A(f"- These {len(pri)} ({int(pc.get('large', 0))} large, {int(pc.get('medium', 0))} medium, {int(pc.get('small', 0))} small) are "
      "already in the lowest quarter of their group and still falling. They are the first places to look.")
    A(f"- **A good level can hide a slide.** {len(hid)} hospitals are in the top quarter of their group and slipping: "
      f"{', '.join(hid['facility_name'])}. A league table of levels would show them as fine.")
    A(f"- **A poor level can hide a recovery.** {len(rec)} are in the lowest quarter and improving: "
      f"{', '.join(rec['facility_name'])}.\n")
    A("![Level against trend](charts/08_level_vs_trend.png)\n")

    A("## 8. When did it happen, and does the front door move with it?\n")
    slip = both[both["trend"] == "slipping"]
    both_years = slip[(slip["within_first"] < 0) & (slip["within_second"] < 0)]
    first_only = slip[(slip["within_first"] < 0) & (slip["within_second"] >= 0)]
    second_only = slip[(slip["within_first"] >= 0) & (slip["within_second"] < 0)]
    assert len(both_years) + len(first_only) + len(second_only) == len(slip)
    A(f"Splitting the two years at {qname(q_mid)} (each year's within-category change, so the two do not add up exactly to "
      f"the two-year figure), for the {len(slip)} slipping hospitals:\n")
    A(f"- **{len(both_years)}** fell in both years.")
    A(f"- **{len(first_only)}** fell in the first year only, and have been level or better since (for example "
      f"{', '.join(first_only.sort_values('within_first', kind='stable')['facility_name'].head(3))}).")
    A(f"- **{len(second_only)}** fell in the second year only (for example "
      f"{', '.join(second_only.sort_values('within_second', kind='stable')['facility_name'].head(3))}): the most recent, and "
      "the ones a year-old review would have missed.")
    A("- Single-year changes have wider chance bars than the two-year change, so read this as a pointer to timing, not a "
      "second test.\n")
    ct = pd.crosstab(both["trend"], both["seen_trend"]).reindex(index=TRENDS, columns=TRENDS, fill_value=0)
    rows = [[i.capitalize()] + [str(int(v)) for v in ct.loc[i]] for i in ct.index]
    A("Patients seen within the recommended time, scored the same way (within-category change against its own chance "
      "bar; changes only, as Part 2 found the level does not rebuild exactly):\n")
    A(table(["4-hour stays ↓ / seen on time →", "Slipping", "No clear change", "Improving"], rows) + "\n")
    s_s, s_i = int(ct.loc["slipping", "slipping"]), int(ct.loc["slipping", "improving"])
    i_s, i_i = int(ct.loc["improving", "slipping"]), int(ct.loc["improving", "improving"])
    assert i_s == 0 and s_i > 0
    A(f"- Of the {len(slip)} hospitals slipping on 4-hour stays, {s_s} are also slipping on seeing patients on time and "
      f"{s_i} are *improving* on it.")
    A(f"- Of the {int(tot['improving'])} improving on 4-hour stays, {i_i} are also improving on seeing patients on time and "
      "none is slipping.")
    A("- So in this data no hospital improved its 4-hour rate while its front door got worse, but several improved the "
      "front door while the 4-hour rate fell. Part 4 looks at those hospitals' waits, walk-outs and admitted-patient "
      "delays.\n")

    A("## 9. What this means\n")
    state_rate = r["state_rate"]
    kl_below = int((kl["published_1"] < state_rate).sum())
    ks_above = int((ks["published_1"] > state_rate).sum())
    assert kl_below > 0.8 * len(kl) and ks_above == len(ks)
    A(f"1. **Judge a hospital against hospitals its own size, on the same mix.** The peer medians run from "
      f"{lg['median_standardised']:.1f}% (large) to {sm['median_standardised']:.1f}% (small). Against the state figure of "
      f"{state_rate:.1f}%, {kl_below} of the {len(kl)} large hospitals are below and all {ks_above} small hospitals are "
      "above, which says nothing about any of them.")
    A(f"2. **Start with the {len(pri)} hospitals that are below peers and slipping**, then the {len(hid)} whose high level "
      "hides a fall. Level and trend need separate columns in any performance report.")
    A(f"3. **Do not chase small hospitals' quarterly swings.** {int(sm['no_clear_change'])} of "
      f"{int(sm['with_both_quarters'])} show no change that chance could not produce. Review them on a rolling year, or "
      "only when a change clears the bar.")
    A(f"4. **The slide is concentrated where the patients are.** {int(lg['slipping'])} of {int(lg['with_both_quarters'])} "
      f"large hospitals are slipping, worth roughly {abs(round(pe_s, -2)):,.0f} more stays over 4 hours a quarter than "
      f"their {qname(q0)} category rates would give.")
    A(f"5. **Ask the improvers what changed.** {best.facility_name} and the other {int(tot['improving']) - 1} improving "
      "hospitals moved against the statewide trend. The data shows that they did, not how.\n")

    A("## 10. Rules carried into Part 4\n")
    A("1. Keep the three peer groups and compare levels on the peer group's mix.")
    A("2. Call a change real only when it clears the chance bar, and say that the bar is a floor.")
    A("3. Keep level and trend as separate verdicts.")
    A("4. Peer medians are not targets. If official targets are confirmed later, add them as a separate column.")
    A("")

    cols = ["facility_code", "facility_name", "peer_group", "attendances", "published_0", "published_1", "standardised",
            "standardised_se", "mix_covered", "peer_q25", "peer_median", "peer_q75", "vs_peers", "level", "change", "mix",
            "within", "within_se", "bar", "trend", "within_first", "within_second", "patients_equivalent", "seen_within",
            "seen_bar", "seen_trend"]
    csvs = {
        "scorecard_hospitals.csv": card[cols].round(4),
        "scorecard_peer_groups.csv": r["groups"].round(4),
        "scorecard_priority.csv": pri[cols].round(4),
    }
    return "\n".join(L), csvs


def main() -> int:
    df = load.read_snapshot(DATA / "ed_quarterly.csv")
    r = analyse(df)
    CHARTS.mkdir(parents=True, exist_ok=True)
    report, csvs = build_report(r)
    (RESULTS / "HOSPITAL_SCORECARD.md").write_text(report, encoding="utf-8")
    for name, frame in csvs.items():
        frame.to_csv(RESULTS / name, index=False, lineterminator="\n", float_format="%.10g")
    chart_large(r["card"], r["q0"], r["q1"], CHARTS / "07_large_hospital_trend.png")
    chart_level_trend(r["card"], CHART_LABELS, CHARTS / "08_level_vs_trend.png")
    chart_counts(r["groups"], CHARTS / "09_trend_by_group.png")
    print(f"wrote results/HOSPITAL_SCORECARD.md, {len(csvs)} CSVs, 3 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
