"""The star schema (Part 5): the SQL on hand-made rows, then on the real snapshot."""
import pandas as pd
import pytest

from edperf import doors as D, load, mix as M, star
from scripts import export_powerbi, mix_report
from tests.conftest import make_rows as _make_rows

Q0, Q1 = "2024-06", "2026-06"


def make_rows(quarter, code, name, att, **cols):
    """conftest.make_rows, with five-value lists padded for the ALL row: the
    total for a count, blank for a percentage."""
    for key, value in cols.items():
        if isinstance(value, list) and len(value) == 5:
            cols[key] = value + [sum(value) if key in ("did_not_wait", "left_after_treatment") else float("nan")]
    return _make_rows(quarter, code, name, att, **cols)


def scorecard_csv(path, codes, **cols):
    """A scorecard file with just the columns the SQL reads."""
    n = len(codes)
    d = pd.DataFrame({
        "facility_code": codes, "facility_name": [f"H{c}" for c in codes],
        "peer_group": cols.get("peer_group", ["small"] * n), "attendances": cols.get("attendances", [100] * n),
        "published_0": 70.0, "published_1": 60.0, "standardised": 61.0, "peer_median": 65.0, "vs_peers": -4.0,
        "level": cols.get("level", ["below peers"] * n), "change": -10.0, "mix": -1.0, "within": -9.0, "bar": 2.0,
        "trend": cols.get("trend", ["slipping"] * n), "patients_equivalent": -9.0, "seen_within": 1.0,
        "seen_trend": "no clear change",
    })
    d.to_csv(path, index=False)
    return path


def doors_csv(path, codes, **cols):
    n = len(codes)
    d = pd.DataFrame({
        "facility_code": codes, "admission_share": 0.5, "admitted": -4.0,
        "admitted_trend": cols.get("admitted_trend", ["slipping"] * n), "admitted_robust": [True] * n,
        "not_admitted": -5.5, "not_admitted_trend": cols.get("not_admitted_trend", ["no clear change"] * n),
        "not_admitted_robust": [False] * n, "pattern": "admitted only", "median_wait_0": 1, "median_wait_1": 9,
        "wait_step": [True] * n, "dnw_trend": "rising", "left_trend": "falling",
    })
    d.to_csv(path, index=False)
    return path


def build(tmp_path, frames, codes, doors_codes=None, **cols):
    snap = tmp_path / "snap.csv"
    pd.concat(frames, ignore_index=True).to_csv(snap, index=False)
    return star.build(snap, scorecard_csv(tmp_path / "card.csv", codes, **cols),
                      doors_csv(tmp_path / "doors.csv", codes if doors_codes is None else doors_codes, **cols),
                      Q0, Q1)


def one(con, sql):
    return con.execute(sql).fetchone()


@pytest.fixture()
def toy(tmp_path):
    """Two hospitals in two quarters, plus a state row that must be left out."""
    att = [10, 40, 100, 40, 10]
    frames = [
        make_rows(Q0, 1, "H1", att, stay_within_4h_pct=[50.0, 60.0, 70.0, 80.0, 90.0], admitted_pct=25.0,
                  admitted_within_4h_pct=40.0, seen_on_time_pct=80.0, did_not_wait=[0, 1, 2, 3, 4]),
        make_rows(Q1, 1, "H1", att, stay_within_4h_pct=60.0, admitted_pct=[80.0, 50.0, 30.0, 10.0, 0.0],
                  admitted_within_4h_pct=[20.0, 30.0, 40.0, 50.0, float("nan")]),
        make_rows(Q0, 2, "H2", [0, 0, 50, 50, 0], stay_within_4h_pct=[float("nan")] * 2 + [90.0, 95.0, float("nan")],
                  admitted_pct=[float("nan")] * 2 + [10.0, 0.0, float("nan")],
                  admitted_within_4h_pct=[float("nan")] * 2 + [50.0] + [float("nan")] * 2,
                  seen_on_time_pct=[float("nan")] * 2 + [90.0, 90.0, float("nan")]),
        make_rows(Q1, 2, "H2", [0, 0, 50, 50, 0], stay_within_4h_pct=80.0),
        make_rows(Q0, load.STATE_CODE, "Queensland", [10, 40, 150, 90, 10]),
        make_rows(Q1, load.STATE_CODE, "Queensland", [10, 40, 150, 90, 10]),
    ]
    return build(tmp_path, frames, [1, 2])


