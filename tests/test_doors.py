import math
import re

import numpy as np
import pandas as pd
import pytest

from edperf import doors as D, load, mix as M, scorecard as SC
from scripts import doors_report
from tests.conftest import make_rows

STAY = "stay_within_4h_pct"
NAN = float("nan")
Q0, Q1 = "2024-06", "2026-06"


def hospital(quarter, att, admitted, adm4h, not4h, code=7, **cols):
    """Six tidy rows where each category's stay rate is built from its two streams,
    so the implied not-admitted rate is known in advance."""
    stay = [a / 100 * x + (1 - a / 100) * y for a, x, y in zip(admitted, adm4h, not4h)]
    return make_rows(quarter, code, "Test", att, admitted_pct=list(admitted) + [NAN],
                     admitted_within_4h_pct=list(adm4h) + [NAN], stay_within_4h_pct=stay + [NAN], **cols)


def split(df, code=7):
    t, sc = M.cells(df, STAY), D.stream_cells(df)
    return D.four_way(M.unit(t, Q0, code), M.unit(t, Q1, code), D.unit(sc, Q0, code), D.unit(sc, Q1, code))


ONE = [0, 0, 100, 0, 0]           # every patient in triage category 3
BASE = dict(att=ONE, admitted=[0, 0, 20, 0, 0], adm4h=[0, 0, 50, 0, 0], not4h=[0, 0, 80, 0, 0])


# ------------------------------------------------------------------ building blocks, by hand
def test_stream_cells_by_hand():
    df = hospital(Q0, [0, 0, 200, 0, 0], [0, 0, 25, 0, 0], [0, 0, 40, 0, 0], [0, 0, 80, 0, 0])
    c = D.stream_cells(df).set_index(["triage", "stream"])
    assert c.loc[("3", "admitted"), "weight"] == pytest.approx(50)
    assert c.loc[("3", "not admitted"), "weight"] == pytest.approx(150)
    assert c.loc[("3", "admitted"), "rate"] == pytest.approx(40)
    assert c.loc[("3", "not admitted"), "rate"] == pytest.approx(80)      # (70 - 0.25 * 40) / 0.75
    assert c.loc[("1", "admitted"), "weight"] == 0 and c.loc[("1", "not admitted"), "weight"] == 0
    assert len(c) == 10


def test_rounding_of_a_cell_by_hand():
    df = hospital(Q0, [0, 0, 200, 0, 0], [0, 0, 25, 0, 0], [0, 0, 40, 0, 0], [0, 0, 80, 0, 0])
    c = D.stream_cells(df, tol=0.05).set_index(["triage", "stream"])
    assert c.loc[("3", "admitted"), "rounding"] == pytest.approx(0.05)
    # (0.05 * (1 + 0.25) + 0.05 / 100 * |40 - 80|) / 0.75
    assert c.loc[("3", "not admitted"), "rounding"] == pytest.approx((0.0625 + 0.02) / 0.75)


def test_everyone_admitted_leaves_no_not_admitted_stream():
    df = hospital(Q0, ONE, [0, 0, 100, 0, 0], [0, 0, 40, 0, 0], [0, 0, 0, 0, 0])
    c = D.stream_cells(df).set_index(["triage", "stream"])
    assert c.loc[("3", "not admitted"), "weight"] == 0
    assert math.isnan(c.loc[("3", "not admitted"), "rate"])
    u = D.unit(D.stream_cells(df), Q0, 7)
    assert M.rebuilt(u) == pytest.approx(40)
    assert D.stream_share(u, "admitted") == pytest.approx(100)
    assert math.isnan(D.stream_rate(u, "not admitted"))


