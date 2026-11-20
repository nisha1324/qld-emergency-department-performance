import numpy as np
import pandas as pd
import pytest

from edperf import load, profile as P
from scripts import profile_source
from tests.conftest import make_rows

S = load.STATE_CODE


def toy():
    """Two hospitals and a state row over five quarters, identical in each."""
    parts = []
    quarters = ["2025-03", "2025-06", "2025-09", "2025-12", "2026-03"]
    for i, q in enumerate(quarters):
        a = make_rows(q, 1, "Big", [10, 200, 400, 300, 90], stay_within_4h_pct=40.0, seen_on_time_pct=60.0,
                      did_not_wait=[0, 0, 10, 20, 10, 40], did_not_wait_pct=[0, 0, 2.5, 6.7, 11.1, 4.0])
        b = make_rows(q, 2, "Small", [0, 10, 30, 40, 20], stay_within_4h_pct=90.0, seen_on_time_pct=100.0)
        b.loc[b["triage"] == "1", P.RATES] = np.nan
        s = make_rows(q, S, "Queensland", [10, 210, 430, 340, 110], stay_within_4h_pct=44.5, seen_on_time_pct=63.6,
                      did_not_wait=[0, 0, 10, 20, 10, 40], did_not_wait_pct=[0, 0, 2.3, 5.9, 9.1, 3.6])
        parts += [a, b, s]
    return pd.concat(parts, ignore_index=True)


def test_coverage_counts_hospitals_not_the_state_row():
    cov = P.coverage(toy())
    assert cov["hospitals"].tolist() == [2] * 5
    assert cov["rows"].tolist() == [12] * 5
    assert cov["zero_attendance_rows"].tolist() == [1] * 5
    assert cov["attendances"].tolist() == [1100] * 5


def test_decimal_share_and_whole_number_quarters():
    df = toy()
    df.loc[df["quarter"] == "2025-03", P.PCT_RATES] = df.loc[df["quarter"] == "2025-03", P.PCT_RATES].round()
    share = P.decimal_share(df)
    assert share["2025-03"] == 0 and share["2025-06"] > 0
    assert P.whole_number_quarters(df) == {"2025-03"}
    tol = P.rate_tolerance(pd.Series(["2025-03", "2025-06"]), {"2025-03"})
    assert tol.tolist() == [0.5, 0.05]


def test_state_trend_works_rates_out_from_counts():
    t = P.state_trend(toy())
    assert len(t) == 5 and t["attendances"].tolist() == [1100] * 5
    assert t["did_not_wait_pct"].iloc[0] == pytest.approx(100 * 40 / 1100)


def test_rolling_year_needs_four_quarters():
    r = P.rolling_year(toy())
    assert r["quarter"].tolist() == ["2025-12", "2026-03"] and r["attendances_4q"].tolist() == [4400, 4400]


def test_triage_table_and_mix_shares():
    df = toy()
    t = P.triage_table(df, "2026-03").set_index("triage")
    assert t.loc["2", "share_pct"] == pytest.approx(100 * 210 / 1100)
    assert t.loc["ALL", "share_pct"] == 100
    mix = P.triage_mix(df).set_index("quarter")
    assert mix.loc["2025-03"].sum() == pytest.approx(100)


def test_size_table_and_summary():
    sizes = P.size_table(toy(), "2026-03")
    assert sizes["facility_name"].tolist() == ["Big", "Small"]
    assert sizes["cum_share_pct"].tolist() == pytest.approx([100 * 1000 / 1100, 100])
    summary = P.size_summary(sizes, 500)
    assert summary["hospitals"].tolist() == [1, 1]
    assert summary["share_pct"].tolist() == pytest.approx([100 * 1000 / 1100, 100 * 100 / 1100])
    assert summary["stay_within_4h_weighted"].tolist() == [40.0, 90.0]
    both = P.size_summary(sizes, 50).iloc[0]
    assert both["stay_within_4h_weighted"] == pytest.approx((40 * 1000 + 90 * 100) / 1100)
    assert both["stay_within_4h_median"] == 65
    assert P.size_summary(sizes, 50).iloc[1]["hospitals"] == 0