def test_fact_has_one_row_per_hospital_quarter_and_category_and_no_state_row(toy):
    assert one(toy, "select count(*), count(distinct hospital_key) from fct_ed_triage_quarter") == (20, 2)
    assert one(toy, "select count(*) from fct_hospital_quarter_published") == (4,)
    assert one(toy, "select count(*), sum(attendances_published) from state_published_quarter") == (2, 600)


def test_counts_are_attendances_times_the_published_rate(toy):
    stays, base, seen, admitted = one(toy, f"""
        select sum(stays_within_4h), sum(stays_4h_base), sum(seen_on_time), sum(admitted)
        from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
        where hospital_key = 1 and quarter_code = '{Q0}'""")
    # 10 x 50% + 40 x 60% + 100 x 70% + 40 x 80% + 10 x 90%
    assert stays == pytest.approx(5 + 24 + 70 + 32 + 9)
    assert base == 200
    assert seen == pytest.approx(160)
    assert admitted == pytest.approx(50)


def test_streams_add_back_and_the_not_admitted_rate_is_the_implied_one(toy):
    row = one(toy, f"""
        select stream_admitted, stream_admitted_within_4h, stream_not_admitted, stream_not_admitted_within_4h
        from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
        where hospital_key = 1 and quarter_code = '{Q1}' and triage_key = 2""")
    # 40 patients, 50% admitted, 30% of those within 4 hours, 60% of everyone within 4 hours
    assert row == pytest.approx((20, 6, 20, 18))
    # implied not-admitted rate = (60 - 0.5 x 30) / 0.5 = 90%
    assert row[3] / row[2] == pytest.approx(0.9)


def test_nobody_admitted_means_nobody_admitted_within_4_hours(toy):
    # category 5 in Q1: admitted share 0 and no published admitted-within-4h rate
    row = one(toy, f"""
        select admitted, stream_admitted, stream_admitted_within_4h, stream_not_admitted, stream_not_admitted_within_4h
        from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
        where hospital_key = 1 and quarter_code = '{Q1}' and triage_key = 5""")
    assert row == pytest.approx((0, 0, 0, 10, 6))


def test_a_category_with_no_attendances_counts_as_zero_not_missing(toy):
    rows = toy.execute(f"""
        select attendances, stays_within_4h, stays_4h_base, admitted, seen_on_time, stream_not_admitted
        from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
        where hospital_key = 2 and quarter_code = '{Q0}' and triage_key in (1, 2, 5)""").fetchall()
    assert rows == [(0, 0.0, 0.0, 0.0, 0.0, 0.0)] * 3
    rate = one(toy, f"""
        select sum(stays_within_4h) / sum(stays_4h_base)
        from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
        where hospital_key = 2 and quarter_code = '{Q0}'""")[0]
    assert rate == pytest.approx((45 + 47.5) / 100)


def test_a_missing_rate_leaves_both_sides_of_the_division(tmp_path):
    # a normal quarter (zeros are published as zeros): category 3 has patients but no 4-hour rate
    frames = [make_rows(q, 1, "H1", [10, 40, 100, 40, 10], stay_within_4h_pct=[50.0, 60.0, float("nan"), 80.0, 90.0])
              for q in (Q0, Q1)]
    con = build(tmp_path, frames, [1])
    assert one(con, "select count(*) from dim_quarter where zero_published_as_dash") == (0,)
    stays, base, attendances = one(con, f"""
        select sum(stays_within_4h), sum(stays_4h_base), sum(attendances)
        from fct_ed_triage_quarter f join dim_quarter q using (quarter_key) where quarter_code = '{Q0}'""")
    assert (stays, base, attendances) == pytest.approx((5 + 24 + 32 + 9, 100, 200))
    # and the streams of that row are unknown, not zero
    assert one(con, "select count(*) from fct_ed_triage_quarter where stream_admitted is null") == (2,)


