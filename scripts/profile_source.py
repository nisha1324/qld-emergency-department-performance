"""Part 1: profile the source and write results/SOURCE_PROFILE.md, CSVs and charts.

    python scripts/profile_source.py

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
from edperf import load, profile as P  # noqa: E402

DATA, RESULTS = ROOT / "data", ROOT / "results"
CHARTS = RESULTS / "charts"
LARGE = 10_000  # attendances in the quarter; splits "large" emergency departments from the rest

# Reference palette (2 slots, light mode)
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlecolor": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "path.simplify": False,
})
SAVE = {"dpi": 150, "metadata": {"Software": None}}
MONTHS = {"03": "Jan-Mar", "06": "Apr-Jun", "09": "Jul-Sep", "12": "Oct-Dec"}
SHORT = {"03": "Mar", "06": "Jun", "09": "Sep", "12": "Dec"}


def qname(q: str) -> str:
    """'2026-06' -> 'Apr-Jun 2026'."""
    return f"{MONTHS[q[5:]]} {q[:4]}"


def qshort(q: str) -> str:
    return f"{SHORT[q[5:]]}\n{q[:4]}" if q[5:] == "03" else SHORT[q[5:]]


def n(x: float, nd: int = 0) -> str:
    return f"{x:,.{nd}f}"


def pw(x: float, quarter: str, whole: set[str]) -> str:
    """A published percentage, at the precision its quarter was published with."""
    return f"{x:.0f}%" if quarter in whole else f"{x:.1f}%"


def style(ax, title: str, subtitle: str | None = None) -> None:
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=22 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_2)


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join(" --- " if df[c].dtype == object and i == 0 else " ---: "
                         for i, c in enumerate(df.columns)) + "|"
    rows = ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep] + rows)


# ------------------------------------------------------------------ charts
def chart_trend(trend: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    x = range(len(trend))
    series = [("seen_on_time_pct", "Seen within the recommended time", BLUE),
              ("stay_within_4h_pct", "Left the ED within 4 hours", ORANGE)]
    for col, label, colour in series:
        ax.plot(x, trend[col], color=colour, linewidth=2, marker="o", markersize=4)
        first, last = trend[col].iloc[0], trend[col].iloc[-1]
        ax.text(len(trend) - 1 + 0.2, last, f"{last:.1f}%", va="center", fontsize=9, color=INK)
        ax.text(-0.2, first, f"{first:.0f}%", va="center", ha="right", fontsize=9, color=INK)
        ax.text(-0.1, first + (6.3 if col == "seen_on_time_pct" else -3.2), label,
                fontsize=9, color=colour, fontweight="bold")
    ax.set_xticks(list(x), [qshort(q) for q in trend["quarter"]])
    ax.set_xlim(-1.1, len(trend) - 1 + 1.2)
    ax.set_ylim(50, 80)
    ax.set_ylabel("% of attendances")
    style(ax, "Patients are seen a little sooner, but fewer leave within four hours",
          "Queensland public emergency departments, all triage categories, by quarter (last month shown)")
    fig.tight_layout()
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_mix(mix: pd.DataFrame, q0: str, q1: str, path: Path) -> None:
    a = mix.set_index("quarter").loc[q0]
    b = mix.set_index("quarter").loc[q1]
    labels = ["1\nresuscitation", "2\nemergency", "3\nurgent", "4\nsemi-urgent", "5\nnon-urgent"]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    w = 0.38
    xs = range(5)
    ax.bar([i - w / 2 - 0.01 for i in xs], a[P.TRIAGE_1_TO_5], width=w, color=BLUE, label=qname(q0))
    ax.bar([i + w / 2 + 0.01 for i in xs], b[P.TRIAGE_1_TO_5], width=w, color=ORANGE, label=qname(q1))
    for i, t in enumerate(P.TRIAGE_1_TO_5):
        ax.text(i - w / 2, a[t] + 0.7, f"{a[t]:.1f}%", ha="center", fontsize=8, color=INK)
        ax.text(i + w / 2, b[t] + 0.7, f"{b[t]:.1f}%", ha="center", fontsize=8, color=INK)
    ax.set_xticks(list(xs), labels)
    ax.set_xlabel("Triage category")
    ax.set_ylabel("% of attendances")
    ax.set_ylim(0, 50)
    style(ax, "The mix has shifted towards more urgent patients",
          "Share of Queensland emergency department attendances by triage category, same quarter three years apart")
    ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_size(sizes: pd.DataFrame, quarter: str, state_rate: float, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    big = sizes["attendances"] >= LARGE
    ax.scatter(sizes.loc[~big, "attendances"], sizes.loc[~big, "stay_within_4h_pct"], s=26,
               color=BLUE, alpha=0.75, linewidth=0, label=f"Under {LARGE:,} attendances ({(~big).sum()} hospitals)")
    ax.scatter(sizes.loc[big, "attendances"], sizes.loc[big, "stay_within_4h_pct"], s=34,
               color=ORANGE, alpha=0.9, linewidth=0, label=f"{LARGE:,} or more ({big.sum()} hospitals)")
    ax.axhline(state_rate, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(110, state_rate + 1.2, f"Queensland: {state_rate:.1f}%", fontsize=9, color=INK_2)
    ax.set_xscale("log")
    ax.set_xticks([100, 300, 1000, 3000, 10000, 30000], ["100", "300", "1,000", "3,000", "10,000", "30,000"])
    ax.minorticks_off()
    ax.set_xlim(100, 45000)
    ax.set_ylim(20, 104)
    ax.set_xlabel("Attendances in the quarter (log scale)")
    ax.set_ylabel("% of ED stays within 4 hours")
    style(ax, "The four-hour problem sits in the large emergency departments",
          f"Each dot is one hospital, {qname(quarter)}")
    ax.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path, **SAVE)
    plt.close(fig)


# ------------------------------------------------------------------ report
def build_report(df: pd.DataFrame, names: pd.DataFrame) -> tuple[str, dict[str, pd.DataFrame]]:
    quarters = sorted(df["quarter"].unique())
    q_first, q_last = quarters[0], quarters[-1]
    q_base = f"{int(q_last[:4]) - 3}{q_last[4:]}"          # same quarter, three years earlier
    whole = P.whole_number_quarters(df)
    cov = P.coverage(df)
    trend = P.state_trend(df).set_index("quarter")
    roll = P.rolling_year(df).set_index("quarter")
    tri = P.triage_table(df, q_last)
    mix = P.triage_mix(df)
    sizes = P.size_table(df, q_last)
    size_sum = P.size_summary(sizes, LARGE)
    missing = P.missing_table(df)
    dash = P.dash_for_zero(df)
    change = P.change_check(df)
    newf = P.new_facilities(df)
    c_tri, c_state, c_rates = P.check_triage_sums(df), P.check_state_sums(df), P.check_rates_from_counts(df)
    w_seen = P.check_state_rate_is_weighted(df, "seen_on_time_pct")
    w_stay = P.check_state_rate_is_weighted(df, "stay_within_4h_pct")
    sv_stay = P.simple_vs_weighted(df, q_last, "stay_within_4h_pct")
    sv_seen = P.simple_vs_weighted(df, q_last, "seen_on_time_pct")

    last, base = trend.loc[q_last], trend.loc[q_base]
    m_last, m_base = mix.set_index("quarter").loc[q_last], mix.set_index("quarter").loc[q_base]
    big, small = size_sum.iloc[0], size_sum.iloc[1]
    n_hosp_last = int(cov.set_index("quarter").loc[q_last, "hospitals"])
    n_hosp_first = int(cov.set_index("quarter").loc[q_first, "hospitals"])
    multi_names = int((names.groupby("facility_code")["raw_name"].nunique() > 1).sum())
    n_codes = int(names["facility_code"].nunique())
    zero_rows = df[df["attendances"] == 0]
    mism = change[change["mismatch"]]
    mism_whole = mism[mism["quarter"].isin(whole)]
    mism_dec = mism[~mism["quarter"].isin(whole)]
    mism_dec_all = mism_dec[mism_dec["triage"] == "ALL"]
    yr_last, yr_base = roll.loc[q_last, "attendances_4q"], roll.loc[f"{int(q_last[:4]) - 2}{q_last[4:]}", "attendances_4q"]
    q_yr_base = f"{int(q_last[:4]) - 2}{q_last[4:]}"
    adm4_gap = df[df["admitted_within_4h_pct"].isna() & (df["attendances"] > 0)]
    adm4_gap_zero = int(((adm4_gap["admitted_pct"] == 0) | adm4_gap["admitted_pct"].isna()).sum())
    dash_q = dash[dash["published_empty"] > 0]
    top5 = sizes.head(5)
    half_n = int((sizes["cum_share_pct"] < 50).sum()) + 1

    L: list[str] = []
    A = L.append
    A("# Source profile: Queensland emergency departments, quarterly\n")
    A("*Generated by `scripts/profile_source.py` from the snapshot in `data/`. Do not edit by hand.*\n")
    A(f"Source: Queensland Health, [Emergency departments - quarterly data]({P_SOURCE}), CC BY 4.0. "
      f"One row per hospital, quarter and triage category. A quarter is named by its last month, "
      f"so `{q_last}` is {qname(q_last)}.\n")

    A("## 1. What is in the snapshot\n")
    A(f"- **{len(quarters)} quarters**, {qname(q_first)} to {qname(q_last)}; **{len(df):,} rows**.")
    A(f"- **{n_hosp_first} hospitals** in every quarter, plus one \"Queensland\" total row per triage category. "
      + (f"**{newf.iloc[0]['facility_name']}** first reports in {qname(newf.iloc[0]['first_quarter'])}, "
         f"which makes {n_hosp_last}." if len(newf) == 1 else f"{len(newf)} hospitals are not in every quarter."))
    A(f"- Six rows per hospital and quarter: triage categories 1 to 5 and `ALL`.")
    A(f"- **{n(yr_last)} attendances** in the four quarters to {qname(q_last)}, against {n(yr_base)} in the four "
      f"quarters to {qname(q_yr_base)} ({(yr_last / yr_base - 1) * 100:+.1f}% over two years).\n")

    A("## 2. The state picture\n")
    A(f"Same quarter, three years apart ({qname(q_base)} was published in whole percentages):\n")
    t = pd.DataFrame({
        "Measure (all triage categories)": [
            "Attendances", "Seen within the clinically recommended time", "Median wait to treatment (minutes)",
            "ED stay within 4 hours", "Admitted from the ED", "Admissions to hospital within 4 hours",
            "Did not wait for treatment", "Left after treatment started"],
        qname(q_base): [
            n(base["attendances"]), pw(base["seen_on_time_pct"], q_base, whole), f"{base['median_wait_min']:.0f}",
            pw(base["stay_within_4h_pct"], q_base, whole), pw(base["admitted_pct"], q_base, whole),
            pw(base["admitted_within_4h_pct"], q_base, whole),
            f"{base['did_not_wait_pct']:.1f}%", f"{base['left_after_treatment_pct']:.1f}%"],
        qname(q_last): [
            n(last["attendances"]), pw(last["seen_on_time_pct"], q_last, whole), f"{last['median_wait_min']:.0f}",
            pw(last["stay_within_4h_pct"], q_last, whole), pw(last["admitted_pct"], q_last, whole),
            pw(last["admitted_within_4h_pct"], q_last, whole),
            f"{last['did_not_wait_pct']:.1f}%", f"{last['left_after_treatment_pct']:.1f}%"],
    })
    A(md_table(t) + "\n")
    A("The last two rows are worked out from the published counts, so both columns have one decimal place. "
      "\"Admissions to hospital within 4 hours\" is the source's wording; it is read here as the share of admitted "
      "patients whose ED stay was within 4 hours.\n")
    A(f"- **The front door got a little faster.** Patients seen on time went from "
      f"{pw(base['seen_on_time_pct'], q_base, whole)} to {pw(last['seen_on_time_pct'], q_last, whole)}, and the median "
      f"wait from {base['median_wait_min']:.0f} to {last['median_wait_min']:.0f} minutes.")
    A(f"- **The back door got slower.** Stays within 4 hours fell from {pw(base['stay_within_4h_pct'], q_base, whole)} "
      f"to {pw(last['stay_within_4h_pct'], q_last, whole)}. For patients who are admitted it fell from "
      f"{pw(base['admitted_within_4h_pct'], q_base, whole)} to {pw(last['admitted_within_4h_pct'], q_last, whole)}: "
      f"on that reading, about two in three admitted patients now spend more than 4 hours in the ED.")
    A(f"- **Attendances barely moved** ({(last['attendances'] / base['attendances'] - 1) * 100:+.1f}% on the same quarter "
      f"three years earlier), so volume alone does not explain the longer stays.\n")
    A("![State trend](charts/01_state_trend.png)\n")

    A(f"### By triage category, {qname(q_last)}\n")
    tt = pd.DataFrame({
        "Triage": tri["triage"],
        "Attendances": [n(v) for v in tri["attendances"]],
        "Share": [f"{v:.1f}%" for v in tri["share_pct"]],
        "Seen on time": [f"{v:.1f}%" for v in tri["seen_on_time_pct"]],
        "Median wait (min)": [f"{v:.0f}" for v in tri["median_wait_min"]],
        "Admitted": [f"{v:.1f}%" for v in tri["admitted_pct"]],
        "Stay within 4 h": [f"{v:.1f}%" for v in tri["stay_within_4h_pct"]],
    })
    A(md_table(tt) + "\n")
    A(f"The mix is getting more urgent. Category 2 went from {m_base['2']:.1f}% of attendances in {qname(q_base)} to "
      f"{m_last['2']:.1f}% in {qname(q_last)}; categories 4 and 5 together went from {m_base['4'] + m_base['5']:.1f}% to "
      f"{m_last['4'] + m_last['5']:.1f}%. More urgent patients are admitted more often and stay longer, so part of "
      f"the fall in the 4-hour figure is mix. Part 2 separates the two.\n")
    A("![Triage mix](charts/02_triage_mix.png)\n")

    A("## 3. A few large hospitals carry the state figure\n")
    A(f"In {qname(q_last)}, **{int(big['hospitals'])} of {n_hosp_last} hospitals** had {LARGE:,} or more attendances. "
      f"They handled **{big['share_pct']:.1f}%** of all attendances; the largest {half_n} alone handled just over half.\n")
    st = pd.DataFrame({
        "Attendances in the quarter": size_sum["attendances_in_quarter"],
        "Hospitals": size_sum["hospitals"],
        "Attendances": [n(v) for v in size_sum["attendances"]],
        "Share": [f"{v:.1f}%" for v in size_sum["share_pct"]],
        "Stay within 4 h": [f"{v:.1f}%" for v in size_sum["stay_within_4h_weighted"]],
        "median hospital": [f"{v:.1f}%" for v in size_sum["stay_within_4h_median"]],
        "lowest": [f"{v:.1f}%" for v in size_sum["stay_within_4h_min"]],
        "highest": [f"{v:.1f}%" for v in size_sum["stay_within_4h_max"]],
    })
    A(md_table(st) + "\n")
    A(f"Weighted by attendances, {big['stay_within_4h_weighted']:.1f}% of stays at the large hospitals were within 4 hours, "
      f"against {small['stay_within_4h_weighted']:.1f}% at the rest. The state's {sv_stay['state']:.1f}% is therefore mostly a "
      f"statement about {int(big['hospitals'])} hospitals, and it is far from the typical one: the median across all "
      f"{n_hosp_last} is {sv_stay['median_hospital']:.1f}%. The same holds for patients seen on time "
      f"({sv_seen['state']:.1f}% for the state, {sv_seen['median_hospital']:.1f}% for the median hospital).\n")
    A("![Size and 4-hour stays](charts/03_size_vs_4h.png)\n")
    A("The five largest:\n")
    t5 = pd.DataFrame({
        "Hospital": top5["facility_name"],
        "Attendances": [n(v) for v in top5["attendances"]],
        "Seen on time": [f"{v:.1f}%" for v in top5["seen_on_time_pct"]],
        "Median wait (min)": [f"{v:.0f}" for v in top5["median_wait_min"]],
        "Stay within 4 h": [f"{v:.1f}%" for v in top5["stay_within_4h_pct"]],
    })
    A(md_table(t5) + "\n")

    A("## 4. Checks on the source\n")
    A(f"- **Triage categories add up.** Categories 1 to 5 sum to the `ALL` row in {c_tri['facility_quarters'] - c_tri['mismatches']:,} "
      f"of {c_tri['facility_quarters']:,} hospital-quarters (state rows included).")
    A(f"- **Hospitals add up to the state.** Attendances, did-not-wait counts and left-after-treatment counts summed over "
      f"hospitals equal the Queensland row in {c_state['quarters'] - c_state['attendances_mismatches']} of {c_state['quarters']} quarters "
      f"(mismatches: {c_state['attendances_mismatches']}, {c_state['did_not_wait_mismatches']}, {c_state['left_after_treatment_mismatches']}).")
    A(f"- **Percentages match their counts.** \"Did not wait\" ({c_rates['did_not_wait_pct_compared']:,} rows) and \"left after "
      f"treatment\" ({c_rates['left_after_treatment_pct_compared']:,} rows) equal count ÷ attendances to the published rounding, with "
      f"{c_rates['did_not_wait_pct_mismatches']} and {c_rates['left_after_treatment_pct_mismatches']} exceptions.")
    A(f"- **State rates are attendance-weighted.** The state \"seen on time\" and \"stay within 4 hours\" figures are within "
      f"{w_seen:.2f} and {w_stay:.2f} points of the attendance-weighted mean of hospital figures in every quarter "
      f"(hospital figures are rounded, so a small gap is expected).")
    A(f"- **\"Variation in attendances\" is the change on the same quarter a year earlier.** Recomputed from this snapshot "
      f"for {len(change):,} rows: {len(change) - len(mism):,} agree to the published rounding. The {len(mism)} that do not are all in "
      f"two quarters, {' and '.join(qname(q) for q in sorted(mism['quarter'].unique()))}, at "
      f"{mism.loc[~mism['is_state_total'], 'facility_code'].nunique()} hospitals. Their all-categories rows:\n")
    mm = mism[mism["triage"] == "ALL"].sort_values(["quarter", "is_state_total", "facility_name"], kind="stable")
    A(md_table(pd.DataFrame({
        "Hospital": mm["facility_name"],
        "Quarter": [qname(q) for q in mm["quarter"]],
        "Attendances": [n(v) for v in mm["attendances"]],
        "A year earlier (snapshot)": [n(v) for v in mm["attendances_year_earlier"]],
        "Change, recomputed": [f"{v:+.1f}%" for v in mm["recomputed_pct"]],
        "Change, published": [f"{v:+.0f}%" if q in whole else f"{v:+.1f}%"
                              for v, q in zip(mm["attendances_change_pct"], mm["quarter"])],
        "Year-earlier figure the published change implies": [n(v) for v in mm["implied_year_earlier"]],
    })) + "\n")
    A("Either the year-earlier figure was revised somewhere this snapshot does not show, or the published change is "
      "wrong. The snapshot cannot tell which. Most gaps are a point or two. The exception is Nambour in Oct-Dec 2025, "
      "and the Queensland row for that quarter is out by a similar number of attendances.\n")

    A("## 5. Quirks the loader handles\n")
    A(f"- **Names drift.** {multi_names} of {n_codes} facility codes (the state row included) appear under more than one name "
      f"(for example \"Ipswich Hospital\", then \"Ipswich\"). The code is the key; `data/facility_names.csv` lists every spelling.")
    A("- **Columns drift.** The triage column is `Triage Category` in some quarters and `Triage_Category` in others, "
      "its all-categories value is `All` in one quarter and `ALL` elsewhere, and five quarters carry an extra "
      "`Median Wait Traffic Light` column (dropped).")
    A(f"- **Precision changes.** Percentages are whole numbers in the {len(whole)} quarters to {qname(max(whole))} and have one "
      f"decimal place from {qname(min(set(quarters) - whole))}.")
    A("- **Four spellings of \"missing\".** `-`, `NULL`, an empty string and a null all become empty cells.\n")

    A("### Empty cells by measure\n")
    mt = missing.rename(columns={
        "measure": "Measure", "empty": "Empty", "of_which_no_attendances": "Row has no attendances",
        "of_which_with_attendances": "Row has attendances", "quarters_affected_with_attendances": "Quarters affected (rows with attendances)"})
    A(md_table(mt) + "\n")
    A(f"- {len(zero_rows)} rows have no attendances at all ({int((zero_rows['triage'] == '1').sum())} of them are triage "
      f"category 1). Their rates are empty, as they should be.")
    A(f"- In {len(dash_q)} quarters ({qname(dash_q['quarter'].min())} to {qname(dash_q['quarter'].max())}) a **zero is published as `-`**: "
      f"{int(dash_q['published_empty'].sum())} of {int(dash_q['rows'].sum())} rows with attendances and nobody who left without "
      f"waiting have an empty percentage. In the other {len(dash) - len(dash_q)} quarters all such rows show 0.")
    A(f"- \"Admitted within 4 hours\" is empty in {len(adm4_gap)} rows that have attendances. In {adm4_gap_zero} of them nobody was "
      f"admitted (or the admitted share is itself a `-`), so the measure has no base.\n")

    A("## 6. Rules for the rest of the project\n")
    rules = [
        "**Use the facility code, not the name.**",
        "**Work out \"did not wait\" and \"left after treatment\" from the counts**, not the published percentages: the counts "
        "are complete in every quarter and are not rounded.",
        f"**Mind the rounding break.** Up to {qname(max(whole))} a published percentage can be off by up to 0.5 points, so a "
        "change of under a point across the break is not a finding.",
        "**Compare like quarters.** Use the same quarter a year apart, or four-quarter totals, not neighbouring quarters.",
        f"**Do not average hospitals to describe the state.** The plain average of hospital 4-hour figures in {qname(q_last)} is "
        f"{sv_stay['simple_mean_of_hospitals']:.1f}%; the state figure is {sv_stay['state']:.1f}%. Weight by attendances, or compare "
        "hospitals within a size group.",
        "**Compare within a triage category where possible.** The all-categories figures move when the mix moves.",
        "**Where the published change and the snapshot disagree, flag the hospital instead of picking a side.** "
        "Growth figures for those hospital-quarters are not reliable.",
        "**An empty \"admitted within 4 hours\" usually means nobody was admitted**, not a bad result.",
    ]
    for i, r in enumerate(rules, 1):
        A(f"{i}. {r}")
    A("")

    csvs = {
        "state_trend.csv": P.state_trend(df).round(3),
        "triage_latest.csv": tri.round(3),
        "triage_mix.csv": mix.round(3),
        "hospital_sizes_latest.csv": sizes.round(3),
        "missing_by_measure.csv": missing,
        "attendance_change_mismatches.csv": mism.round(3),
    }
    return "\n".join(L), csvs


P_SOURCE = "https://www.data.qld.gov.au/dataset/emergency-departments-quarterly-data"


def main() -> int:
    df = load.read_snapshot(DATA / "ed_quarterly.csv")
    names = pd.read_csv(DATA / "facility_names.csv", dtype=str).astype({"facility_code": int})
    CHARTS.mkdir(parents=True, exist_ok=True)
    report, csvs = build_report(df, names)
    (RESULTS / "SOURCE_PROFILE.md").write_text(report, encoding="utf-8")
    for name, frame in csvs.items():
        frame.to_csv(RESULTS / name, index=False, lineterminator="\n", float_format="%.10g")

    quarters = sorted(df["quarter"].unique())
    q_last = quarters[-1]
    q_base = f"{int(q_last[:4]) - 3}{q_last[4:]}"
    trend = P.state_trend(df)
    chart_trend(trend, CHARTS / "01_state_trend.png")
    chart_mix(P.triage_mix(df), q_base, q_last, CHARTS / "02_triage_mix.png")
    sizes = P.size_table(df, q_last)
    chart_size(sizes, q_last, float(trend["stay_within_4h_pct"].iloc[-1]), CHARTS / "03_size_vs_4h.png")
    print(f"wrote results/SOURCE_PROFILE.md, {len(csvs)} CSVs, 3 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