def test_missing_table_splits_by_attendances():
    df = toy()
    df.loc[(df["facility_code"] == 1) & (df["triage"] == "2") & (df["quarter"] == "2025-06"), "admitted_pct"] = np.nan
    m = P.missing_table(df).set_index("measure")
    assert m.loc["seen_on_time_pct", ["empty", "of_which_no_attendances", "of_which_with_attendances"]].tolist() == [5, 5, 0]
    assert m.loc["admitted_pct", ["empty", "of_which_with_attendances", "quarters_affected_with_attendances"]].tolist() == [6, 1, 1]


def test_dash_for_zero_counts_zeroes_published_as_empty():
    df = toy()
    hit = (df["quarter"] == "2025-06") & (df["did_not_wait"] == 0) & (df["attendances"] > 0)
    df.loc[hit, "did_not_wait_pct"] = np.nan
    d = P.dash_for_zero(df).set_index("quarter")
    assert d.loc["2025-06", ["rows", "published_as_zero", "published_empty"]].tolist() == [9, 0, 9]
    assert d.loc["2025-09", ["rows", "published_as_zero", "published_empty"]].tolist() == [9, 9, 0]


def test_sum_checks_pass_then_catch_planted_errors():
    df = toy()
    assert P.check_triage_sums(df) == {"facility_quarters": 15, "mismatches": 0}
    assert P.check_state_sums(df)["attendances_mismatches"] == 0
    bad = df.copy()
    bad.loc[(bad["facility_code"] == 1) & (bad["triage"] == "3") & (bad["quarter"] == "2025-09"), "attendances"] += 1
    assert P.check_triage_sums(bad)["mismatches"] == 1
    bad = df.copy()
    bad.loc[(bad["facility_code"] == S) & (bad["triage"] == "ALL") & (bad["quarter"] == "2025-09"), "did_not_wait"] += 1
    out = P.check_state_sums(bad)
    assert out["did_not_wait_mismatches"] == 1 and out["attendances_mismatches"] == 0


def test_rates_from_counts_respects_the_rounding():
    df = toy()
    ok = P.check_rates_from_counts(df)
    assert ok["did_not_wait_pct_mismatches"] == 0 and ok["did_not_wait_pct_compared"] > 0
    bad = df.copy()
    bad.loc[(bad["facility_code"] == 1) & (bad["triage"] == "3") & (bad["quarter"] == "2025-09"), "did_not_wait_pct"] = 2.7
    assert P.check_rates_from_counts(bad)["did_not_wait_pct_mismatches"] == 1


def test_change_check_flags_only_real_disagreements():
    df = toy()
    last = df["quarter"] == "2026-03"
    df.loc[last & (df["facility_code"] == 1), "attendances"] = [11, 220, 400, 300, 90, 1021]
    df.loc[last & (df["facility_code"] == 1), "attendances_change_pct"] = [10.0, 10.0, 0.0, 0.0, 0.0, 9.0]
    c = P.change_check(df)
    assert set(c["quarter"]) == {"2026-03"} and len(c) == 6          # only rows with a published change
    flagged = c[c["mismatch"]]
    assert flagged["triage"].tolist() == ["ALL"]                      # 1021 / 1000 is +2.1%, not +9.0%
    assert flagged["recomputed_pct"].iloc[0] == pytest.approx(2.1)
    assert flagged["implied_year_earlier"].iloc[0] == round(1021 / 1.09)


def test_state_rate_weighting():
    df = toy()
    assert P.check_state_rate_is_weighted(df, "stay_within_4h_pct") == pytest.approx(abs((40 * 1000 + 90 * 100) / 1100 - 44.5))
    sv = P.simple_vs_weighted(df, "2026-03", "stay_within_4h_pct")
    assert sv == {"state": 44.5, "simple_mean_of_hospitals": 65.0, "median_hospital": 65.0}


