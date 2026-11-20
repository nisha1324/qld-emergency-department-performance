"""Part 2: mix versus performance. Writes results/MIX_VS_PERFORMANCE.md, CSVs and charts 04-06.

    python scripts/mix_report.py

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
from edperf import load, mix as M, profile as P  # noqa: E402
from scripts import profile_source as B  # noqa: E402  (shared palette, labels and chart style)

DATA, RESULTS, CHARTS = B.DATA, B.RESULTS, B.CHARTS
LARGE = B.LARGE
S = load.STATE_CODE
BLUE, ORANGE, INK, INK_2, MUTED, GRID = B.BLUE, B.ORANGE, B.INK, B.INK_2, B.MUTED, B.GRID
qname = B.qname

STAY, SEEN, ADM, ADM4 = "stay_within_4h_pct", "seen_on_time_pct", "admitted_pct", "admitted_within_4h_pct"
LABEL = {STAY: "ED stay within 4 hours", SEEN: "Seen within the recommended time",
         ADM4: "Admitted patients: ED stay within 4 hours", ADM: "Admitted from the ED"}
TRIAGE_NAME = {"1": "1 resuscitation", "2": "2 emergency", "3": "3 urgent", "4": "4 semi-urgent", "5": "5 non-urgent"}


def sg(x: float, nd: int = 2) -> str:
    """Signed number with a real minus sign; a rounded zero has no sign."""
    r = round(x, nd)
    if r == 0:
        return f"{0:.{nd}f}"
    return f"{'+' if r > 0 else '−'}{abs(r):.{nd}f}"


def pct_of(part: float, change: float) -> str:
    return f"{M.share_of_change(part, change):.0f}%"


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "| --- |" + " ---: |" * (len(header) - 1)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def periods(df: pd.DataFrame) -> dict:
    quarters = sorted(df["quarter"].unique())
    whole = P.whole_number_quarters(df)
    q1 = quarters[-1]
    same = [q for q in quarters if q[5:] == q1[5:] and q != q1]
    return {"quarters": quarters, "whole": whole, "q1": q1, "q_long": same[0],
            "q0": [q for q in same if q not in whole][0]}


def tol(q: str, whole: set[str]) -> float:
    return 0.5 if q in whole else 0.05


def analyse(df: pd.DataFrame) -> dict:
    """Everything the report, CSVs and charts are built from."""
    p = periods(df)
    q0, q1, q_long, whole = p["q0"], p["q1"], p["q_long"], p["whole"]
    c = {m: M.cells(df, m) for m in M.WEIGHT}
    r = dict(p)
    r["state"] = {m: M.decompose(M.unit(c[m], q0, S), M.unit(c[m], q1, S)) for m in M.WEIGHT}
    r["state_long"] = {m: M.decompose(M.unit(c[m], q_long, S), M.unit(c[m], q1, S)) for m in (STAY, SEEN)}
    r["margin"] = {m: M.rounding_margin(r["state"][m], tol(q0, whole), tol(q1, whole)) for m in M.WEIGHT}
    r["margin_long"] = {m: M.rounding_margin(r["state_long"][m], tol(q_long, whole), tol(q1, whole)) for m in (STAY, SEEN)}
    r["gaps"] = {m: M.rebuild_gaps(df, m, S) for m in M.WEIGHT}
    r["yoy"] = {m: M.year_on_year(c[m], S) for m in (STAY, SEEN)}
    r["fixed"] = M.fixed_mix_series(c[STAY], S, p["quarters"][0])

    big = M.large_codes(df, q1, LARGE)
    h = df[~df["is_state_total"]]
    both = set(h.loc[h["quarter"] == q0, "facility_code"]) & set(h.loc[h["quarter"] == q1, "facility_code"])
    only_end = sorted(set(h.loc[h["quarter"] == q1, "facility_code"]) - both)
    rest = sorted(both - set(big))
    r["big"], r["rest"], r["only_end"] = big, rest, only_end
    r["groups"] = {
        name: {m: M.decompose(M.pool(c[m], q0, codes), M.pool(c[m], q1, codes)) for m in (STAY, SEEN)}
        for name, codes in (("large", big), ("rest", rest))
    }
    r["hospitals"] = {m: M.hospital_table(df, m, q0, q1, big) for m in (STAY, SEEN)}

    a = df[(df["triage"] == "ALL") & df["is_state_total"]].set_index("quarter")
    u0, u1 = M.admitted_split(a.loc[q0]), M.admitted_split(a.loc[q1])
    r["adm_split"] = M.decompose(u0, u1)
    r["adm_margin"] = max(M.implied_margin(a.loc[q0], tol(q0, whole)), M.implied_margin(a.loc[q1], tol(q1, whole)))
    r["published"] = a
    return r


# ------------------------------------------------------------------ charts
def chart_fixed_mix(fixed: pd.DataFrame, base_q: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    x = list(range(len(fixed)))
    ax.plot(x, fixed["fixed_mix"], color=INK_2, linewidth=2, linestyle=(0, (4, 2)),
            label=f"With the {qname(base_q)} triage mix")
    ax.plot(x, fixed["rebuilt"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="Actual")
    last = len(fixed) - 1
    a, f = fixed["rebuilt"].iloc[-1], fixed["fixed_mix"].iloc[-1]
    ax.text(last + 0.2, a - 0.25, f"{a:.1f}%  actual", va="center", fontsize=9, color=INK)
    ax.text(last + 0.2, f + 0.25, f"{f:.1f}%  same mix", va="center", fontsize=9, color=INK)
    ax.text(-0.2, fixed["rebuilt"].iloc[0], f"{fixed['rebuilt'].iloc[0]:.1f}%", va="center", ha="right",
            fontsize=9, color=INK)
    ax.set_xticks(x, [B.qshort(q) for q in fixed["quarter"]])
    ax.set_xlim(-1.3, last + 2.6)
    ax.set_ylim(54, 64)
    ax.set_ylabel("% of ED stays within 4 hours")
    B.style(ax, "A more urgent mix explains part of the fall, not most of it",
            "Queensland, ED stays within 4 hours: actual, and with every category's share held at its first-quarter level")
    ax.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


def chart_effects(state: dict, q0: str, q1: str, path: Path) -> None:
    measures = [STAY, ADM4, SEEN]
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    hgt = 0.32
    for i, m in enumerate(measures):
        d = state[m]
        y = len(measures) - 1 - i
        for off, key, colour in ((hgt / 2 + 0.02, "mix", BLUE), (-hgt / 2 - 0.02, "within", ORANGE)):
            v = d[key]
            ax.barh(y + off, v, height=hgt, color=colour)
            ax.text(v + (0.06 if v >= 0 else -0.06), y + off, sg(v, 1), va="center",
                    ha="left" if v >= 0 else "right", fontsize=9, color=INK)
        ax.text(-4.35, y, f"{LABEL[m]}\n{d['rate_0']:.1f}% to {d['rate_1']:.1f}% ({sg(d['change'], 1)})",
                va="center", ha="right", fontsize=9, color=INK)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks([])
    ax.set_xlim(-4.3, 2.6)
    ax.set_ylim(-0.6, len(measures) - 0.4)
    ax.set_xlabel("Contribution to the change, percentage points")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=ORANGE)]
    fig.legend(handles, ["Triage mix (which patients arrive)", "Within category (same category, different result)"],
               loc="upper left", bbox_to_anchor=(0.012, 0.885), ncol=2, frameon=False, fontsize=9, labelcolor=INK_2)
    fig.suptitle("Mix hides part of the front-door gain and explains part of the 4-hour fall",
                 x=0.02, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.02, 0.9, f"Queensland emergency departments, {qname(q0)} to {qname(q1)}", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.83))
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


def chart_hospitals(hosp: pd.DataFrame, q0: str, q1: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 8.6))
    hgt = 0.36
    n = len(hosp)
    for i, row in enumerate(hosp.itertuples(index=False)):
        y = n - 1 - i
        ax.barh(y + hgt / 2 + 0.02, row.mix, height=hgt, color=BLUE)
        ax.barh(y - hgt / 2 - 0.02, row.within, height=hgt, color=ORANGE)
        ax.text(10.4, y, f"{row.published_0:.1f}% to {row.published_1:.1f}%", va="center", fontsize=8.5, color=INK)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks(range(n), list(hosp["facility_name"])[::-1], fontsize=9)
    ax.set_xlim(-9.5, 10)
    ax.set_ylim(-0.7, n + 0.3)
    ax.text(10.4, n - 0.25, "Stays within 4 h", fontsize=8.5, color=INK_2)
    ax.set_xlabel("Contribution to the change in stays within 4 hours, percentage points")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=ORANGE)]
    ax.legend(handles, ["Triage mix", "Within category"], loc="upper right", bbox_to_anchor=(1.0, 0.97),
              frameon=False, fontsize=9, labelcolor=INK_2)
    fig.suptitle("At the large hospitals the change is within category, in both directions",
                 x=0.02, y=0.985, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.02, 0.95, f"The {n} hospitals with {LARGE:,}+ attendances a quarter, {qname(q0)} to {qname(q1)}, "
             "largest fall first", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 0.86, 0.945))
    fig.savefig(path, **B.SAVE)
    plt.close(fig)


# ------------------------------------------------------------------ report
def build_report(r: dict) -> tuple[str, dict[str, pd.DataFrame]]:
    q0, q1, q_long, whole = r["q0"], r["q1"], r["q_long"], r["whole"]
    L: list[str] = []
    A = L.append
    st, lg = r["state"], r["state_long"]
    d = st[STAY]
    by = d["by_category"]
    years = int(q1[:4]) - int(q0[:4])
    years_long = int(q1[:4]) - int(q_long[:4])
    words = {2: "two", 3: "three"}

    A("# Mix versus performance: why fewer ED stays finish within 4 hours\n")
    A("*Generated by `scripts/mix_report.py` from the snapshot in `data/`. Do not edit by hand.*\n")
    A("Part 1 found two things moving at once: fewer emergency department (ED) stays finish within 4 hours, and more "
      "patients arrive in the urgent triage categories, where fewer stays finish within 4 hours. This part separates them. "
      "\"Mix\" is the part of a change that comes from *which* patients arrive. \"Within category\" is the part that "
      "comes from patients in the same triage category getting a different result, which is closer to a measure of performance.\n")

    A("## 1. Method\n")
    A("An all-categories rate is the weighted average of the five triage categories, each weighted by its share of "
      "patients. Between two quarters the change splits exactly into two parts, with nothing left over:\n")
    A("- **mix effect**: each category's change in share × its average rate over the two quarters, summed;")
    A("- **within-category effect**: each category's change in rate × its average share, summed.\n")
    A(f"The main comparison is **{qname(q0)} to {qname(q1)}**: the same quarter {words[years]} years apart, and the longest "
      "like-for-like span in which every figure is published to one decimal place. The "
      f"{words[years_long]}-year comparison from {qname(q_long)} is given with a margin, because that quarter was "
      "published in whole percentages.\n")

    g = r["gaps"]
    dec = lambda m: g[m][~g[m]["quarter"].isin(whole)]  # noqa: E731
    wh = lambda m: g[m][g[m]["quarter"].isin(whole)]  # noqa: E731
    A("**Does the method fit the data?** Rebuilding the published all-categories figure from the five categories:\n")
    rows = []
    for m, base in ((STAY, "attendances"), (ADM, "attendances"), (ADM4, "admitted patients (attendances × admitted share)"),
                    (SEEN, "attendances")):
        rows.append([LABEL[m], base, f"{dec(m)['gap'].abs().max():.2f}", f"{wh(m)['gap'].abs().max():.2f}"])
    A(table(["Measure", "Weighted by", f"Largest gap, {len(dec(STAY))} one-decimal quarters (points)",
             f"Largest gap, {len(wh(STAY))} whole-number quarters (points)"], rows) + "\n")
    sg_ = dec(SEEN)["gap"]
    assert dec(STAY)["gap"].abs().max() < 0.1 and dec(ADM4)["gap"].abs().max() < 0.1 and dec(ADM)["gap"].abs().max() < 0.1
    assert sg_.min() > 0.1
    A(f"Three of the four rebuild to within rounding. \"Seen within the recommended time\" does not: the rebuilt figure is "
      f"{sg_.min():.2f} to {sg_.max():.2f} points above the published one in every one-decimal quarter, so its published "
      "total is not a plain attendance-weighted average of the categories (the source does not say what it leaves out). "
      f"The gap is steady, moving by at most {sg_.max() - sg_.min():.2f} points between those quarters, so the split of a "
      "*change* in that measure is still usable, to about a tenth of a point.\n")

    A("## 2. Stays within 4 hours: the triage mix is over a third of the fall\n")
    A(f"Queensland, {qname(q0)} to {qname(q1)}:\n")
    rows = [[TRIAGE_NAME[t], f"{by.loc[t, 'share_0']:.1f}%", f"{by.loc[t, 'share_1']:.1f}%", f"{by.loc[t, 'rate_0']:.1f}%",
             f"{by.loc[t, 'rate_1']:.1f}%", sg(by.loc[t, "mix"]), sg(by.loc[t, "within"])] for t in P.TRIAGE_1_TO_5]
    rows.append(["**All**", "100.0%", "100.0%", f"{d['rate_0']:.1f}%", f"{d['rate_1']:.1f}%",
                 f"**{sg(d['mix'])}**", f"**{sg(d['within'])}**"])
    A(table(["Triage category", f"Share, {qname(q0)}", f"Share, {qname(q1)}", f"Within 4 h, {qname(q0)}",
             f"Within 4 h, {qname(q1)}", "Mix effect (points)", "Within-category effect (points)"], rows) + "\n")
    mg = r["margin"][STAY]
    assert d["change"] < 0 and d["mix"] < 0 and d["within"] < d["mix"]
    assert all(by["rate_1"] < by["rate_0"])
    worst_within = by["within"].idxmin()
    assert worst_within == by["share_1"].idxmax() and 100 / 3 < M.share_of_change(d["mix"], d["change"]) < 40
    A(f"- Stays within 4 hours fell **{abs(d['change']):.2f} points** ({d['rate_0']:.1f}% to {d['rate_1']:.1f}%).")
    A(f"- **{abs(d['mix']):.2f} points ({pct_of(d['mix'], d['change'])}) is mix**: categories 4 and 5, where most patients leave "
      f"within 4 hours, shrank from {by.loc[['4', '5'], 'share_0'].sum():.1f}% to {by.loc[['4', '5'], 'share_1'].sum():.1f}% of "
      f"attendances, and category 2 grew from {by.loc['2', 'share_0']:.1f}% to {by.loc['2', 'share_1']:.1f}%.")
    A(f"- **{abs(d['within']):.2f} points ({pct_of(d['within'], d['change'])}) is within category**: the 4-hour rate fell in all "
      f"five categories. Category {worst_within} accounts for the most ({sg(by.loc[worst_within, 'within'])} points): it fell from "
      f"{by.loc[worst_within, 'rate_0']:.1f}% to {by.loc[worst_within, 'rate_1']:.1f}% and is the largest category.")
    A(f"- Rounding in the published rates could move the within-category figure by up to {mg['within']:.2f} points and the mix "
      f"figure by less than {max(mg['mix'], 0.01):.2f}.\n")

    dl, ml = lg[STAY], r["margin_long"][STAY]
    lo, hi = abs(dl["mix"]) / (abs(dl["change"]) + ml["within"]), abs(dl["mix"]) / (abs(dl["change"]) - ml["within"])
    A(f"**Over {words[years_long]} years** ({qname(q_long)} to {qname(q1)}) the rebuilt rate fell {abs(dl['change']):.2f} points: "
      f"{abs(dl['mix']):.2f} mix and {abs(dl['within']):.2f} within category. The start quarter is rounded to whole "
      f"percentages, so the within-category figure is good to ±{ml['within']:.2f} points; mix is then {100 * lo:.0f}% to "
      f"{100 * hi:.0f}% of the fall.\n")

    y = r["yoy"][STAY]
    assert (y["mix"] < 0).all()
    first4, last4 = y.head(4), y.tail(4)
    A("**Every year-on-year comparison agrees on the sign of the mix effect.** Each quarter against the same quarter a year "
      "earlier:\n")
    rows = [[f"{qname(a)} to {qname(b)}" + (" *" if a in whole or b in whole else ""), sg(ch), sg(mx), sg(wi)]
            for a, b, ch, mx, wi in y[["quarter_0", "quarter_1", "change", "mix", "within"]].itertuples(index=False)]
    A(table(["Comparison", "Change (points)", "Mix", "Within category"], rows) + "\n")
    A("\\* one or both quarters published in whole percentages; the within-category figure is good to about half a point.\n")
    n_within_neg = int((y["within"] < 0).sum())
    A(f"- Mix lowered the rate in {len(y)} of {len(y)} comparisons, and the pull is growing: it averaged "
      f"{abs(first4['mix'].mean()):.2f} points a year in the first four comparisons and {abs(last4['mix'].mean()):.2f} in the "
      "last four.")
    A(f"- The within-category effect was negative in {n_within_neg} of {len(y)} and is the larger of the two in "
      f"{int((y['within'].abs() > y['mix'].abs()).sum())} of {len(y)}.\n")

    f = r["fixed"]
    A(f"Another way to see it: hold each category's share at its {qname(f['quarter'].iloc[0])} level and apply each "
      f"quarter's own category rates. On that fixed mix the {qname(q1)} figure would be {f['fixed_mix'].iloc[-1]:.1f}% instead of "
      f"{f['rebuilt'].iloc[-1]:.1f}%: {f['fixed_mix'].iloc[-1] - f['rebuilt'].iloc[-1]:.1f} points higher, but still "
      f"{f['rebuilt'].iloc[0] - f['fixed_mix'].iloc[-1]:.1f} points below where it started ({f['rebuilt'].iloc[0]:.1f}%). "
      "(This uses start-quarter shares over the whole period, so it does not match the two-quarter splits above to the "
      "decimal.)\n")
    A("![Actual against fixed mix](charts/04_fixed_mix.png)\n")

    A("## 3. The other measures\n")
    rows = []
    for m in (STAY, ADM4, SEEN, ADM):
        x = st[m]
        rows.append([LABEL[m], f"{x['rate_0']:.1f}%", f"{x['rate_1']:.1f}%", sg(x["change"]), sg(x["mix"]), sg(x["within"])])
    A(table(["Measure (rebuilt from categories)", qname(q0), qname(q1), "Change (points)", "Mix", "Within category"], rows) + "\n")
    se, a4, ad = st[SEEN], st[ADM4], st[ADM]
    b2 = ad["by_category"].loc["2"]
    assert se["mix"] < 0 < se["within"] and abs(a4["mix"]) < 0.2 and ad["mix"] > 0 > ad["within"]
    assert all(a4["by_category"]["rate_1"] < a4["by_category"]["rate_0"])
    assert se["by_category"].loc["3", "within"] > se["within"] / 2
    assert ad["by_category"]["within"].idxmin() == "2" and ad["by_category"].loc["2", "within"] < ad["within"]
    A(f"- **Seen on time: the front-door gain is larger than the headline.** The rate rose {se['change']:.2f} points, but the "
      f"mix pulled it down by {abs(se['mix']):.2f}; within categories the gain was {se['within']:.2f} points, most of it in "
      f"category 3 ({se['by_category'].loc['3', 'rate_0']:.1f}% to {se['by_category'].loc['3', 'rate_1']:.1f}%).")
    ys = r["yoy"][SEEN]
    neg = ys[ys["within"] < 0]
    A(f"  It is not a steady gain, though: the within-category effect was negative in {len(neg)} of {len(ys)} year-on-year "
      f"comparisons, all {len(neg)} of them ending between {qname(neg['quarter_1'].min())} and {qname(neg['quarter_1'].max())}.")
    A(f"- **Admitted patients: none of the fall is mix.** The share of admitted patients whose ED stay was within 4 hours fell "
      f"{abs(a4['change']):.2f} points, {abs(a4['within']):.2f} of it within category. It fell in all five categories. "
      "Admitted patients are spread across triage categories much as they were, so the mix cannot explain it.")
    A(f"- **Admissions: the mix effect is partly offset.** A more urgent mix alone would have lifted the admitted share by "
      f"{ad['mix']:.2f} points. It rose {ad['change']:.2f}, largely because the admission rate *within* category 2 fell from "
      f"{b2['rate_0']:.1f}% to {b2['rate_1']:.1f}%.\n")
    A("![Mix and within-category effects](charts/05_mix_vs_within.png)\n")

    A("## 4. Is the mix shift real?\n")
    s2 = by.loc["2"]
    A(f"The last point matters. Category 2 grew from {s2['share_0']:.1f}% to {s2['share_1']:.1f}% of attendances while a smaller "
      f"share of its patients were admitted ({b2['rate_0']:.1f}% to {b2['rate_1']:.1f}%). That is what you would see if some "
      "patients who used to be triaged as category 3 are now triaged as category 2. It is also what you would see if "
      "more genuinely urgent patients arrive who do not need a bed. Quarterly totals cannot separate the two, and this split "
      f"only sees how sick a patient is through the triage category. So the mix effect of {abs(d['mix']):.2f} points cannot "
      "be read straight off as \"sicker patients\".\n")
    sp = r["adm_split"]
    sb = sp["by_category"]
    assert sp["mix"] < 0 and sb.loc["not admitted", "within"] < sb.loc["admitted", "within"] < 0
    A("A second split does not rely on triage at all. It treats each quarter as two groups, admitted and not admitted. The "
      "4-hour rate of patients who were not admitted is not published, but the three published figures imply it "
      "(stays = admitted share × admitted rate + the rest × the not-admitted rate):\n")
    rows = [[k.capitalize(), f"{sb.loc[k, 'share_0']:.1f}%", f"{sb.loc[k, 'share_1']:.1f}%", f"{sb.loc[k, 'rate_0']:.1f}%",
             f"{sb.loc[k, 'rate_1']:.1f}%", sg(sb.loc[k, "mix"]), sg(sb.loc[k, "within"])] for k in sb.index]
    rows.append(["**All**", "100.0%", "100.0%", f"{sp['rate_0']:.1f}%", f"{sp['rate_1']:.1f}%", f"**{sg(sp['mix'])}**",
                 f"**{sg(sp['within'])}**"])
    A(table(["Group", f"Share, {qname(q0)}", f"Share, {qname(q1)}", f"Within 4 h, {qname(q0)}", f"Within 4 h, {qname(q1)}",
             "Mix effect (points)", "Within-group effect (points)"], rows) + "\n")
    A(f"- The not-admitted rates are implied, not published, and are good to about ±{r['adm_margin']:.1f} points given the "
      "rounding of the inputs. They also rest on reading \"admissions to hospital within 4 hours\" as the share of "
      "admitted patients whose ED stay was within 4 hours.")
    A(f"- On this split only {abs(sp['mix']):.2f} of the {abs(sp['change']):.1f} points ({pct_of(sp['mix'], sp['change'])}) "
      "comes from admitting a larger share of patients.")
    A(f"- **Patients who were not admitted account for more of the fall than patients who were**: "
      f"{abs(sb.loc['not admitted', 'within']):.2f} points against {abs(sb.loc['admitted', 'within']):.2f}. Their rate fell "
      f"less ({sb.loc['not admitted', 'rate_0']:.1f}% to {sb.loc['not admitted', 'rate_1']:.1f}%, against "
      f"{sb.loc['admitted', 'rate_0']:.1f}% to {sb.loc['admitted', 'rate_1']:.1f}%), but they are "
      f"{sb.loc['not admitted', 'share_1']:.0f}% of attendances.\n")
    A(f"The two splits put mix at {pct_of(sp['mix'], sp['change'])} and {pct_of(d['mix'], d['change'])} of the fall. In both, "
      "the larger part is patients in the same group taking longer.\n")

    A("## 5. Large hospitals: mostly within category, not mix\n")
    gl, gr = r["groups"]["large"], r["groups"]["rest"]
    rows = []
    for name, grp, k in ((f"{LARGE:,} or more attendances", gl, len(r["big"])), (f"Under {LARGE:,}", gr, len(r["rest"]))):
        x = grp[STAY]
        rows.append([name, str(k), f"{x['rate_0']:.1f}%", f"{x['rate_1']:.1f}%", sg(x["change"]), sg(x["mix"]), sg(x["within"])])
    A(table([f"Hospitals by attendances in {qname(q1)}", "Hospitals", f"Within 4 h, {qname(q0)}", f"Within 4 h, {qname(q1)}",
             "Change (points)", "Mix", "Within category"], rows) + "\n")
    xl, xr = gl[STAY], gr[STAY]
    assert abs(xl["within"]) > abs(xl["mix"]) and abs(xr["mix"]) > abs(xr["within"]) and xl["change"] < xr["change"] < 0
    note = (f" {len(r['only_end'])} hospital that first reports in {qname(q1)} is left out." if len(r["only_end"]) == 1
            else f" {len(r['only_end'])} hospitals without both quarters are left out.")
    A(f"Each group's hospitals are added together, category by category.{note}\n")
    A(f"- At the **{len(r['big'])} large hospitals** the 4-hour rate fell {abs(xl['change']):.2f} points and "
      f"{abs(xl['within']):.2f} of that ({pct_of(xl['within'], xl['change'])}) is within category.")
    A(f"- At the **other {len(r['rest'])}** it fell {abs(xr['change']):.2f} points and {abs(xr['mix']):.2f} of that "
      f"({pct_of(xr['mix'], xr['change'])}) is mix: like for like, they are close to where they were.")
    sl, sr = gl[SEEN], gr[SEEN]
    A(f"- Seen on time, within category: {sg(sl['within'])} points at the large hospitals and {sg(sr['within'])} at the rest.\n")

    hs = r["hospitals"][STAY]
    assert len(hs) == len(r["big"])
    fell, rose = hs[hs["change"] < 0], hs[hs["change"] > 0]
    big_fall = hs[hs["change"] <= -5]
    same_sign = int(((hs["within"] < 0) == (hs["change"] < 0)).sum())
    mix_major = int((hs["mix"].abs() > hs["within"].abs()).sum())
    A(f"### The {len(hs)} large hospitals, {qname(q0)} to {qname(q1)}\n")
    rows = [[x.facility_name, f"{x.attendances:,}", f"{x.published_0:.1f}%", f"{x.published_1:.1f}%", sg(x.change, 1),
             sg(x.mix, 1), sg(x.within, 1), f"{x.urgent_share_0:.1f}%", f"{x.urgent_share_1:.1f}%"]
            for x in hs.itertuples(index=False)]
    A(table(["Hospital", f"Attendances, {qname(q1)}", f"Within 4 h, {qname(q0)}", f"Within 4 h, {qname(q1)}", "Change (points)",
             "Mix", "Within category", f"Categories 1-2 share, {qname(q0)}", f"Categories 1-2 share, {qname(q1)}"], rows) + "\n")
    top, best = hs.iloc[0], hs.iloc[-1]
    up = hs.assign(d=hs["urgent_share_1"] - hs["urgent_share_0"]).sort_values("d", ascending=False, kind="stable").iloc[0]
    A(f"- **{len(fell)} of {len(hs)} fell and {len(rose)} rose.** {len(big_fall)} fell by 5 points or more, led by "
      f"{top.facility_name} ({top.published_0:.1f}% to {top.published_1:.1f}%). {best.facility_name} improved the most "
      f"({best.published_0:.1f}% to {best.published_1:.1f}%).")
    A(f"- **Mix is the larger effect at {mix_major} of {len(hs)}**, and the within-category effect has the same sign as the "
      f"total change at {same_sign} of {len(hs)}. The spread in the within-category effect ({sg(hs['within'].min(), 1)} to "
      f"{sg(hs['within'].max(), 1)} points) is far wider than in the mix effect ({sg(hs['mix'].min(), 1)} to "
      f"{sg(hs['mix'].max(), 1)}).")
    A(f"- **The triage shift is uneven.** Categories 1 and 2 together went from {up.urgent_share_0:.1f}% to "
      f"{up.urgent_share_1:.1f}% of attendances at {up.facility_name}, the largest rise; at "
      f"{int(((hs['urgent_share_1'] - hs['urgent_share_0']).abs() < 1).sum())} of the {len(hs)} the share moved by less than a point.\n")
    A("![Large hospitals](charts/06_large_hospitals.png)\n")

    hsn = r["hospitals"][SEEN]
    m = hs.merge(hsn[["facility_code", "within"]], on="facility_code", suffixes=("", "_seen"))
    both_down = m[(m["within"] < 0) & (m["within_seen"] < 0)]
    split = m[(m["within"] < 0) & (m["within_seen"] > 0)]
    both_up = m[(m["within"] > 0) & (m["within_seen"] > 0)]
    assert len(split) + len(both_down) + len(both_up) == len(m)
    A("### Front door and back door\n")
    A(f"Within category, over the same two years, at the {len(m)} large hospitals:\n")
    A(f"- **{len(split)}** got better at seeing patients on time and worse on 4-hour stays (for example "
      f"{', '.join(split.sort_values('within', kind='stable')['facility_name'].head(3))}).")
    A(f"- **{len(both_down)}** got worse on both ({', '.join(both_down.sort_values('within_seen', kind='stable')['facility_name'].head(3))} "
      "had the largest falls in patients seen on time).")
    A(f"- **{len(both_up)}** got better on both ({', '.join(both_up.sort_values('within', ascending=False, kind='stable')['facility_name'])}).\n")
    corr = float(m["within"].corr(m["within_seen"]))
    assert 0.3 < corr < 0.6
    A(f"Across the {len(m)}, the correlation between the two within-category effects is {corr:.2f}: a moderate link, with "
      f"{len(split)} hospitals moving in opposite directions. A better front door does not by itself bring back the 4-hour "
      "rate. Part 4 looks at both, hospital by hospital.\n")

    A("## 6. What this means\n")
    A(f"1. **Do not explain the 4-hour fall away as \"sicker patients\".** On the triage split, mix is "
      f"{pct_of(d['mix'], d['change'])} of the two-year fall; on the admitted split it is {pct_of(sp['mix'], sp['change'])}. "
      "Either way most of it is patients in the same group taking longer.")
    A("2. **Report within-category rates next to the headline.** The headline understates the gain in patients seen on time "
      "and overstates the loss in 4-hour stays, and the yearly pull from the mix has grown.")
    A(f"3. **Look at the large hospitals one at a time.** As a group their fall is {pct_of(xl['within'], xl['change'])} within "
      f"category, but {len(rose)} of the {len(hs)} improved while {len(big_fall)} fell by 5 points or more. A state average "
      "hides both.")
    A(f"4. **The fall is not only among admitted patients.** Admitted patients' 4-hour rate fell the most, but patients who were not "
      f"admitted account for {abs(sb.loc['not admitted', 'within']):.2f} of the {abs(sp['change']):.1f} points. Part 1's "
      "\"back door\" reading needs that correction: patients who are not admitted are leaving later too.")
    A("5. **Check triage practice before crediting or blaming the mix.** Category 2 is growing while a smaller share of it "
      "is admitted. A hospital can find out which explanation holds from its own patient-level records; this data cannot.\n")

    A("## 7. Rules carried into Part 3\n")
    A("1. Score hospitals on within-category change, not on the all-categories figure.")
    A(f"2. Compare {qname(q0)} with {qname(q1)} (both one decimal); use earlier quarters only with the half-point margin.")
    A("3. \"Seen within the recommended time\" does not rebuild exactly from its categories. Use changes, not levels, from "
      "the rebuilt figure.")
    A("4. The not-admitted 4-hour rate is implied, not published. Label it that way wherever it appears.")
    A("")

    yo = r["yoy"][STAY].assign(measure=STAY)
    ys_ = r["yoy"][SEEN].assign(measure=SEEN)
    state_rows = []
    for label, src, a_q in (("main", st, q0), ("long", lg, q_long)):
        for meas, x in src.items():
            state_rows.append({"comparison": label, "quarter_0": a_q, "quarter_1": q1, "measure": meas,
                               "rate_0": x["rate_0"], "rate_1": x["rate_1"], "change": x["change"],
                               "mix": x["mix"], "within": x["within"]})
    cat = pd.concat([x["by_category"].reset_index(names="triage").assign(measure=meas) for meas, x in st.items()])
    csvs = {
        "mix_state.csv": pd.DataFrame(state_rows).round(4),
        "mix_state_by_category.csv": cat[["measure", "triage", "share_0", "share_1", "rate_0", "rate_1", "mix", "within"]].round(4),
        "mix_year_on_year.csv": pd.concat([yo, ys_])[["measure", "quarter_0", "quarter_1", "rate_0", "rate_1", "change",
                                                      "mix", "within"]].round(4),
        "mix_fixed_series.csv": r["fixed"].round(4),
        "mix_large_hospitals.csv": m.rename(columns={"within_seen": "seen_on_time_within"}).round(4),
    }
    return "\n".join(L), csvs


def main() -> int:
    df = load.read_snapshot(DATA / "ed_quarterly.csv")
    r = analyse(df)
    CHARTS.mkdir(parents=True, exist_ok=True)
    report, csvs = build_report(r)
    (RESULTS / "MIX_VS_PERFORMANCE.md").write_text(report, encoding="utf-8")
    for name, frame in csvs.items():
        frame.to_csv(RESULTS / name, index=False, lineterminator="\n", float_format="%.10g")
    chart_fixed_mix(r["fixed"], r["quarters"][0], CHARTS / "04_fixed_mix.png")
    chart_effects(r["state"], r["q0"], r["q1"], CHARTS / "05_mix_vs_within.png")
    chart_hospitals(r["hospitals"][STAY], r["q0"], r["q1"], CHARTS / "06_large_hospitals.png")
    print(f"wrote results/MIX_VS_PERFORMANCE.md, {len(csvs)} CSVs, 3 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
