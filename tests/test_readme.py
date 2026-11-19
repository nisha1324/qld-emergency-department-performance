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


def results_section(readme: str) -> str:
    start = readme.index("## Part 1")
    return readme[start:readme.index("## How to run")]


def tokens(text: str) -> set[str]:
    return {t.lstrip("+") for t in NUMBER.findall(text)}


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


def test_readme_charts_exist(readme, root):
    charts = re.findall(r"\]\((results/charts/[^)]+)\)", readme)
    assert len(charts) == 3
    for c in charts:
        assert (root / c).is_file(), c


def test_readme_commands_exist(readme, root):
    for script in re.findall(r"python (scripts/\w+\.py)", readme):
        assert (root / script).is_file(), script


def test_file_sizes_quoted_in_readme(root):
    raw = sum(p.stat().st_size for p in (root / "data" / "raw").glob("*.json"))
    assert round(raw / 1e6, 1) == 1.0
    assert round((root / "data" / "ed_quarterly.csv").stat().st_size / 1e6, 1) == 0.6