def test_a_dash_quarter_reads_a_blank_as_zero(tmp_path):
    # Q0 publishes zero as blank: no row with did_not_wait = 0 shows 0%
    dash = make_rows(Q0, 1, "H1", [10, 40, 100, 40, 10], did_not_wait_pct=float("nan"),
                     admitted_pct=[float("nan"), 50.0, 30.0, 10.0, float("nan")],
                     stay_within_4h_pct=[float("nan"), 60.0, 70.0, 80.0, 90.0])
    normal = make_rows(Q1, 1, "H1", [10, 40, 100, 40, 10])
    con = build(tmp_path, [dash, normal], [1])
    assert con.execute("select quarter_code from dim_quarter where zero_published_as_dash").fetchall() == [(Q0,)]
    admitted, base, stays, stay_base, published_blank = one(con, f"""
        select sum(admitted), sum(admitted_base), sum(stays_within_4h), sum(stays_4h_base),
               count(*) filter (where admitted_pct_published is null)
        from fct_ed_triage_quarter f join dim_quarter q using (quarter_key) where quarter_code = '{Q0}'""")
    assert (admitted, base) == pytest.approx((20 + 30 + 4, 200))
    assert (stays, stay_base) == pytest.approx((24 + 70 + 32 + 9, 200))
    assert published_blank == 2      # the published columns keep the blank


def test_a_few_blank_zeros_do_not_make_a_dash_quarter(tmp_path):
    # one hospital in three leaves its zero percentages blank: still a normal quarter,
    # so its blank 4-hour rate stays unknown instead of becoming 0%
    frames = []
    for q in (Q0, Q1):
        frames += [make_rows(q, 1, "H1", [10, 40, 100, 40, 10]), make_rows(q, 2, "H2", [10, 40, 100, 40, 10]),
                   make_rows(q, 3, "H3", [10, 40, 100, 40, 10], did_not_wait_pct=float("nan"),
                             stay_within_4h_pct=[float("nan"), 60.0, 70.0, 80.0, 90.0])]
    con = build(tmp_path, frames, [1, 2, 3])
    assert one(con, "select count(*) from dim_quarter where zero_published_as_dash") == (0,)
    assert one(con, "select count(*) from fct_ed_triage_quarter where stays_within_4h is null") == (2,)


def test_dimensions(toy):
    assert toy.execute("""
        select quarter_key, quarter_label, quarter_start::varchar, financial_year, quarter_of_year,
               quarter_index, comparison_role
        from dim_quarter order by quarter_key""").fetchall() == [
        (202406, "Apr-Jun 2024", "2024-04-01", 2024, 2, 1, "start"),
        (202606, "Apr-Jun 2026", "2026-04-01", 2026, 2, 2, "latest")]
    assert one(toy, "select count(*), sum(recommended_minutes) from dim_triage") == (5, 220)
    assert toy.execute("select hospital_key, hospital_name, quarters_reported from dim_hospital order by 1").fetchall() \
        == [(1, "H1", 2), (2, "H2", 2)]


def test_peer_groups_sort_large_to_small(tmp_path):
    frames = [make_rows(q, c, f"H{c}", [10, 40, 100, 40, 10]) for q in (Q0, Q1) for c in (1, 2, 3)]
    con = build(tmp_path, frames, [1, 2, 3], peer_group=["small", "large", "medium"], attendances=[200, 20000, 5000])
    assert con.execute("""
        select peer_group, peer_group_sort, peer_group_label, latest_attendances, peer_group_quarter
        from dim_hospital order by peer_group_sort""").fetchall() == [
        ("large", 1, "Large (10,000 or more)", 20000, Q1),
        ("medium", 2, "Medium (2,500 to 9,999)", 5000, Q1),
        ("small", 3, "Small (under 2,500)", 200, Q1)]


def test_financial_year_runs_july_to_june(tmp_path):
    frames = [make_rows(q, 1, "H1", [1, 1, 1, 1, 1]) for q in ("2025-06", "2025-09", "2025-12", "2026-03", Q0, Q1)]
    con = build(tmp_path, frames, [1])
    got = dict(con.execute("select quarter_code, financial_year from dim_quarter").fetchall())
    assert (got["2025-06"], got["2025-09"], got["2025-12"], got["2026-03"]) == (2025, 2026, 2026, 2026)


