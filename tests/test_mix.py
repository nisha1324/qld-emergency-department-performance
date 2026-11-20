import numpy as np
import pandas as pd
import pytest

from edperf import load, mix as M, profile as P
from scripts import mix_report
from tests.conftest import make_rows

S = load.STATE_CODE
T = P.TRIAGE_1_TO_5
STAY, SEEN, ADM, ADM4 = "stay_within_4h_pct", "seen_on_time_pct", "admitted_pct", "admitted_within_4h_pct"


def u(weights, rates) -> pd.DataFrame:
    return pd.DataFrame({"weight": weights, "rate": rates}, index=T, dtype=float)


# ------------------------------------------------------------------ the split, on hand-made numbers
def test_split_by_hand():
    nan = float("nan")
    d = M.decompose(u([0, 50, 50, 0, 0], [nan, 40, 80, nan, nan]), u([0, 60, 40, 0, 0], [nan, 30, 80, nan, nan]))
    assert d["rate_0"] == pytest.approx(60) and d["rate_1"] == pytest.approx(50)
    assert d["mix"] == pytest.approx(0.1 * 35 - 0.1 * 80)            # -4.5
    assert d["within"] == pytest.approx(-10 * 0.55)                  # -5.5
    assert d["mix"] + d["within"] == pytest.approx(d["change"])
    assert d["by_category"].loc["2", "within"] == pytest.approx(-5.5)
    assert d["by_category"].loc["3", "mix"] == pytest.approx(-8.0)


def test_only_the_mix_moves():
    rates = [40, 45, 50, 75, 90]
    d = M.decompose(u([1, 17, 42, 32, 8], rates), u([1, 20, 43, 29, 7], rates))
    assert d["within"] == pytest.approx(0) and d["mix"] == pytest.approx(d["change"]) and d["change"] < 0


def test_only_the_rates_move():
    w = [1, 17, 42, 32, 8]
    d = M.decompose(u(w, [40, 45, 50, 75, 90]), u([10 * x for x in w], [38, 44, 47, 75, 91]))
    assert d["mix"] == pytest.approx(0) and d["within"] == pytest.approx(d["change"])


def test_every_category_improves_but_the_total_falls():
    d = M.decompose(u([0, 20, 0, 80, 0], [0, 40, 0, 80, 0]), u([0, 60, 0, 40, 0], [0, 45, 0, 85, 0]))
    assert d["change"] < 0 < d["within"]
    assert d["within"] == pytest.approx(5) and d["mix"] == pytest.approx(0.4 * 42.5 - 0.4 * 82.5)


def test_swapping_the_periods_flips_the_signs():
    a, b = u([1, 17, 42, 32, 8], [40, 45, 50, 75, 90]), u([2, 21, 40, 30, 7], [35, 41, 52, 70, 92])
    d, e = M.decompose(a, b), M.decompose(b, a)
    assert e["mix"] == pytest.approx(-d["mix"]) and e["within"] == pytest.approx(-d["within"])


def test_a_category_with_no_patients_in_one_period_counts_as_mix():
    nan = float("nan")
    d = M.decompose(u([0, 50, 50, 0, 0], [nan, 40, 80, nan, nan]), u([10, 45, 45, 0, 0], [20, 40, 80, nan, nan]))
    assert d["within"] == pytest.approx(0)
    assert d["change"] == pytest.approx(0.1 * 20 + 0.9 * 60 - 60) == pytest.approx(d["mix"])


def test_missing_rate_with_patients_is_refused():
    nan = float("nan")
    good = u([1, 1, 1, 1, 1], [50] * 5)
    with pytest.raises(M.Incomplete):
        M.decompose(good, u([1, 1, 1, 1, 1], [50, nan, 50, 50, 50]))
    with pytest.raises(M.Incomplete):
        M.rebuilt(u([0, 0, 0, 0, 0], [50] * 5))
    assert M.rebuilt(u([0, 1, 1, 0, 0], [nan, 40, 60, nan, nan])) == pytest.approx(50)