def test_everyone_admitted_with_figures_that_disagree_by_rounding():
    """Stay 41% but admitted rate 40% with 100% admitted: the implied rate would be 1/0. It must be empty, not infinite."""
    df = make_rows(Q0, 7, "Test", [0, 0, 100, 50, 0], admitted_pct=[0, 0, 100, 0, 0, NAN],
                   admitted_within_4h_pct=[NAN, NAN, 40, NAN, NAN, NAN], stay_within_4h_pct=[NAN, NAN, 41, 90, NAN, NAN])
    c = D.stream_cells(df).set_index(["triage", "stream"])
    assert math.isnan(c.loc[("3", "not admitted"), "rate"]) and math.isnan(c.loc[("3", "not admitted"), "rounding"])
    u = D.unit(D.stream_cells(df), Q0, 7)
    assert D.stream_rate(u, "not admitted") == pytest.approx(90)
    assert D.stream_rate(u, "admitted") == pytest.approx(40)


def test_ten_cells_rebuild_the_category_rates():
    df = hospital(Q0, [10, 200, 400, 300, 90], [80, 50, 30, 10, 4], [40, 35, 30, 50, 60], [45, 50, 60, 80, 92])
    u = D.unit(D.stream_cells(df), Q0, 7)
    assert M.rebuilt(u) == pytest.approx(M.rebuilt(M.unit(M.cells(df, STAY), Q0, 7)))
    # stream rate = that stream's patients only: admitted counts 8, 100, 120, 30, 3.6
    adm = np.array([8, 100, 120, 30, 3.6])
    assert D.stream_rate(u, "admitted") == pytest.approx((adm * [40, 35, 30, 50, 60]).sum() / adm.sum())
    assert D.stream_share(u, "admitted") == pytest.approx(100 * adm.sum() / 1000)


@pytest.mark.parametrize("end, expected", [
    # admitted patients' rate falls 50 -> 40: 20% of patients x -10
    (dict(BASE, adm4h=[0, 0, 40, 0, 0]), dict(change=-2, triage_mix=0, admission_share=0, admitted=-2, not_admitted=0)),
    # not-admitted patients' rate falls 80 -> 70: 80% of patients x -10
    (dict(BASE, not4h=[0, 0, 70, 0, 0]), dict(change=-8, triage_mix=0, admission_share=0, admitted=0, not_admitted=-8)),
    # twice the share admitted, same rates: 0.2 x 50 - 0.2 x 80
    (dict(BASE, admitted=[0, 0, 40, 0, 0]), dict(change=-6, triage_mix=0, admission_share=-6, admitted=0, not_admitted=0)),
    # nothing moves
    (BASE, dict(change=0, triage_mix=0, admission_share=0, admitted=0, not_admitted=0)),
])
def test_four_way_split_isolates_one_cause(end, expected):
    f = split(pd.concat([hospital(Q0, **BASE), hospital(Q1, **end)]))
    for key, value in expected.items():
        assert f[key] == pytest.approx(value, abs=1e-9), key
    assert f["rebuild_gap"] == pytest.approx(0, abs=1e-9)


def test_four_way_split_sends_a_triage_shift_to_triage_mix():
    """Category 3 (60% within 4 h) grows from half to three quarters of patients; no rate moves."""
    kw = dict(admitted=[0, 0, 50, 0, 0], adm4h=[0, 0, 40, 0, 0], not4h=[0, 0, 80, 90, 0])
    f = split(pd.concat([hospital(Q0, [0, 0, 100, 100, 0], **kw), hospital(Q1, [0, 0, 150, 50, 0], **kw)]))
    assert f["change"] == pytest.approx(-7.5)                # 0.75*60 + 0.25*90 - 75
    assert f["triage_mix"] == pytest.approx(-7.5)
    for key in ("admission_share", "admitted", "not_admitted"):
        assert f[key] == pytest.approx(0, abs=1e-9), key