def test_new_facilities():
    df = toy()
    df = df[~((df["facility_code"] == 2) & (df["quarter"] < "2026-03"))]
    new = P.new_facilities(df)
    assert new["facility_name"].tolist() == ["Small"] and new["first_quarter"].tolist() == ["2026-03"]


# ------------------------------------------------------------------ real data
def test_real_headline_figures(snapshot):
    t = P.state_trend(snapshot).set_index("quarter")
    assert t.loc["2026-06", "attendances"] == 593177 and t.loc["2023-06", "attendances"] == 584431
    assert t.loc["2026-06", ["seen_on_time_pct", "stay_within_4h_pct", "admitted_within_4h_pct"]].tolist() == [74.6, 56.1, 31.3]
    assert t.loc["2023-06", ["seen_on_time_pct", "stay_within_4h_pct", "admitted_within_4h_pct"]].tolist() == [71, 61, 37]
    assert P.rolling_year(snapshot).set_index("quarter").loc["2026-06", "attendances_4q"] == 2406005
    summary = P.size_summary(P.size_table(snapshot, "2026-06"), 10_000)
    assert summary["hospitals"].tolist() == [22, 83]
    assert summary["share_pct"].round(1).tolist() == [70.2, 29.8]
    assert summary["stay_within_4h_weighted"].round(1).tolist() == [45.7, 80.6]


def test_real_checks(snapshot):
    assert P.check_triage_sums(snapshot) == {"facility_quarters": 1471, "mismatches": 0}
    s = P.check_state_sums(snapshot)
    assert [s[k] for k in s if k.endswith("mismatches")] == [0, 0, 0]
    r = P.check_rates_from_counts(snapshot)
    assert r["did_not_wait_pct_mismatches"] == 0 and r["left_after_treatment_pct_mismatches"] == 0
    assert P.whole_number_quarters(snapshot) == {"2023-03", "2023-06", "2023-09", "2023-12", "2024-03"}
    c = P.change_check(snapshot)
    m = c[c["mismatch"]]
    assert len(c) == 6157 and len(m) == 42 and set(m["quarter"]) == {"2024-03", "2025-12"}
    worst = m.sort_values("gap").iloc[-1]
    assert worst["facility_name"] == "Nambour" and worst["quarter"] == "2025-12"
    # the report says the state row is out by a similar number of attendances to Nambour
    allm = m[(m["triage"] == "ALL") & (m["quarter"] == "2025-12")].set_index("facility_name")
    gap = allm["implied_year_earlier"] - allm["attendances_year_earlier"]
    assert abs(gap["Queensland"] - gap["Nambour"]) < 0.1 * gap["Nambour"]
    other = m[(m["triage"] == "ALL") & (m["quarter"] == "2024-03")]
    assert other["gap"].max() < 2


def test_report_and_csvs_regenerate_byte_for_byte(snapshot, root):
    names = pd.read_csv(root / "data" / "facility_names.csv", dtype=str).astype({"facility_code": int})
    report, csvs = profile_source.build_report(snapshot, names)
    assert report.encode() == (root / "results" / "SOURCE_PROFILE.md").read_bytes()
    for name, frame in csvs.items():
        expected = frame.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode()
        assert expected == (root / "results" / name).read_bytes(), name


def test_charts_regenerate_byte_for_byte(snapshot, root, tmp_path):
    trend = P.state_trend(snapshot)
    sizes = P.size_table(snapshot, "2026-06")
    profile_source.chart_trend(trend, tmp_path / "01_state_trend.png")
    profile_source.chart_mix(P.triage_mix(snapshot), "2023-06", "2026-06", tmp_path / "02_triage_mix.png")
    profile_source.chart_size(sizes, "2026-06", float(trend["stay_within_4h_pct"].iloc[-1]), tmp_path / "03_size_vs_4h.png")
    for png in sorted(tmp_path.glob("*.png")):
        assert png.read_bytes() == (root / "results" / "charts" / png.name).read_bytes(), png.name
    assert len(list(tmp_path.glob("*.png"))) == 3
    # every committed chart is regenerated by this test or by tests/test_mix.py
    assert len(list((root / "results" / "charts").glob("*.png"))) == 9