def test_rounding_margin():
    d = M.decompose(u([0, 50, 50, 0, 0], [0, 40, 80, 0, 0]), u([0, 60, 40, 0, 0], [0, 30, 80, 0, 0]))
    m = M.rounding_margin(d, 0.5, 0.05)
    assert m["within"] == pytest.approx(0.55) and m["mix"] == pytest.approx(0.2 * 0.55 / 2)
    # the worst case really is reachable: push every start rate up by its tolerance
    worst = M.decompose(u([0, 50, 50, 0, 0], [0, 40.5, 80.5, 0, 0]), u([0, 60, 40, 0, 0], [0, 29.95, 79.95, 0, 0]))
    assert worst["within"] - d["within"] == pytest.approx(-0.55)
    assert abs(worst["mix"] - d["mix"]) <= m["mix"] + 1e-12


def test_share_of_change():
    assert M.share_of_change(-1, -4) == 25 and np.isnan(M.share_of_change(1, 0))


# ------------------------------------------------------------------ building the pieces from the tidy table
def toy():
    q0 = [make_rows("2024-06", 1, "Big", [10, 200, 400, 300, 90], stay_within_4h_pct=[40, 40, 50, 70, 90, 55.8],
                    admitted_pct=[80, 50, 30, 10, 0, 28.8], admitted_within_4h_pct=[40, 30, 30, 40, float("nan"), 31.0]),
          make_rows("2024-06", 2, "Small", [0, 10, 30, 40, 20], stay_within_4h_pct=[float("nan"), 80, 90, 90, 100, 91.0])]
    q1 = [make_rows("2025-06", 1, "Big", [10, 300, 400, 200, 90], stay_within_4h_pct=[40, 38, 48, 70, 90, 52.5],
                    admitted_pct=[80, 50, 30, 10, 0, 32.0], admitted_within_4h_pct=[40, 30, 30, 40, float("nan"), 31.0]),
          make_rows("2025-06", 2, "Small", [0, 10, 30, 40, 20], stay_within_4h_pct=[float("nan"), 80, 90, 90, 100, 91.0]),
          make_rows("2025-06", 3, "New", [0, 0, 5, 5, 0], stay_within_4h_pct=[float("nan"), float("nan"), 100, 100, float("nan"), 100])]
    return pd.concat(q0 + q1, ignore_index=True)


def test_cells_weights():
    df = toy()
    c = M.cells(df, STAY)
    assert len(c) == 5 * 5 and set(c["triage"]) == set(T)
    assert M.unit(c, "2024-06", 1)["weight"].tolist() == [10, 200, 400, 300, 90]
    a = M.unit(M.cells(df, ADM4), "2024-06", 1)
    assert a["weight"].tolist() == pytest.approx([8, 100, 120, 30, 0])          # admitted patients
    assert M.rebuilt(a) == pytest.approx((8 * 40 + 100 * 30 + 120 * 30 + 30 * 40) / 258)


def test_pool_adds_hospitals_category_by_category():
    c = M.cells(toy(), STAY)
    p = M.pool(c, "2024-06", [1, 2])
    assert p["weight"].tolist() == [10, 210, 430, 340, 110]
    assert p.loc["1", "rate"] == 40                                   # Small has no category 1 patients
    assert p.loc["2", "rate"] == pytest.approx((200 * 40 + 10 * 80) / 210)
    assert M.rebuilt(p) == pytest.approx((1000 * M.rebuilt(M.unit(c, "2024-06", 1)) + 100 * M.rebuilt(M.unit(c, "2024-06", 2))) / 1100)
    one = M.pool(c, "2024-06", [1])
    pd.testing.assert_frame_equal(one, M.unit(c, "2024-06", 1).rename_axis(None), check_names=False)


def test_pool_keeps_a_missing_rate_missing():
    df = toy()
    df.loc[(df["facility_code"] == 2) & (df["quarter"] == "2024-06") & (df["triage"] == "3"), STAY] = np.nan
    p = M.pool(M.cells(df, STAY), "2024-06", [1, 2])
    assert np.isnan(p.loc["3", "rate"])
    with pytest.raises(M.Incomplete):
        M.rebuilt(p)