def test_scorecard_verdicts_carry_over_and_a_new_hospital_gets_no_stream_verdict(tmp_path):
    frames = [make_rows(q, c, f"H{c}", [10, 40, 100, 40, 10]) for q in (Q0, Q1) for c in (1, 2)]
    con = build(tmp_path, frames, [1, 2], doors_codes=[1], trend=["slipping", "new"],
                level=["below peers", "below peers"])
    rows = con.execute("""
        select hospital_key, trend, below_peers_and_slipping, admitted_stream_trend,
               admitted_verdict_survives_rounding, not_admitted_stream_trend,
               not_admitted_verdict_survives_rounding, slipping_pattern, wait_step, trend_sort
        from hospital_scorecard order by hospital_key""").fetchall()
    assert rows[0] == (1, "slipping", True, "slipping", True, "no clear change", None, "admitted only", True, 1)
    assert rows[1] == (2, "new", False, "new", None, "new", None, "new", False, 4)


def test_check_stops_a_star_that_lost_rows(toy):
    toy.execute("delete from fct_ed_triage_quarter where hospital_key = 2 and triage_key = 3")
    with pytest.raises(star.StarError, match="fact rows"):
        star.check(toy)


def test_check_stops_a_duplicate_key_and_an_orphan(toy):
    toy.execute("insert into dim_triage select * from dim_triage where triage_key = 1")
    toy.execute("delete from dim_hospital where hospital_key = 2")
    with pytest.raises(star.StarError) as err:
        star.check(toy)
    assert "dim_triage: duplicate triage_key" in str(err.value)
    assert "fct_ed_triage_quarter rows with no dim_hospital" in str(err.value)


def test_check_stops_streams_that_do_not_add_back(toy):
    toy.execute("update fct_ed_triage_quarter set stream_not_admitted = stream_not_admitted + 1 where triage_key = 3")
    with pytest.raises(star.StarError, match="streams do not add back"):
        star.check(toy)


def test_export_refuses_a_file_that_differs(toy, tmp_path, monkeypatch):
    real = star.profile

    def tampered(con, relation):
        result = real(con, relation)
        if relation.startswith("read_parquet") and "dim_hospital" in relation:
            result["rows"] -= 1
        return result
    monkeypatch.setattr(star, "profile", tampered)
    with pytest.raises(star.StarError, match="dim_hospital.parquet"):
        star.export(toy, tmp_path / "out")


# ---- the real snapshot ------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    return export_powerbi.connect()


def test_real_star_matches_the_snapshot(real, snapshot):
    h = snapshot[~snapshot["is_state_total"]]
    cats, allrows = h[h["triage"] != "ALL"], h[h["triage"] == "ALL"]
    assert one(real, "select count(*), sum(attendances), sum(did_not_wait) from fct_ed_triage_quarter") == (
        len(cats), int(allrows["attendances"].sum()), int(allrows["did_not_wait"].sum()))
    assert one(real, "select count(*) from fct_hospital_quarter_published") == (len(allrows),)
    assert one(real, "select count(*) from dim_hospital") == (h["facility_code"].nunique(),)
    assert one(real, "select count(*) from dim_quarter") == (snapshot["quarter"].nunique(),)


def test_real_comparison_quarters_and_precision_flags_match_part_2(real, snapshot):
    p = mix_report.periods(snapshot)
    assert dict(real.execute(
        "select comparison_role, quarter_code from dim_quarter where comparison_role is not null").fetchall()) \
        == {"start": p["q0"], "latest": p["q1"]}
    whole = {q for (q,) in real.execute("select quarter_code from dim_quarter where whole_number_rates").fetchall()}
    assert whole == p["whole"]
    dash = [q for (q,) in real.execute(
        "select quarter_code from dim_quarter where zero_published_as_dash order by 1").fetchall()]
    assert dash == ["2023-06", "2023-09", "2023-12", "2024-03"]


def test_real_every_row_with_attendances_has_a_usable_rate(real):
    # the guide says so: each base equals attendances in the current data
    assert one(real, """
        select count(*) filter (where stays_within_4h is null or admitted is null or seen_on_time is null
                                   or stream_admitted is null),
               sum(attendances) - sum(stays_4h_base), sum(attendances) - sum(admitted_base),
               sum(attendances) - sum(seen_on_time_base),
               sum(attendances) - sum(stream_admitted) - sum(stream_not_admitted)
        from fct_ed_triage_quarter""") == pytest.approx((0, 0, 0, 0, 0), abs=1e-6)


