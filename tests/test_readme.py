"""The README may only quote figures that the generated report contains."""
import re

import pytest

NUMBER = re.compile(r"(?<![\w.,-])[+-]?\d[\d,]*(?:\.\d+)?%?")
# figures in the README that describe the repo or the source, not results
ALLOWED = {
    "1", "2", "3", "4", "5", "4.0", "14", "2020", "2022", "2023", "2026", "1.0", "0.6", "10,000",
    "104", "105", "8,826", "22", "83", "256",
}


@pytest.fixture(scope="module")
def readme(root) -> str:
    return (root / "README.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def report(root) -> str:
    return (root / "results" / "SOURCE_PROFILE.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def mix_report(root) -> str:
    return (root / "results" / "MIX_VS_PERFORMANCE.md").read_text(encoding="utf-8")


def results_section(readme: str) -> str:
    start = readme.index("## Part 1")
    return readme[start:readme.index("## Part 2")]


def part2_section(readme: str) -> str:
    start = readme.index("## Part 2")
    return readme[start:readme.index("## Part 3")]


def part3_section(readme: str) -> str:
    start = readme.index("## Part 3")
    return readme[start:readme.index("## Part 4")]


def part4_section(readme: str) -> str:
    start = readme.index("## Part 4")
    return readme[start:readme.index("## Part 5")]


def part5_section(readme: str) -> str:
    start = readme.index("## Part 5")
    return readme[start:readme.index("## How to run")]


def tokens(text: str) -> set[str]:
    return {t.lstrip("+").rstrip(",") for t in NUMBER.findall(text)}


def test_every_result_figure_is_in_the_report(readme, report):
    have = tokens(report)
    missing = sorted(t for t in tokens(results_section(readme)) if t not in have and t not in ALLOWED)
    assert not missing, f"README figures not found in SOURCE_PROFILE.md: {missing}"


@pytest.mark.parametrize("readme_phrase, report_phrase", [
    ("| Seen within the recommended time | 71% | 74.6% |", "| Seen within the clinically recommended time | 71% | 74.6% |"),
    ("| ED stay within 4 hours | 61% | 56.1% |", "| ED stay within 4 hours | 61% | 56.1% |"),
    ("| Admissions to hospital within 4 hours | 37% | 31.3% |", "| Admissions to hospital within 4 hours | 37% | 31.3% |"),
    ("| Attendances | 584,431 | 593,177 |", "| Attendances | 584,431 | 593,177 |"),
    ("| Median wait to treatment | 17 min | 14 min |", "| Median wait to treatment (minutes) | 17 | 14 |"),
    ("Attendances are up only 1.5%", "(+1.5% on the same quarter three years earlier)"),
    ("Triage category 2 rose from 16.8% to 20.0%", "Category 2 went from 16.8% of attendances in Apr-Jun 2023 to 20.0%"),
    ("categories 4 and 5 together fell from 40.4% to 36.2%", "categories 4 and 5 together went from 40.4% to 36.2%"),
    ("22 of 105 hospitals had 10,000 or more attendances and handled 70.2%", "They handled **70.2%**"),
    ("At those hospitals 45.7% of stays were within 4 hours; at the other 83 it was 80.6%",
     "45.7% of stays at the large hospitals were within 4 hours, against 80.6% at the rest"),
    ("The median hospital is at 86.9%, nowhere near the state's 56.1%", "the median across all 105 is 86.9%"),
    ("in 1,471 of 1,471 hospital-quarters", "in 1,471 of 1,471 hospital-quarters"),
    ("in 14 of 14 quarters", "in 14 of 14 quarters"),
    ("in 6,115 of 6,157 rows. The 42 that do not are in two quarters", "for 6,157 rows: 6,115 agree to the published rounding. The 42 that do not are all in two quarters"),
    ("the published change is +5.0%, but the two quarters' own attendance figures give +22.0%",
     "| Nambour | Oct-Dec 2025 | 18,115 | 14,849 | +22.0% | +5.0% |"),
    ("for 105 of 106 facility codes", "105 of 106 facility codes"),
    ("whole numbers in the first 5 quarters", "whole numbers in the 5 quarters to Jan-Mar 2024"),
    ("In 4 quarters a zero is published as `-`", "In 4 quarters (Apr-Jun 2023 to Jan-Mar 2024) a **zero is published as `-`**"),
    ("eight rules", "8. **An empty"),
    ("the plain average of hospital 4-hour figures is 79.2%, against 56.1% for the state",
     "is 79.2%; the state figure is 56.1%"),
    ("14 quarters, Jan-Mar 2023 to Apr-Jun 2026", "**14 quarters**, Jan-Mar 2023 to Apr-Jun 2026; **8,826 rows**"),
    ("104 reporting hospitals (105 from Apr-Jun 2026)", "**104 hospitals** in every quarter"),
])
def test_readme_statement_is_backed_by_the_report(readme, report, readme_phrase, report_phrase):
    assert readme_phrase in readme
    assert report_phrase in report


def test_every_part2_figure_is_in_the_mix_report(readme, mix_report):
    have = tokens(mix_report)
    missing = sorted(t for t in tokens(part2_section(readme)) if t not in have and t not in {"2"})
    assert not missing, f"README figures not found in MIX_VS_PERFORMANCE.md: {missing}"


@pytest.mark.parametrize("readme_phrase, report_phrase", [
    ("| ED stay within 4 hours | −3.05 | −1.14 | −1.91 |", "| ED stay within 4 hours | 59.1% | 56.1% | −3.05 | −1.14 | −1.91 |"),
    ("| Admitted patients: ED stay within 4 hours | −3.10 | −0.06 | −3.04 |",
     "| Admitted patients: ED stay within 4 hours | 34.4% | 31.3% | −3.10 | −0.06 | −3.04 |"),
    ("| Seen within the recommended time | +1.30 | −0.48 | +1.78 |",
     "| Seen within the recommended time | 73.6% | 74.9% | +1.30 | −0.48 | +1.78 |"),
    ("Apr-Jun 2024 to Apr-Jun 2026, the longest same-quarter span published to one decimal place",
     "**Apr-Jun 2024 to Apr-Jun 2026**: the same quarter two years apart, and the longest like-for-like span"),
    ("A more urgent mix is 37% of the fall in 4-hour stays", "**1.14 points (37%) is mix**"),
    ("The other 63% is within category", "**1.91 points (63%) is within category**"),
    ("The 4-hour rate fell in all five triage categories", "the 4-hour rate fell in all five categories"),
    ("Mix lowered the rate in 10 of 10 year-on-year comparisons, and its pull is growing",
     "Mix lowered the rate in 10 of 10 comparisons, and the pull is growing"),
    ("held at its Jan-Mar 2023 level, the Apr-Jun 2026 figure would be 57.8% instead of 56.1%",
     "hold each category's share at its Jan-Mar 2023 level and apply each quarter's own category rates. "
     "On that fixed mix the Apr-Jun 2026 figure would be 57.8% instead of 56.1%"),
    ("Patients seen on time rose 1.30 points, but the mix pulled that down by 0.48: within categories the gain was 1.78 points",
     "The rate rose 1.30 points, but the mix pulled it down by 0.48; within categories the gain was 1.78 points"),
    ("the within-category effect was negative in 3 of 10 year-on-year comparisons",
     "the within-category effect was negative in 3 of 10 year-on-year comparisons"),
    ("Admitted patients' 4-hour rate fell from 34.5% to 31.3%", "| Admitted | 28.1% | 29.0% | 34.5% | 31.3% |"),
    ("the published figures imply 68.7% falling to 66.2%", "| Not admitted | 71.9% | 71.0% | 68.7% | 66.2% |"),
    ("because those patients are 71% of attendances they account for 1.78 of the 3.0 points, against 0.91 for admitted patients",
     "1.78 points against 0.91. Their rate fell less (68.7% to 66.2%, against 34.5% to 31.3%), but they are 71% of attendances"),
    ("At the 22 large hospitals the 4-hour rate fell 3.47 points and 83% of that is within category",
     "At the **22 large hospitals** the 4-hour rate fell 3.47 points and 2.87 of that (83%) is within category"),
    ("At the other 82 it fell 1.43 points and 80% of that is mix",
     "At the **other 82** it fell 1.43 points and 1.14 of that (80%) is mix"),
    ("Among the 22, 18 fell (9 of them by 5 points or more, led by Sunshine Coast University, 49.8% to 41.4%)",
     "**18 of 22 fell and 4 rose.** 9 fell by 5 points or more, led by Sunshine Coast University (49.8% to 41.4%)"),
    ("and 4 rose (Queensland Children's most, 63.2% to 70.8%)", "Queensland Children's improved the most (63.2% to 70.8%)"),
    ("Category 2 grew from 17.9% to 20.0% of attendances while a smaller share of its patients were admitted (50.6% to 47.6%)",
     "Category 2 grew from 17.9% to 20.0% of attendances while a smaller share of its patients were admitted (50.6% to 47.6%)"),
    ("The triage split puts mix at 37% of the fall and the admitted split puts it at 10%",
     "The two splits put mix at 10% and 37% of the fall"),
    ("two lost about 8 points", "| Sunshine Coast University | 24,756 | 49.8% | 41.4% | −8.3 |"),
    ("two lost about 8 points", "| Queen Elizabeth II | 14,971 | 45.3% | 37.3% | −8.0 |"),
    ("one gained more than 7", "| Queensland Children's | 17,413 | 63.2% | 70.8% | +7.6 |"),
    ("the rebuilt figure is about 0.3 points higher", "the rebuilt figure is 0.26 to 0.37 points above the published one"),
])
def test_part2_statement_is_backed_by_the_mix_report(readme, mix_report, readme_phrase, report_phrase):
    assert readme_phrase in readme
    assert report_phrase in mix_report


def test_part2_extremes_among_large_hospitals(root):
    """'two lost about 8 points and one gained more than 7': no other large hospital did."""
    import pandas as pd
    h = pd.read_csv(root / "results" / "mix_large_hospitals.csv")
    assert int((h["change"] <= -7.75).sum()) == 2 and int((h["change"] > 7).sum()) == 1
    assert h["change"].min() > -8.5


@pytest.fixture(scope="module")
def scorecard_report(root) -> str:
    return (root / "results" / "HOSPITAL_SCORECARD.md").read_text(encoding="utf-8")


def test_every_part3_figure_is_in_the_scorecard_report(readme, scorecard_report):
    have = tokens(scorecard_report)
    missing = sorted(t for t in tokens(part3_section(readme)) if t not in have and t not in {"3"})
    assert not missing, f"README figures not found in HOSPITAL_SCORECARD.md: {missing}"


@pytest.mark.parametrize("readme_phrase, report_phrase", [
    ("| Large (10,000 or more) | 22 | 44.3% | 16 | 2 | 4 |", "| Large | 22 | 16 | 2 | 4 | ±1.3 |"),
    ("| Large (10,000 or more) | 22 | 44.3% |", "| Large (10,000 or more) | 22 | 70.2% | 45.7% | 44.3% |"),
    ("| Medium (2,500 to 9,999) | 26 | 77.5% | 10 | 10 | 5 |", "| Medium | 25 | 10 | 10 | 5 | ±2.1 |"),
    ("| Medium (2,500 to 9,999) | 26 | 77.5% |", "| Medium (2,500 to 9,999) | 26 | 20.3% | 75.7% | 77.5% |"),
    ("| Small (under 2,500) | 57 | 92.7% | 9 | 45 | 3 |", "| Small | 57 | 9 | 45 | 3 | ±2.9 |"),
    ("| Small (under 2,500) | 57 | 92.7% |", "| Small (under 2,500) | 57 | 9.5% | 91.1% | 92.7% |"),
    ("Mater Springfield, first reports in Apr-Jun 2026 and has a level but no trend",
     "Mater Springfield first reports in Apr-Jun 2026, so it has a level but no trend"),
    ("\"Below peers\" means the lowest quarter of the group", "is in the lowest quarter of its group"),
    ("from Apr-Jun 2024 to Apr-Jun 2026", "**Trend: the within-category change**, Apr-Jun 2024 to Apr-Jun 2026"),
    ("a **chance bar** of ±2.58 standard errors", "Each change is compared with ±2.58 standard errors"),
    ("35 of 104 hospitals slipped by more than chance, and 12 improved",
     "**35 of 104 hospitals slipped by more than chance and 12 improved.**"),
    ("Slipping is the norm among large hospitals: 16 of 22", "**Slipping is the norm among large hospitals**: 16 of 22"),
    ("roughly 14,800 more stays over 4 hours in the quarter than their Apr-Jun 2024 category rates would give",
     "at the 16 slipping large hospitals the within-category falls add up to roughly 14,800 more stays over 4 hours in the "
     "quarter than their Apr-Jun 2024 category rates would give"),
    ("Queen Elizabeth II fell the most within category (−8.2 points) and Queensland Children's gained the most (+9.0)",
     "**Queen Elizabeth II** has the largest within-category fall (−8.2 points) and **Queensland Children's** the largest gain (+9.0)"),
    ("On the published figure 74 of 104 hospitals fell", "On the published all-categories figure, 74 of 104 fell"),
    ("45 of 57 small hospitals show no change that chance could not produce", "45 of 57 small hospitals show no clear change"),
    ("about ±2.9 points, against ±1.3 for a large one", "A small hospital's bar is about ±2.9 points, against ±1.3 for a large one"),
    ("12 hospitals are below their peers and slipping (5 large, 2 medium, 5 small)", "These 12 (5 large, 2 medium, 5 small)"),
    ("Another 8 are in the top quarter of their group and slipping",
     "8 hospitals are in the top quarter of their group and slipping"),
    ("And 3 are in the lowest quarter and improving: Caboolture, Gympie and Kingaroy",
     "3 are in the lowest quarter and improving: Caboolture, Gympie, Kingaroy"),
    ("Of the 12 improving on 4-hour stays, 11 are also improving on patients seen on time and none is slipping",
     "Of the 12 improving on 4-hour stays, 11 are also improving on seeing patients on time and none is slipping"),
    ("of the 35 slipping on 4-hour stays, 7 are improving on patients seen on time",
     "Of the 35 hospitals slipping on 4-hour stays, 16 are also slipping on seeing patients on time and 7 are *improving* on it"),
    ("the state figure of 56.1% puts 20 of the 22 large hospitals below it and all 57 small hospitals above it",
     "Against the state figure of 56.1%, 20 of the 22 large hospitals are below and all 57 small hospitals are above"),
])
def test_part3_statement_is_backed_by_the_scorecard_report(readme, scorecard_report, readme_phrase, report_phrase):
    assert readme_phrase in part3_section(readme)
    assert report_phrase in scorecard_report


def test_part3_large_priority_hospitals_named_in_readme(readme, root):
    """The five large hospitals the README names are exactly the large rows of the priority CSV."""
    import pandas as pd
    pri = pd.read_csv(root / "results" / "scorecard_priority.csv")
    large = list(pri.loc[pri["peer_group"] == "large", "facility_name"])
    assert len(pri) == 12 and len(large) == 5
    sentence = "the five large ones are Queen Elizabeth II, Hervey Bay, Bundaberg, Royal Brisbane & Women's and Princess Alexandra"
    assert sentence in readme
    assert all(name in sentence for name in large)


@pytest.fixture(scope="module")
def doors_report(root) -> str:
    return (root / "results" / "FRONT_VS_BACK_DOOR.md").read_text(encoding="utf-8")


def test_every_part4_figure_is_in_the_doors_report(readme, doors_report):
    have = tokens(doors_report)
    missing = sorted(t for t in tokens(part4_section(readme)) if t not in have and t not in {"3", "4"})
    assert not missing, f"README figures not found in FRONT_VS_BACK_DOOR.md: {missing}"


@pytest.mark.parametrize("readme_phrase, report_phrase", [
    ("| Queensland | −3.05 | −1.14 | −0.02 | −0.87 | −1.02 |", "| Queensland | 59.1% | 56.1% | −3.05 | −1.14 | −0.02 | −0.87 | −1.02 |"),
    ("| Large hospitals | −3.47 | −0.60 | −0.15 | −1.07 | −1.65 |",
     "| Large hospitals | 49.2% | 45.7% | −3.47 | −0.60 | −0.15 | −1.07 | −1.65 |"),
    ("| Medium hospitals | −1.78 | −1.51 | +0.17 | −0.51 | +0.07 |",
     "| Medium hospitals | 78.3% | 76.5% | −1.78 | −1.51 | +0.17 | −0.51 | +0.07 |"),
    ("| Small hospitals | −1.16 | −0.46 | +0.04 | −0.19 | −0.56 |",
     "| Small hospitals | 92.3% | 91.1% | −1.16 | −0.46 | +0.04 | −0.19 | −0.56 |"),
    ("from Apr-Jun 2024 to Apr-Jun 2026 is split four ways, with nothing left over",
     "from Apr-Jun 2024 to Apr-Jun 2026 is split exactly into"),
    ("It is implied by three published figures", "it is the rate implied by the published stay rate, admitted share and admitted 4-hour rate"),
    ("Admitted patients are 29.0% of attendances and 45% of the within-category fall",
     "They are 29.0% of attendances and 45% of the within-category fall"),
    ("Their 4-hour rate went from 34.4% to 31.3%; the implied rate for everyone else went from 68.8% to 66.2%",
     "Their own 4-hour rate went from 34.4% to 31.3%; the implied rate for everyone else went from 68.8% to 66.2%"),
    ("Part 2 put 1.78 points on patients who were not admitted; with triage held fixed it is 1.02",
     "put 1.78 points on patients who were not admitted and 0.91 on admitted patients. With triage held fixed the "
     "not-admitted part is 1.02 points"),
    ("At 15 of the 16 slipping large hospitals, patients who were not admitted left later too",
     "So the not-admitted stream is slipping at 15 of the 16"),
    ("11 are slipping in both streams, 4 only among patients who were not admitted (Mackay, Rockhampton, Robina and "
     "Princess Alexandra) and 1 only among admitted patients (Nambour)",
     "Of the 16 slipping large hospitals, 11 are slipping in both streams, 4 only among patients who were not admitted "
     "(Mackay, Rockhampton, Robina and Princess Alexandra) and 1 only among admitted patients (Nambour)"),
    ("The 4 improving large hospitals all gained most among patients who were not admitted",
     "**The 4 improving large hospitals all improved among patients who were not admitted**, and at each of them that "
     "stream is the larger part of the gain"),
    ("correlation 0.64 across the 22 large hospitals", "(correlation 0.64 across the 22 large hospitals)"),
    ("did not wait to be seen fell from 3.34% to 2.87%", "the did-not-wait rate fell from 3.34% to 2.87% of attendances"),
    ("Apr-Jun 2024 was a high point", "Apr-Jun 2024 was higher than the year before it, so the two-year fall starts from a high point"),
    ("the medium hospitals' fall came mostly in the latest quarter", "most of the fall to 3.49% happened in the latest quarter"),
    ("The 7 hospitals that slipped on 4-hour stays while improving on patients seen on time all have a shorter median wait, "
     "and all 7 are slipping among patients who were not admitted",
     "The median wait is shorter at 7 of the 7, and every one is slipping among patients who were not admitted"),
    ("In Apr-Jun 2024, 36 hospitals published a median wait of 0 or 1 minute",
     "In Apr-Jun 2024, 36 hospitals (34 small, 2 medium) published a median wait of 0 or 1 minute"),
    ("At 9 of them it had risen to 5 minutes or more by Apr-Jun 2026", "At 9 of them the median had risen to 5 minutes or more by Apr-Jun 2026"),
    ("6 of the 26 hospitals that Part 3 marks as slipping on patients seen on time are in that group",
     "6 of the 26 hospitals that Part 3 marks as slipping on patients seen on time are in this group"),
    ("Of the 35 hospitals slipping on 4-hour stays, 32 are slipping among patients who were not admitted and 23 among admitted patients",
     "Of the 35 hospitals slipping on 4-hour stays, 32 are slipping among patients who were not admitted and 23 among admitted patients"),
])
def test_part4_statement_is_backed_by_the_doors_report(readme, doors_report, readme_phrase, report_phrase):
    assert readme_phrase in part4_section(readme)
    assert report_phrase in doors_report


def test_part4_limitation_about_zero_waits(root):
    """'published by about a third of hospitals': 36 of 104 in the first quarter compared."""
    import pandas as pd
    h = pd.read_csv(root / "results" / "doors_hospitals.csv")
    assert len(h) == 104 and int((h["median_wait_0"] <= 1).sum()) == 36
    assert 0.3 < 36 / 104 < 0.37


# ---- Part 5: the Power BI model ---------------------------------------------

@pytest.fixture(scope="module")
def checks_md(root) -> str:
    return (root / "powerbi" / "CHECKS.md").read_text(encoding="utf-8")


def test_every_part5_figure_is_in_the_check_values_or_the_manifest(readme, checks_md, root):
    import json
    manifest = json.loads((root / "powerbi" / "data" / "MANIFEST.json").read_text())["tables"]
    have = tokens(checks_md) | {f"{t['rows']:,}" for t in manifest.values()}
    # part numbers, and counts tied to their sources in the tests below
    allowed = {"1", "2", "3", "4", "5", "27", "8", "79.2%", "16", "22", "12", "9"}
    missing = sorted(t for t in tokens(part5_section(readme)) if t not in have and t not in allowed)
    assert not missing, f"README Part 5 figures not found in CHECKS.md or MANIFEST.json: {missing}"


@pytest.mark.parametrize("readme_phrase, checks_phrase", [
    ("to within 0.1 points in all 937 hospital-quarters published to one decimal place",
     "| one decimal place | 937 | 0.09 | 937 (within 0.1) |"),
    ("to within 1.0 in all 520 published as whole numbers", "| whole numbers | 520 | 0.83 | 520 (within 1.0) |"),
    ("the model gives 56.12% in Apr-Jun 2026 against the published 56.1%",
     "| Apr-Jun 2026 | 105 | 593,177 | 56.12% | 56.1% |"),
    ("In 83 hospital-quarters a category's admitted share is blank while the hospital's total is published",
     "In 83 hospital-quarters that happens while the all-categories share is published"),
    ("Reading the blank as zero rebuilds the published total in 83 of 83", "| zero (used by the model) | 83 of 83 |"),
    ("dropping the row does so in 62 of 83", "| no data: drop the row | 62 of 83 |"),
    ("At Cunnamulla in Oct-Dec 2023 the model gives 7.85% (published: 8%); dropping the blank rows would give 11.37%",
     "| Cunnamulla | 407 | 7.85% | 11.37% | 8% |"),
    ("16 of 22 large hospitals slipping", "| Large (10,000 or more) | 22 | 16 | 2 | 4 | 5 | 0 |"),
])
def test_part5_statement_is_backed_by_the_check_values(readme, checks_md, readme_phrase, checks_phrase):
    assert readme_phrase in part5_section(readme)
    assert checks_phrase in checks_md


def test_part5_counts_match_the_pack(readme, root):
    import json
    import pandas as pd
    section = part5_section(readme)
    dax = (root / "powerbi" / "measures.dax").read_text(encoding="utf-8")
    assert f"{len(re.findall(r'^    MEASURE ', dax, re.M))} DAX measures" in section
    assert f"{len(re.findall(r'^EVALUATE', dax, re.M))} check queries" in section
    manifest = json.loads((root / "powerbi" / "data" / "MANIFEST.json").read_text())["tables"]
    for table in ("fct_ed_triage_quarter", "fct_hospital_quarter_published", "hospital_scorecard",
                  "state_published_quarter"):
        assert f"| `{table}` | {manifest[table]['rows']:,} |" in section
    dims = ", ".join(str(manifest[t]["rows"]) for t in ("dim_hospital", "dim_quarter", "dim_triage"))
    assert f"| `dim_hospital`, `dim_quarter`, `dim_triage` | {dims} |" in section
    card = pd.read_csv(root / "results" / "scorecard_hospitals.csv")
    doors = pd.read_csv(root / "results" / "doors_hospitals.csv")
    assert ((card["level"] == "below peers") & (card["trend"] == "slipping")).sum() == 12
    assert "12 hospitals below peers and slipping" in section
    assert int(doors["wait_step"].sum()) == 9 and "the 9 hospitals whose median wait stepped up" in section


def test_part5_diagram_is_the_guides_diagram(readme, root):
    guide = (root / "powerbi" / "POWERBI_GUIDE.md").read_text(encoding="utf-8")
    block = re.search(r"```mermaid\n(.*?)```", part5_section(readme), re.S).group(1)
    assert block in guide


def test_part5_average_trap_and_blank_limitation(readme, snapshot):
    latest = snapshot[(snapshot["quarter"] == snapshot["quarter"].max()) & (snapshot["triage"] == "ALL")]
    plain = latest.loc[~latest["is_state_total"], "stay_within_4h_pct"].mean()
    state = latest.loc[latest["is_state_total"], "stay_within_4h_pct"].iloc[0]
    assert f"the plain average of hospital 4-hour figures is {plain:.1f}% for a state at {state:.1f}%" \
        in part5_section(readme)
    # limitation: "13 category rows (24 patients) with a blank 4-hour rate"
    h = snapshot[~snapshot["is_state_total"] & (snapshot["triage"] != "ALL") & (snapshot["attendances"] > 0)]
    blank = h[h["stay_within_4h_pct"].isna()]
    assert (len(blank), int(blank["attendances"].sum())) == (13, 24)
    assert set(blank["quarter"]) == {"2023-06", "2023-09", "2023-12", "2024-03"}
    assert "including 13 category rows (24 patients) with a blank 4-hour rate" in readme


def test_readme_charts_exist(readme, root):
    charts = re.findall(r"\]\((results/charts/[^)]+)\)", readme)
    # 12 charts; chart 07 is shown twice (in the summary and in Part 3)
    assert len(set(charts)) == 12 and len(charts) == 13
    for c in charts:
        assert (root / c).is_file(), c


def test_readme_commands_exist(readme, root):
    for script in re.findall(r"python (scripts/\w+\.py)", readme):
        assert (root / script).is_file(), script


def test_file_sizes_quoted_in_readme(root):
    raw = sum(p.stat().st_size for p in (root / "data" / "raw").glob("*.json"))
    assert round(raw / 1e6, 1) == 1.0
    assert round((root / "data" / "ed_quarterly.csv").stat().st_size / 1e6, 1) == 0.6


# ---- Summary and recommendations --------------------------------------------

def summary_section(readme: str) -> str:
    start = readme.index("## Summary")
    return readme[start:readme.index("## Why it matters")]


def parts_text(readme: str) -> str:
    """Parts 1 to 5, whose figures the tests above tie to the generated reports."""
    return readme[readme.index("## Part 1"):readme.index("## How to run")]


def test_summary_adds_no_figure_of_its_own(readme):
    have = tokens(parts_text(readme))
    # 21 = 83 - 62, checked against CHECKS.md below
    missing = sorted(t for t in tokens(summary_section(readme)) if t not in have and t != "21")
    assert not missing, f"summary figures that Parts 1 to 5 do not contain: {missing}"


@pytest.mark.parametrize("summary_phrase, part_phrase", [
    ("56.1% of ED stays in Queensland were within 4 hours, down from 61% in the same quarter of 2023",
     "| ED stay within 4 hours | 61% | 56.1% |"),
    ("74.6% within the recommended time, up from 71%", "| Seen within the recommended time | 71% | 74.6% |"),
    ("A more urgent mix of patients is 37% of the fall", "A more urgent mix is 37% of the fall in 4-hour stays"),
    ("the 4-hour rate fell 3.05 points: 1.14 from the triage mix and 1.91 within category",
     "| ED stay within 4 hours | −3.05 | −1.14 | −1.91 |"),
    ("The rate fell in all five triage categories", "The 4-hour rate fell in all five triage categories"),
    ("22 hospitals handle 70.2% of attendances",
     "22 of 105 hospitals had 10,000 or more attendances and handled 70.2% of the total"),
    ("16 of those 22 slipped by more than chance", "| Large (10,000 or more) | 22 | 44.3% | 16 | 2 | 4 |"),
    ("roughly 14,800 more stays over 4 hours in the quarter than their Apr-Jun 2024 category rates would give",
     "At those 16 the falls add up to roughly 14,800 more stays over 4 hours in the quarter than their Apr-Jun 2024 "
     "category rates would give"),
    ("Of the 57 small hospitals, 45 show no clear change", "| Small (under 2,500) | 57 | 92.7% | 9 | 45 | 3 |"),
    ("Admitted patients are 29.0% of attendances and 45% of the within-category fall",
     "Admitted patients are 29.0% of attendances and 45% of the within-category fall"),
    ("Of the 35 hospitals slipping on 4-hour stays, 32 are slipping among patients who were not admitted and 23 "
     "among admitted patients",
     "Of the 35 hospitals slipping on 4-hour stays, 32 are slipping among patients who were not admitted and 23 "
     "among admitted patients"),
    ("12 improved by more than chance, Queensland Children's the most (+9.0 points within category)",
     "Queensland Children's gained the most (+9.0)"),
    ("None of the 12 is slipping on patients seen on time",
     "Of the 12 improving on 4-hour stays, 11 are also improving on patients seen on time and none is slipping"),
    ("At 9 hospitals the published median wait stepped up from 0 or 1 minute to 5 minutes or more",
     "36 hospitals published a median wait of 0 or 1 minute. At 9 of them it had risen to 5 minutes or more"),
    ("another 8 hospitals are in the top quarter of their group and slipping",
     "Another 8 are in the top quarter of their group and slipping"),
    ("of the 16 slipping large hospitals, 11 slip in both streams, 4 only among patients who were not admitted "
     "and 1 only among admitted patients",
     "11 are slipping in both streams, 4 only among patients who were not admitted (Mackay, Rockhampton, Robina "
     "and Princess Alexandra) and 1 only among admitted patients (Nambour)"),
    ("Bed managers where only the admitted stream slips, the ED's own tests, reviews and discharge decisions where "
     "only the not-admitted stream slips, and crowding where both do",
     "bed managers where only the admitted stream slips, the ED's own tests, reviews and discharge decisions where "
     "only the not-admitted stream slips, and crowding where both do"),
    ("against the state's 56.1%, 20 of the 22 large hospitals are below and all 57 small hospitals are above",
     "puts 20 of the 22 large hospitals below it and all 57 small hospitals above it"),
    ("4-hour stays −3.05 points, of which −1.91 within category", "| ED stay within 4 hours | −3.05 | −1.14 | −1.91 |"),
    ("seen on time +1.30, of which +1.78 within category", "| Seen within the recommended time | +1.30 | −0.48 | +1.78 |"),
    ("The headline overstates the loss in 4-hour stays and understates the gain in patients seen on time",
     "the headline understates the gain in patients seen on time and overstates the loss in 4-hour stays"),
    ("a small hospital's chance bar is about ±2.9 points, against ±1.3 for a large one",
     "A small hospital's chance bar is about ±2.9 points, against ±1.3 for a large one"),
    ("4 large hospitals improved, all of them most among patients who were not admitted",
     "The 4 improving large hospitals all gained most among patients who were not admitted"),
    ("Caboolture, Gympie and Kingaroy are in the lowest quarter of their group and improving",
     "3 are in the lowest quarter and improving: Caboolture, Gympie and Kingaroy"),
    ("6 of the 26 hospitals marked as slipping on patients seen on time are among the 9 whose median wait stepped up",
     "6 of the 26 hospitals that Part 3 marks as slipping on patients seen on time are in that group"),
    ("the plain average of hospital 4-hour figures is 79.2% for a state at 56.1%",
     "the plain average of hospital 4-hour figures is 79.2% for a state at 56.1%"),
    ("gives 56.12% against the published 56.1%", "the model gives 56.12% in Apr-Jun 2026 against the published 56.1%"),
])
def test_summary_statement_is_backed_by_a_part(readme, summary_phrase, part_phrase):
    assert summary_phrase in summary_section(readme)
    assert part_phrase in parts_text(readme)


def test_summary_priority_list_is_the_scorecards(readme, root):
    import pandas as pd
    priority = pd.read_csv(root / "results" / "scorecard_priority.csv")
    card = pd.read_csv(root / "results" / "scorecard_hospitals.csv")
    both = card[(card["level"] == "below peers") & (card["trend"] == "slipping")]
    assert len(priority) == 12 and set(priority["facility_code"]) == set(both["facility_code"])
    large = priority.loc[priority["peer_group"] == "large", "facility_name"].tolist()
    names = ", ".join(large[:-1]) + " and " + large[-1]
    assert "Start reviews with the 12 hospitals that are below their peers and slipping" in summary_section(readme)
    assert f"The five large ones are {names}." in summary_section(readme)
    assert "(results/scorecard_priority.csv)" in summary_section(readme)


def test_summary_improvers_and_blank_count(readme, root, checks_md):
    import pandas as pd
    card = pd.read_csv(root / "results" / "scorecard_hospitals.csv")
    doors = pd.read_csv(root / "results" / "doors_hospitals.csv")
    improving = card[card["trend"] == "improving"]
    assert len(improving) == 12 and (improving["seen_trend"] != "slipping").all()
    assert ((improving["peer_group"] == "large").sum()) == 4
    stepped = set(doors.loc[doors["wait_step"] == 1, "facility_code"]) if doors["wait_step"].dtype != bool \
        else set(doors.loc[doors["wait_step"], "facility_code"])
    seen_slipping = set(card.loc[card["seen_trend"] == "slipping", "facility_code"])
    assert (len(stepped), len(seen_slipping), len(stepped & seen_slipping)) == (9, 26, 6)
    # "the wrong admitted share in 21 of 83 hospital-quarters": dropping the row is right in 62 of 83
    assert "| no data: drop the row | 62 of 83 |" in checks_md and 83 - 62 == 21
    assert "gives the wrong admitted share in 21 of 83 hospital-quarters" in summary_section(readme)


def test_project_is_marked_complete(readme):
    assert "**Status: complete.**" in readme and "work in progress" not in readme.lower()
    roadmap = readme[readme.index("## Roadmap"):readme.index("## Limitations")]
    steps = re.findall(r"^\d\. (.*)$", roadmap, re.M)
    assert len(steps) == 6 and all(s.startswith("~~") and s.endswith("~~") for s in steps)
    # the one open step is stated wherever the Power BI pack is described
    assert "the DAX measures have not yet been run in Power BI" in readme
    assert "The DAX measures have not been run in Power BI" in readme