def test_hospital_table_and_large_codes():
    df = toy()
    assert M.large_codes(df, "2025-06", 500) == [1]
    t = M.hospital_table(df, STAY, "2024-06", "2025-06", [1, 2, 3])
    assert t["facility_name"].tolist() == ["Big", "Small"]            # worst first; New has no start quarter
    big = t.iloc[0]
    assert big["published_0"] == 55.8 and big["published_1"] == 52.5 and big["attendances"] == 1000
    assert big["mix"] + big["within"] == pytest.approx(big["change"])
    assert big["within"] == pytest.approx(-2 * 0.25 - 2 * 0.4)
    assert big["urgent_share_0"] == pytest.approx(21) and big["urgent_share_1"] == pytest.approx(31)
    assert t.iloc[1][["change", "mix", "within"]].tolist() == pytest.approx([0, 0, 0])


def test_fixed_mix_series_and_year_on_year():
    df = toy()
    c = M.cells(df[df["facility_code"] == 1], STAY)
    f = M.fixed_mix_series(c, 1, "2024-06").set_index("quarter")
    assert f.loc["2024-06", "fixed_mix"] == pytest.approx(f.loc["2024-06", "rebuilt"])
    assert f.loc["2025-06", "fixed_mix"] == pytest.approx((10 * 40 + 200 * 38 + 400 * 48 + 300 * 70 + 90 * 90) / 1000)
    y = M.year_on_year(c, 1, lag=1)
    assert y[["quarter_0", "quarter_1"]].values.tolist() == [["2024-06", "2025-06"]]
    assert y["mix"].iloc[0] + y["within"].iloc[0] == pytest.approx(y["change"].iloc[0])
    g = M.rebuild_gaps(df, STAY, 1).set_index("quarter")
    assert g.loc["2024-06", "gap"] == pytest.approx((10 * 40 + 200 * 40 + 400 * 50 + 300 * 70 + 90 * 90) / 1000 - 55.8)


def test_admitted_split_is_an_identity():
    row = pd.Series({"admitted_pct": 25.0, "admitted_within_4h_pct": 30.0, "stay_within_4h_pct": 60.0})
    s = M.admitted_split(row)
    assert s.loc["not admitted", "rate"] == pytest.approx((60 - 0.25 * 30) / 0.75)       # 70
    assert M.rebuilt(s) == pytest.approx(60)
    # worst case: stays and the admitted share read high, the admitted rate reads low
    assert M.implied_margin(row, 0.05) == pytest.approx((60.05 - 0.2505 * 29.95) / 0.7495 - 70, abs=1e-9)
    assert M.implied_margin(row, 0.5) > M.implied_margin(row, 0.05) > 0


# ------------------------------------------------------------------ real data
@pytest.fixture(scope="module")
def r(snapshot):
    return mix_report.analyse(snapshot)


def test_real_periods(r):
    assert (r["q0"], r["q1"], r["q_long"]) == ("2024-06", "2026-06", "2023-06")


def test_real_state_split(r):
    d = r["state"][STAY]
    assert [round(d[k], 2) for k in ("rate_0", "rate_1", "change", "mix", "within")] == [59.14, 56.09, -3.05, -1.14, -1.91]
    assert d["mix"] + d["within"] == pytest.approx(d["change"])
    long = r["state_long"][STAY]
    assert [round(long[k], 2) for k in ("change", "mix", "within")] == [-5.37, -1.37, -4.0]
    assert [round(r["state"][SEEN][k], 2) for k in ("change", "mix", "within")] == [1.3, -0.48, 1.78]
    assert [round(r["state"][ADM4][k], 2) for k in ("change", "mix", "within")] == [-3.1, -0.06, -3.04]
    assert [round(r["state"][ADM][k], 2) for k in ("change", "mix", "within")] == [0.86, 1.13, -0.27]