def test_four_way_split_with_everything_moving_adds_up():
    a = hospital(Q0, [10, 200, 400, 300, 90], [80, 50, 30, 10, 4], [40, 35, 30, 50, 60], [45, 50, 60, 80, 92])
    b = hospital(Q1, [14, 260, 390, 250, 86], [78, 46, 31, 9, 5], [33, 30, 28, 52, 55], [41, 47, 58, 79, 93])
    df = pd.concat([a, b])
    f = split(df)
    assert f["triage_mix"] + f["admission_share"] + f["admitted"] + f["not_admitted"] == pytest.approx(f["change"])
    d5 = M.decompose(M.unit(M.cells(df, STAY), Q0, 7), M.unit(M.cells(df, STAY), Q1, 7))
    assert f["triage_mix"] == pytest.approx(d5["mix"])
    assert f["admission_share"] + f["admitted"] + f["not_admitted"] == pytest.approx(d5["within"])
    assert f["admitted"] < 0 and f["not_admitted"] < 0


def test_stream_standard_error_by_hand():
    f = split(pd.concat([hospital(Q0, **BASE), hospital(Q1, **dict(BASE, adm4h=[0, 0, 40, 0, 0]))]))
    # 20 admitted patients each time: 0.2 * sqrt(50*50/20 + 40*60/20)
    assert f["admitted_se"] == pytest.approx(0.2 * math.sqrt(125 + 120))
    # 80 not-admitted patients at 80% both times: 0.8 * sqrt(2 * 80*20/80)
    assert f["not_admitted_se"] == pytest.approx(0.8 * math.sqrt(40))


def test_stream_rounding_by_hand():
    f = split(pd.concat([hospital(Q0, **BASE), hospital(Q1, **BASE)]))
    assert f["admitted_rounding"] == pytest.approx(0.2 * (0.05 + 0.05))
    cell = (0.05 * 1.2 + 0.05 / 100 * 30) / 0.8
    assert f["not_admitted_rounding"] == pytest.approx(0.8 * 2 * cell)


def test_more_patients_make_a_narrower_bar():
    def se(scale):
        big = dict(BASE, att=[0, 0, 100 * scale, 0, 0])
        return split(pd.concat([hospital(Q0, **big), hospital(Q1, **dict(big, adm4h=[0, 0, 40, 0, 0]))]))["admitted_se"]
    assert se(100) == pytest.approx(se(1) / 10)


@pytest.mark.parametrize("admitted, not_admitted, expected", [
    ("slipping", "slipping", "both streams"), ("slipping", "no clear change", "admitted only"),
    ("slipping", "improving", "admitted only"), ("no clear change", "slipping", "not admitted only"),
    ("improving", "slipping", "not admitted only"), ("improving", "improving", "neither stream"),
    ("no clear change", "no clear change", "neither stream"),
])
def test_pattern(admitted, not_admitted, expected):
    assert D.pattern(admitted, not_admitted) == expected
    assert expected in D.PATTERNS


def walkouts(quarter, n, left):
    return make_rows(quarter, 7, "Test", [0, 0, n, 0, 0], did_not_wait=[0, 0, left, 0, 0, left])


@pytest.mark.parametrize("n, left_0, left_1, trend", [
    (100, 5, 10, "no clear change"),       # +5 points, but the bar is 2.58 * sqrt(4.75 + 9) = 9.6
    (10_000, 500, 1_000, "rising"),        # the same rates on 100 times the patients
    (10_000, 1_000, 500, "falling"),
])
def test_did_not_wait_change_by_hand(n, left_0, left_1, trend):
    c = D.count_cells(pd.concat([walkouts(Q0, n, left_0), walkouts(Q1, n, left_1)]), "did_not_wait")
    w = D.count_change(c, Q0, Q1, 7)
    assert w["rate_0"] == pytest.approx(100 * left_0 / n) and w["rate_1"] == pytest.approx(100 * left_1 / n)
    assert w["within"] == pytest.approx(100 * (left_1 - left_0) / n)
    p0, p1 = 100 * left_0 / n, 100 * left_1 / n
    assert w["bar"] == pytest.approx(SC.Z * math.sqrt(p0 * (100 - p0) / n + p1 * (100 - p1) / n))
    assert w["trend"] == trend


