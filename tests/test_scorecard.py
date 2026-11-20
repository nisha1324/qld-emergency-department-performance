import math

import numpy as np
import pandas as pd
import pytest

from edperf import load, mix as M, profile as P, scorecard as SC
from scripts import mix_report, scorecard_report
from tests.conftest import make_rows

T = P.TRIAGE_1_TO_5
STAY, SEEN = "stay_within_4h_pct", "seen_on_time_pct"
NAN = float("nan")


def u(weights, rates) -> pd.DataFrame:
    return pd.DataFrame({"weight": weights, "rate": rates}, index=T, dtype=float)


def ref(*shares) -> pd.Series:
    return pd.Series(shares, index=T, dtype=float)


# ------------------------------------------------------------------ building blocks, by hand
@pytest.mark.parametrize("attendances, group", [
    (144, "small"), (2_499, "small"), (2_500, "medium"), (9_999, "medium"), (10_000, "large"), (31_831, "large"),
])
def test_peer_group_boundaries(attendances, group):
    assert SC.peer_group(attendances) == group


def test_same_mix_rate_by_hand():
    s = SC.standardised(u([0, 100, 300, 0, 0], [NAN, 50, 80, NAN, NAN]), ref(0, 0.5, 0.5, 0, 0))
    assert s["rate"] == pytest.approx(65)                      # own mix would give 72.5
    assert s["covered"] == pytest.approx(1)
    # variance = 0.25 * 50*50/100 + 0.25 * 80*20/300
    assert s["se"] == pytest.approx(math.sqrt(0.25 * 25 + 0.25 * 1600 / 300))


def test_same_mix_rate_removes_a_mix_difference():
    rates = [40, 45, 50, 75, 90]
    a = SC.standardised(u([10, 300, 400, 200, 90], rates), ref(0.01, 0.2, 0.4, 0.3, 0.09))
    b = SC.standardised(u([1, 50, 200, 500, 249], rates), ref(0.01, 0.2, 0.4, 0.3, 0.09))
    assert a["rate"] == pytest.approx(b["rate"])
    assert M.rebuilt(u([10, 300, 400, 200, 90], rates)) < M.rebuilt(u([1, 50, 200, 500, 249], rates))


def test_same_mix_rate_leaves_out_a_category_with_nobody():
    s = SC.standardised(u([0, 100, 300, 0, 0], [NAN, 50, 80, NAN, NAN]), ref(0.2, 0.4, 0.4, 0, 0))
    assert s["covered"] == pytest.approx(0.8)
    assert s["rate"] == pytest.approx(65)


def test_same_mix_rate_refuses_a_missing_rate():
    with pytest.raises(M.Incomplete):
        SC.standardised(u([0, 100, 300, 0, 0], [NAN, NAN, 80, NAN, NAN]), ref(0, 0.5, 0.5, 0, 0))


def test_within_se_by_hand():
    u0, u1 = u([0, 100, 100, 0, 0], [NAN, 50, 80, NAN, NAN]), u([0, 100, 100, 0, 0], [NAN, 40, 80, NAN, NAN])
    # avg share 0.5 each; var2 = 50*50/100 + 40*60/100 = 49; var3 = 2 * 80*20/100 = 32
    assert SC.within_se(u0, u1) == pytest.approx(math.sqrt(0.25 * 49 + 0.25 * 32))


def test_four_times_the_patients_halves_the_bar():
    r0, r1 = [30, 45, 50, 75, 90], [28, 41, 52, 70, 92]
    w = np.array([5, 80, 200, 150, 40])
    assert SC.within_se(u(4 * w, r0), u(4 * w, r1)) == pytest.approx(SC.within_se(u(w, r0), u(w, r1)) / 2)


def test_a_category_with_nobody_in_one_period_adds_no_noise():
    u0 = u([0, 100, 100, 0, 0], [NAN, 50, 80, NAN, NAN])
    with_one = u([20, 100, 100, 0, 0], [50, 50, 80, NAN, NAN])
    s0, s1 = pd.Series([0, .5, .5, 0, 0], index=T), pd.Series([20, 100, 100, 0, 0], index=T) / 220
    avg = (s0 + s1) / 2
    expected = math.sqrt(avg["2"] ** 2 * 2 * 25 + avg["3"] ** 2 * 2 * 16)
    assert SC.within_se(u0, with_one) == pytest.approx(expected)


@pytest.mark.parametrize("value, se, expected", [
    (2.59, 1.0, "up"), (2.57, 1.0, "flat"), (-2.59, 1.0, "down"), (-2.57, 1.0, "flat"), (0.0, 0.0, "flat"),
    (NAN, 1.0, "n/a"), (0.1, 0.0, "up"),
])
def test_direction(value, se, expected):
    assert SC.direction(value, se) == expected