def test_real_pooled_rates_equal_the_python_pools(real, snapshot):
    """Large and small hospitals at both comparison quarters: the SQL ratio of
    sums is the pooled rate that Parts 2 and 4 use."""
    p = mix_report.periods(snapshot)
    stay, streams = M.cells(snapshot, D.STAY), D.stream_cells(snapshot)
    for group in ("large", "small"):
        codes = [c for (c,) in real.execute(
            f"select hospital_key from dim_hospital where peer_group = '{group}'").fetchall()]
        for q in (p["q0"], p["q1"]):
            got = one(real, f"""
                select 100 * sum(stays_within_4h) / sum(stays_4h_base),
                       100 * sum(stream_admitted_within_4h) / sum(stream_admitted),
                       100 * sum(stream_not_admitted_within_4h) / sum(stream_not_admitted),
                       100 * sum(stream_admitted) / sum(attendances)
                from fct_ed_triage_quarter f join dim_quarter d using (quarter_key) join dim_hospital h using (hospital_key)
                where h.peer_group = '{group}' and d.quarter_code = '{q}'""")
            u = D.pool(streams, q, codes)
            want = (M.rebuilt(M.pool(stay, q, codes)), D.stream_rate(u, "admitted"),
                    D.stream_rate(u, "not admitted"), D.stream_share(u, "admitted"))
            assert got == pytest.approx(want, abs=1e-9), (group, q)


def test_real_hospital_rates_rebuild_the_published_figures(real):
    worst = real.execute("""
        with model as (
            select hospital_key, quarter_key, 100 * sum(stays_within_4h) / sum(stays_4h_base) as stay,
                   100 * sum(admitted) / sum(admitted_base) as admitted
            from fct_ed_triage_quarter group by all
        )
        select q.whole_number_rates, max(abs(m.stay - p.stay_within_4h_pct)),
               max(abs(m.admitted - coalesce(p.admitted_pct, 0)))
        from model m join fct_hospital_quarter_published p using (hospital_key, quarter_key)
        join dim_quarter q using (quarter_key) group by 1 order by 1""").fetchall()
    assert worst[0][1] < 0.1 and worst[0][2] < 0.1          # one-decimal quarters
    assert worst[1][1] < 1.0 and worst[1][2] < 1.0          # whole-number quarters


def test_real_scorecard_is_the_part_3_and_part_4_tables(real, root):
    card = pd.read_csv(root / "results" / "scorecard_hospitals.csv")
    doors = pd.read_csv(root / "results" / "doors_hospitals.csv")
    got = real.execute("""
        select hospital_key, level, trend, within_category_effect, slipping_pattern, wait_step,
               triage_mix_effect + admission_share_effect + admitted_stream_effect + not_admitted_stream_effect
                   - change_points as leftover
        from hospital_scorecard order by hospital_key""").df()
    want = card.sort_values("facility_code").reset_index(drop=True)
    assert got["hospital_key"].tolist() == want["facility_code"].tolist()
    assert got["level"].tolist() == want["level"].tolist()
    assert got["trend"].tolist() == want["trend"].tolist()
    assert int(got["wait_step"].sum()) == int(doors["wait_step"].sum())
    # the four effects still add up to the change (the CSVs are rounded to 4 places)
    assert got["leftover"].abs().max() < 3e-4
    assert got["leftover"].isna().sum() == 1                 # the hospital that is new in the latest quarter
    assert got["within_category_effect"].tolist() == pytest.approx(want["within"].tolist(), nan_ok=True)
    # a rounding verdict exists only where a stream is flagged: 37 of 40 admitted, 47 of 50 not admitted
    flags = dict(real.execute("""
        select 'admitted', [count(admitted_verdict_survives_rounding),
                            count(*) filter (where admitted_verdict_survives_rounding)]
        from hospital_scorecard
        union all
        select 'not admitted', [count(not_admitted_verdict_survives_rounding),
                                count(*) filter (where not_admitted_verdict_survives_rounding)]
        from hospital_scorecard""").fetchall())
    for stream, column in (("admitted", "admitted"), ("not admitted", "not_admitted")):
        flagged = doors[doors[f"{column}_trend"].isin(["slipping", "improving"])]
        assert flags[stream] == [len(flagged), int(flagged[f"{column}_robust"].sum())]
    assert flags == {"admitted": [40, 37], "not admitted": [50, 47]}
    patterns = got[got["trend"] != "new"].set_index("hospital_key")["slipping_pattern"]
    assert patterns.to_dict() == doors.set_index("facility_code")["pattern"].to_dict()