def test_count_cells_refuses_a_percentage_column():
    with pytest.raises(ValueError):
        D.count_cells(walkouts(Q0, 100, 5), "did_not_wait_pct")


def test_pool_of_one_hospital_is_that_hospital():
    df = hospital(Q0, [10, 200, 400, 300, 90], [80, 50, 30, 10, 4], [40, 35, 30, 50, 60], [45, 50, 60, 80, 92])
    sc = D.stream_cells(df)
    pd.testing.assert_frame_equal(D.pool(sc, Q0, [7]), D.unit(sc, Q0, 7)[["weight", "rate"]], check_names=False)


def test_pool_adds_patients_and_weights_the_rates():
    a = hospital(Q0, ONE, [0, 0, 20, 0, 0], [0, 0, 50, 0, 0], [0, 0, 80, 0, 0], code=1)
    b = hospital(Q0, [0, 0, 300, 0, 0], [0, 0, 40, 0, 0], [0, 0, 30, 0, 0], [0, 0, 60, 0, 0], code=2)
    p = D.pool(D.stream_cells(pd.concat([a, b])), Q0, [1, 2])
    assert p.loc[("3", "admitted"), "weight"] == pytest.approx(140)
    assert p.loc[("3", "admitted"), "rate"] == pytest.approx((20 * 50 + 120 * 30) / 140)
    assert p.loc[("3", "not admitted"), "rate"] == pytest.approx((80 * 80 + 180 * 60) / 260)


def test_doors_leaves_out_a_hospital_missing_from_the_first_quarter():
    both = pd.concat([hospital(Q0, **BASE, code=1), hospital(Q1, **BASE, code=1), hospital(Q1, **BASE, code=2)])
    out = D.doors(both, Q0, Q1)
    assert list(out["facility_code"]) == [1]
    assert out.loc[0, "pattern"] == "neither stream" and out.loc[0, "dnw_trend"] == "no clear change"


# ------------------------------------------------------------------ the real data
@pytest.fixture(scope="module")
def r(snapshot):
    return doors_report.analyse(snapshot)


def test_periods_and_coverage(r):
    assert (r["q0"], r["q1"]) == (Q0, Q1)
    assert len(r["k"]) == 104 and r["new"] == ["Mater Springfield"]
    assert r["max_gap"] < 1e-9


def test_effects_add_up_and_agree_with_part_3(r):
    k = r["k"]
    assert np.allclose(k["triage_mix"] + k["admission_share"] + k["admitted"] + k["not_admitted"], k["change"])
    assert np.allclose(k["triage_mix"], k["mix"])
    assert np.allclose(k["admission_share"] + k["admitted"] + k["not_admitted"], k["within"])


def test_verdicts_follow_the_bars(r):
    k = r["k"]
    for stream in ("admitted", "not_admitted"):
        assert ((k[stream] < -k[f"{stream}_bar"]) == (k[f"{stream}_trend"] == "slipping")).all()
        assert ((k[stream] > k[f"{stream}_bar"]) == (k[f"{stream}_trend"] == "improving")).all()
        flagged = k[k[f"{stream}_trend"] != "no clear change"]
        assert (flagged[f"{stream}_robust"] == (flagged[stream].abs() > flagged[f"{stream}_bar"] + flagged[f"{stream}_rounding"])).all()
    assert ((k["dnw_within"] > k["dnw_bar"]) == (k["dnw_trend"] == "rising")).all()
    assert ((k["dnw_within"] < -k["dnw_bar"]) == (k["dnw_trend"] == "falling")).all()
    assert (k["pattern"] == [D.pattern(a, n) for a, n in zip(k["admitted_trend"], k["not_admitted_trend"])]).all()