# ------------------------------------------------------------------ the scorecard on a hand-made state
def hospital(code, name, att, rates0, rates1, new=False):
    r0, r1 = list(rates0) + [0.0], list(rates1) + [0.0]
    rows = [] if new else [make_rows("2024-06", code, name, att, stay_within_4h_pct=r0)]
    rows.append(make_rows("2026-06", code, name, att, stay_within_4h_pct=r1))
    return rows


@pytest.fixture(scope="module")
def toy() -> pd.DataFrame:
    att = [0, 1000, 1500, 1000, 500]                      # 4,000 a quarter: medium
    base = [0, 50, 60, 80, 90]
    parts = []
    parts += hospital(1, "Steady", att, base, base)
    parts += hospital(2, "Falling", att, base, [0, 40, 50, 70, 80])
    parts += hospital(3, "Rising", att, base, [0, 60, 70, 90, 100])
    parts += hospital(4, "Wobble", att, base, [0, 50.5, 60, 80, 90])
    parts += hospital(5, "Newcomer", att, base, base, new=True)
    parts += hospital(6, "Tiny", [0, 2, 4, 30, 20], [0, 50, 50, 80, 90], [0, 0, 50, 80, 90])
    return pd.concat(parts, ignore_index=True)


def test_scorecard_on_hand_made_hospitals(toy):
    k = SC.scorecard(toy, STAY, "2024-06", "2026-06").set_index("facility_name")
    assert k.loc["Steady", "trend"] == "no clear change" and k.loc["Steady", "within"] == pytest.approx(0)
    assert k.loc["Falling", "trend"] == "slipping" and k.loc["Falling", "within"] == pytest.approx(-10)
    assert k.loc["Rising", "trend"] == "improving" and k.loc["Rising", "within"] == pytest.approx(10)
    assert k.loc["Wobble", "trend"] == "no clear change" and k.loc["Wobble", "within"] == pytest.approx(0.125)
    assert k.loc["Newcomer", "trend"] == "new" and np.isnan(k.loc["Newcomer", "within"])
    # 2 of 2 category-2 patients to 0 of 2 is a 50-point fall in that category, on 2 patients
    assert k.loc["Tiny", "peer_group"] == "small" and k.loc["Tiny", "trend"] == "no clear change"
    assert (k.loc[["Steady", "Falling", "Rising", "Wobble", "Newcomer"], "peer_group"] == "medium").all()


def test_scorecard_levels_on_hand_made_hospitals(toy):
    k = SC.scorecard(toy, STAY, "2024-06", "2026-06").set_index("facility_name")
    # same mix in all five medium hospitals, so the same-mix rate is the plain rate
    assert k.loc["Steady", "standardised"] == pytest.approx(66.25)   # .25*50 + .375*60 + .25*80 + .125*90
    assert k.loc["Falling", "standardised"] == pytest.approx(56.25)
    assert k.loc["Steady", "peer_median"] == pytest.approx(66.25)
    assert k.loc["Falling", "level"] == "below peers"
    assert k.loc["Rising", "level"] == "above peers"
    assert k.loc["Steady", "level"] == "in line" and k.loc["Newcomer", "level"] == "in line"
    assert k.loc["Falling", "patients_equivalent"] == pytest.approx(-400)


def test_scorecard_mid_quarter_split(toy):
    att = [0, 1000, 1500, 1000, 500]
    mid = make_rows("2025-06", 2, "Falling", att, stay_within_4h_pct=[0, 40, 50, 70, 80, 0.0])
    k = SC.scorecard(pd.concat([toy, mid], ignore_index=True), STAY, "2024-06", "2026-06", "2025-06").set_index("facility_name")
    assert k.loc["Falling", "within_first"] == pytest.approx(-10) and k.loc["Falling", "within_second"] == pytest.approx(0)
    assert np.isnan(k.loc["Steady", "within_first"])


def test_group_summary_on_hand_made_hospitals(toy):
    k = SC.scorecard(toy, STAY, "2024-06", "2026-06")
    g = SC.group_summary(toy, k, STAY, "2024-06", "2026-06").set_index("peer_group")
    assert list(g.index) == ["medium", "small"]              # no large hospital in the toy state
    m = g.loc["medium"]
    assert m["hospitals"] == 5 and m["with_both_quarters"] == 4
    assert (m["slipping"], m["improving"], m["no_clear_change"]) == (1, 1, 2)
    assert m["pooled_within"] == pytest.approx(0.125 / 4) and m["pooled_mix"] == pytest.approx(0)
    assert m["attendance_share"] == pytest.approx(100 * 20000 / 20056)


# ------------------------------------------------------------------ the real figures
@pytest.fixture(scope="module")
def r(snapshot) -> dict:
    return scorecard_report.analyse(snapshot)


def test_periods(r):
    assert (r["q0"], r["q_mid"], r["q1"]) == ("2024-06", "2025-06", "2026-06")