def test_real_rebuilt_rates_match_the_published_ones(r, snapshot):
    whole = r["whole"]
    for m in (STAY, ADM, ADM4):
        g = r["gaps"][m]
        assert g.loc[~g["quarter"].isin(whole), "gap"].abs().max() < 0.1, m
        assert g.loc[g["quarter"].isin(whole), "gap"].abs().max() < 0.6, m
    seen = r["gaps"][SEEN]
    assert (seen.loc[~seen["quarter"].isin(whole), "gap"] > 0.2).all()       # the one measure that does not rebuild


def test_real_split_adds_up_everywhere(snapshot):
    c = M.cells(snapshot, STAY)
    codes = snapshot.loc[snapshot["quarter"] == "2024-06", "facility_code"].unique()
    done = 0
    for code in codes:
        try:
            d = M.decompose(M.unit(c, "2024-06", code), M.unit(c, "2026-06", code))
        except M.Incomplete:
            continue
        assert d["mix"] + d["within"] == pytest.approx(d["change"], abs=1e-9)
        done += 1
    assert done == len(codes) == 105                                   # 104 hospitals and the state row


def test_real_groups_and_hospitals(r):
    assert (len(r["big"]), len(r["rest"]), len(r["only_end"])) == (22, 82, 1)
    lg, rest = r["groups"]["large"][STAY], r["groups"]["rest"][STAY]
    assert [round(lg[k], 2) for k in ("change", "mix", "within")] == [-3.47, -0.6, -2.87]
    assert [round(rest[k], 2) for k in ("change", "mix", "within")] == [-1.43, -1.14, -0.29]
    h = r["hospitals"][STAY]
    assert len(h) == 22 and int((h["change"] < 0).sum()) == 18
    assert h.iloc[0]["facility_name"] == "Sunshine Coast University" and h.iloc[-1]["facility_name"] == "Queensland Children's"
    # the rebuilt rates behind the split agree with what each hospital published
    assert (h["rate_0"] - h["published_0"]).abs().max() < 0.1 and (h["rate_1"] - h["published_1"]).abs().max() < 0.1


def test_real_admitted_split(r):
    sp = r["adm_split"]
    assert sp["rate_0"] == pytest.approx(59.1) and sp["rate_1"] == pytest.approx(56.1)
    by = sp["by_category"]
    assert by.loc["not admitted", ["rate_0", "rate_1"]].round(1).tolist() == [68.7, 66.2]
    assert round(sp["mix"], 2) == -0.31 and by["within"].round(2).tolist() == [-0.91, -1.78]
    assert r["adm_margin"] < 0.15


def test_report_and_csvs_regenerate_byte_for_byte(r, root):
    report, csvs = mix_report.build_report(r)
    assert report.encode() == (root / "results" / "MIX_VS_PERFORMANCE.md").read_bytes()
    assert len(csvs) == 5
    for name, frame in csvs.items():
        expected = frame.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode()
        assert expected == (root / "results" / name).read_bytes(), name


def test_charts_regenerate_byte_for_byte(r, root, tmp_path):
    mix_report.chart_fixed_mix(r["fixed"], r["quarters"][0], tmp_path / "04_fixed_mix.png")
    mix_report.chart_effects(r["state"], r["q0"], r["q1"], tmp_path / "05_mix_vs_within.png")
    mix_report.chart_hospitals(r["hospitals"][STAY], r["q0"], r["q1"], tmp_path / "06_large_hospitals.png")
    made = sorted(tmp_path.glob("*.png"))
    assert len(made) == 3
    for png in made:
        assert png.read_bytes() == (root / "results" / "charts" / png.name).read_bytes(), png.name


def test_report_has_no_hyphen_minus_numbers_or_negative_zero(root):
    import re
    text = (root / "results" / "MIX_VS_PERFORMANCE.md").read_text(encoding="utf-8")
    assert not re.search(r"(?<![\w-])-\d", text)
    assert not re.search(r"[−+]0\.0+(?!\d)", text)