def test_state_split_matches_the_published_figures(r, snapshot):
    st = r["groups"].set_index("group").loc["state"]
    pub = snapshot[snapshot["is_state_total"] & (snapshot["triage"] == "ALL")].set_index("quarter")
    assert st["rate_1"] == pytest.approx(pub.loc[Q1, STAY], abs=0.06)
    assert st["admitted_rate_1"] == pytest.approx(pub.loc[Q1, "admitted_within_4h_pct"], abs=0.06)
    assert st["admitted_share_1"] == pytest.approx(pub.loc[Q1, "admitted_pct"], abs=0.06)
    assert st["dnw_rate_1"] == pytest.approx(100 * pub.loc[Q1, "did_not_wait"] / pub.loc[Q1, "attendances"])
    assert round(st["admitted"], 2) == -0.87 and round(st["not_admitted"], 2) == -1.02
    assert st["triage_mix"] + st["admission_share"] + st["admitted"] + st["not_admitted"] == pytest.approx(st["change"])


def test_headline_counts(r):
    k = r["k"]
    slip = k[(k["peer_group"] == "large") & (k["trend"] == "slipping")]
    assert slip["pattern"].value_counts().to_dict() == {"both streams": 11, "not admitted only": 4, "admitted only": 1}
    assert list(slip.loc[slip["pattern"] == "admitted only", "facility_name"]) == ["Nambour"]
    all_slip = k[k["trend"] == "slipping"]
    assert int((all_slip["not_admitted_trend"] == "slipping").sum()) == 32
    assert int((all_slip["admitted_trend"] == "slipping").sum()) == 23
    assert int(k["wait_step"].sum()) == 9


def test_wait_step_rule(r):
    k = r["k"]
    step = k[k["wait_step"]]
    assert (step["median_wait_0"] <= doors_report.ZERO_WAIT).all() and (step["median_wait_1"] >= doors_report.STEP_WAIT).all()
    rest = k[~k["wait_step"]]
    assert ((rest["median_wait_0"] > doors_report.ZERO_WAIT) | (rest["median_wait_1"] < doors_report.STEP_WAIT)).all()


def test_walkouts_by_quarter_add_up_to_the_hospitals(r, snapshot):
    w = r["walkouts"]
    assert len(w) == 14 * 3
    a = snapshot[(snapshot["triage"] == "ALL") & snapshot["facility_code"].isin(r["k"]["facility_code"])]
    assert w["did_not_wait"].sum() == a["did_not_wait"].sum() and w["attendances"].sum() == a["attendances"].sum()


def test_report_and_csvs_regenerate_byte_for_byte(r, root):
    report, csvs = doors_report.build_report(r)
    assert report.encode() == (root / "results" / "FRONT_VS_BACK_DOOR.md").read_bytes()
    assert len(csvs) == 3
    for name, frame in csvs.items():
        expected = frame.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode()
        assert expected == (root / "results" / name).read_bytes(), name


def test_charts_regenerate_byte_for_byte(r, root, tmp_path):
    doors_report.chart_streams(r["k"], r["q0"], r["q1"], tmp_path / "10_large_hospital_streams.png")
    doors_report.chart_four_way(r["groups"], r["q0"], r["q1"], tmp_path / "11_four_way_split.png")
    doors_report.chart_walkouts(r["walkouts"], tmp_path / "12_did_not_wait.png")
    made = sorted(tmp_path.glob("*.png"))
    assert len(made) == 3
    for png in made:
        assert png.read_bytes() == (root / "results" / "charts" / png.name).read_bytes(), png.name


def test_report_has_no_hyphen_minus_numbers_or_negative_zero(root):
    text = (root / "results" / "FRONT_VS_BACK_DOOR.md").read_text(encoding="utf-8")
    assert not re.search(r"(?<![\w-])-\d", text)
    assert not re.search(r"[−+]0\.0+(?!\d)", text)


def test_names_joins_with_and():
    f = lambda *x: pd.DataFrame({"facility_name": list(x)})  # noqa: E731
    assert doors_report.names(f("A")) == "A"
    assert doors_report.names(f("A", "B")) == "A and B"
    assert doors_report.names(f("A", "B", "C")) == "A, B and C"