def test_every_reporting_hospital_is_scored_once(r, snapshot):
    card = r["card"]
    end = snapshot[(snapshot["quarter"] == r["q1"]) & ~snapshot["is_state_total"]]
    assert sorted(card["facility_code"]) == sorted(end["facility_code"].unique())
    assert len(card) == 105 and card["within"].notna().sum() == 104
    assert card["peer_group"].value_counts().to_dict() == {"small": 57, "medium": 26, "large": 22}


def test_trend_counts(r):
    card = r["card"]
    got = pd.crosstab(card["peer_group"], card["trend"])
    assert got.loc["large"].to_dict() == {"improving": 4, "new": 0, "no clear change": 2, "slipping": 16}
    assert got.loc["medium"].to_dict() == {"improving": 5, "new": 1, "no clear change": 10, "slipping": 10}
    assert got.loc["small"].to_dict() == {"improving": 3, "new": 0, "no clear change": 45, "slipping": 9}


def test_priority_list(r):
    card = r["card"]
    pri = card[(card["level"] == "below peers") & (card["trend"] == "slipping")]
    assert len(pri) == 12 and pri["peer_group"].value_counts().to_dict() == {"large": 5, "small": 5, "medium": 2}
    assert {"Queen Elizabeth II", "Princess Alexandra", "Gladstone", "Longreach"} <= set(pri["facility_name"])


def test_scorecard_agrees_with_part_2(r, snapshot):
    """The large hospitals' split is the one Part 2 published."""
    big = r["card"][r["card"]["peer_group"] == "large"].set_index("facility_code")
    p2 = M.hospital_table(snapshot, STAY, r["q0"], r["q1"], list(big.index)).set_index("facility_code")
    assert len(p2) == 22
    for col in ("within", "mix", "change"):
        assert np.allclose(big.loc[p2.index, col], p2[col])
    seen = M.hospital_table(snapshot, SEEN, r["q0"], r["q1"], list(big.index)).set_index("facility_code")
    assert np.allclose(big.loc[seen.index, "seen_within"], seen["within"])


def test_split_adds_up_and_flags_follow_the_bar(r):
    k = r["card"][r["card"]["within"].notna()]
    assert np.allclose(k["mix"] + k["within"], k["change"])
    assert ((k["within"] < -k["bar"]) == (k["trend"] == "slipping")).all()
    assert ((k["within"] > k["bar"]) == (k["trend"] == "improving")).all()
    assert np.allclose(k["bar"], SC.Z * k["within_se"])
    low = r["card"][r["card"]["level"] == "below peers"]
    assert (low["standardised"] <= low["peer_q25"]).all() and (low["vs_peers"] < 0).all()


def test_same_mix_rate_of_a_whole_group_is_its_pooled_rate(r, snapshot):
    """Weighting the pooled group's own category rates by the group's mix gives the pooled rate back."""
    c = M.cells(snapshot, STAY)
    for g in SC.GROUPS:
        codes = r["card"].loc[r["card"]["peer_group"] == g, "facility_code"]
        pooled = M.pool(c, r["q1"], codes)
        s = SC.standardised(pooled, SC.reference_shares(c, r["q1"], codes))
        row = r["groups"].set_index("peer_group").loc[g]
        assert s["rate"] == pytest.approx(row["pooled_rate_1"])


def test_bars_shrink_with_size(r):
    med = r["card"].groupby("peer_group")["bar"].median()
    assert med["large"] < med["medium"] < med["small"]


def test_report_and_csvs_regenerate_byte_for_byte(r, root):
    report, csvs = scorecard_report.build_report(r)
    assert report.encode() == (root / "results" / "HOSPITAL_SCORECARD.md").read_bytes()
    assert len(csvs) == 3
    for name, frame in csvs.items():
        expected = frame.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode()
        assert expected == (root / "results" / name).read_bytes(), name


def test_charts_regenerate_byte_for_byte(r, root, tmp_path):
    scorecard_report.chart_large(r["card"], r["q0"], r["q1"], tmp_path / "07_large_hospital_trend.png")
    scorecard_report.chart_level_trend(r["card"], scorecard_report.CHART_LABELS, tmp_path / "08_level_vs_trend.png")
    scorecard_report.chart_counts(r["groups"], tmp_path / "09_trend_by_group.png")
    made = sorted(tmp_path.glob("*.png"))
    assert len(made) == 3
    for png in made:
        assert png.read_bytes() == (root / "results" / "charts" / png.name).read_bytes(), png.name


def test_chart_labels_name_real_hospitals(r):
    codes = set(r["card"].loc[r["card"]["peer_group"].isin(["large", "medium"]), "facility_code"])
    assert set(scorecard_report.CHART_LABELS) <= codes


def test_report_has_no_hyphen_minus_numbers_or_negative_zero(root):
    import re
    text = (root / "results" / "HOSPITAL_SCORECARD.md").read_text(encoding="utf-8")
    assert not re.search(r"(?<![\w-])-\d", text)
    assert not re.search(r"[−+]0\.0+(?!\d)", text)
