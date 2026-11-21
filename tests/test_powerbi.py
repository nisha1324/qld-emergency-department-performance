"""The Power BI pack (Part 5): Parquet files, check values, the DAX file and the guide.

Power BI cannot run here, so the DAX itself is not executed. What is tested:
the committed Parquet holds exactly what the SQL builds from the committed
snapshot and results; every value in CHECKS.md (SQL over the Parquet with the
DAX's logic) agrees with the Python analysis of Parts 1 to 4 or with the
snapshot read independently in pandas; and measures.dax is consistent with
the export (tables and columns exist, every measure used is defined, one
check query per CHECKS section).
"""
import json
import re

import pandas as pd
import pytest

from edperf import doors as D, mix as M, star
from scripts import export_powerbi, mix_report, powerbi_checks

STAY = D.STAY


@pytest.fixture(scope="module")
def powerbi(root):
    return root / "powerbi"


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("powerbi")
    return out, export_powerbi.export(out)


@pytest.fixture(scope="module")
def check(exported):
    out, _ = exported
    by_title = {c["query"].split(". ", 1)[1]: c for c in powerbi_checks.checks(powerbi_checks.connect(out))}

    def rows(title):
        c = by_title[title]
        return [dict(zip(c["headers"], r)) for r in c["rows"]]
    return rows


@pytest.fixture(scope="module")
def periods(snapshot):
    return mix_report.periods(snapshot)


@pytest.fixture(scope="module")
def hospitals(snapshot):
    return snapshot[~snapshot["is_state_total"]]


# ---- committed files are current --------------------------------------------

def test_committed_parquet_is_byte_for_byte_a_fresh_export(exported, powerbi):
    out, _ = exported
    names = sorted(p.name for p in out.glob("*.parquet"))
    assert names == sorted(f"{t}.parquet" for t, _ in star.TABLES)
    assert names == sorted(p.name for p in (powerbi / "data").glob("*.parquet"))
    for name in names:
        assert (out / name).read_bytes() == (powerbi / "data" / name).read_bytes(), \
            f"{name} is stale: rerun scripts/export_powerbi.py"


def test_committed_manifest_matches_a_fresh_export(exported, powerbi):
    _, manifest = exported
    assert json.loads((powerbi / "data" / "MANIFEST.json").read_text()) == manifest


def test_committed_checks_match_a_fresh_export(exported, powerbi):
    out, _ = exported
    assert powerbi_checks.build(out) == (powerbi / "CHECKS.md").read_text(encoding="utf-8"), \
        "powerbi/CHECKS.md is stale: rerun scripts/powerbi_checks.py"


# ---- check values against the analysis --------------------------------------

def test_state_by_quarter_matches_pandas_and_is_close_to_the_published_figure(check, hospitals, snapshot):
    got = check("Queensland by quarter")
    allrows = hospitals[hospitals["triage"] == "ALL"].groupby("quarter")
    cats = hospitals[(hospitals["triage"] != "ALL") & (hospitals["attendances"] > 0)]
    state = snapshot[snapshot["is_state_total"] & (snapshot["triage"] == "ALL")].set_index("quarter")
    whole = mix_report.periods(snapshot)["whole"]
    assert len(got) == snapshot["quarter"].nunique()
    for r, (q, g) in zip(got, allrows):
        assert r["quarter_label"] == mix_report.B.qname(q)
        assert r["hospitals"] == len(g) and r["attendances"] == g["attendances"].sum()
        assert r["did not wait"] == pytest.approx(g["did_not_wait"].sum() / g["attendances"].sum(), abs=1e-12)
        c = cats[cats["quarter"] == q]
        # blanks in these quarters are zeros (the dash quarters); elsewhere there are none
        stay = (c["attendances"] * c["stay_within_4h_pct"].fillna(0)).sum() / c["attendances"].sum() / 100
        assert r["4-hour stays"] == pytest.approx(stay, abs=1e-12)
        published = state.loc[q, "stay_within_4h_pct"]
        assert r["published"] == pytest.approx(published / 100)
        # close to the published figure, as the note in CHECKS.md says
        assert abs(100 * r["4-hour stays"] - published) <= (0.5 if q in whole else 0.1), q


def test_peer_groups_match_parts_2_and_4(check, snapshot, periods, root):
    card = pd.read_csv(root / "results" / "scorecard_hospitals.csv")
    stay, streams = M.cells(snapshot, STAY), D.stream_cells(snapshot)
    reported = {q: set(g["facility_code"]) for q, g in snapshot.groupby("quarter")}
    got = check("Peer groups at the two comparison quarters")
    assert len(got) == 6
    labels = {"Large": "large", "Medium": "medium", "Small": "small"}
    for r in got:
        group = labels[r["peer_group_label"].split(" ")[0]]
        q = periods["q0"] if r["quarter_label"] == mix_report.B.qname(periods["q0"]) else periods["q1"]
        codes = [c for c in card.loc[card["peer_group"] == group, "facility_code"] if c in reported[q]]
        u = D.pool(streams, q, codes)
        assert r["hospitals"] == len(codes)
        assert 100 * r["4-hour stays"] == pytest.approx(M.rebuilt(M.pool(stay, q, codes)), abs=1e-9)
        assert 100 * r["admitted"] == pytest.approx(D.stream_share(u, "admitted"), abs=1e-9)
        assert 100 * r["admitted: 4-hour stays"] == pytest.approx(D.stream_rate(u, "admitted"), abs=1e-9)
        assert 100 * r["not admitted: 4-hour stays (implied)"] == pytest.approx(
            D.stream_rate(u, "not admitted"), abs=1e-9)


def test_peer_group_rates_are_the_ones_part_4_published(check, root):
    """The large and small rows equal results/doors_peer_groups.csv (same hospitals in both quarters)."""
    groups = pd.read_csv(root / "results" / "doors_peer_groups.csv").set_index("group")
    got = check("Peer groups at the two comparison quarters")
    for name, label in (("large", "Large"), ("small", "Small")):
        start, latest = [r for r in got if r["peer_group_label"].startswith(label)]
        assert 100 * start["4-hour stays"] == pytest.approx(groups.loc[name, "rate_0"], abs=5e-5)
        assert 100 * latest["4-hour stays"] == pytest.approx(groups.loc[name, "rate_1"], abs=5e-5)
        assert 100 * latest["admitted: 4-hour stays"] == pytest.approx(groups.loc[name, "admitted_rate_1"], abs=5e-5)
        assert 100 * latest["not admitted: 4-hour stays (implied)"] == pytest.approx(
            groups.loc[name, "not_admitted_rate_1"], abs=5e-5)


def test_triage_categories_match_pandas(check, hospitals, periods):
    got = check("Triage categories, latest quarter")
    c = hospitals[(hospitals["quarter"] == periods["q1"]) & (hospitals["triage"] != "ALL")]
    total = c["attendances"].sum()
    assert [r["triage_label"][0] for r in got] == ["1", "2", "3", "4", "5"]
    assert sum(r["share"] for r in got) == pytest.approx(1)
    for r in got:
        g = c[c["triage"] == r["triage_label"][0]]
        g = g[g["attendances"] > 0]
        assert r["attendances"] == g["attendances"].sum()
        assert r["share"] == pytest.approx(g["attendances"].sum() / total, abs=1e-12)
        for column, measure in (("4-hour stays", "stay_within_4h_pct"), ("admitted", "admitted_pct"),
                                ("seen on time (rebuilt)", "seen_on_time_pct")):
            assert r[column] == pytest.approx(
                (g["attendances"] * g[measure]).sum() / g["attendances"].sum() / 100, abs=1e-12), column


def test_year_on_year_matches_check_1(check):
    by_quarter = check("Queensland by quarter")
    got = check("Change on the same quarter a year earlier")
    assert len(got) == len(by_quarter) - 4
    for i, r in enumerate(got):
        now, earlier = by_quarter[i + 4], by_quarter[i]
        assert r["quarter_label"] == now["quarter_label"]
        assert r["quarter_label"].split(" ")[0] == earlier["quarter_label"].split(" ")[0]   # same quarter of the year
        assert r["4-hour stays"] == now["4-hour stays"] and r["year earlier"] == earlier["4-hour stays"]
        assert r["change (points)"] == pytest.approx(100 * (now["4-hour stays"] - earlier["4-hour stays"]))
        assert r["attendances change"] == pytest.approx(now["attendances"] / earlier["attendances"] - 1)


def test_scorecard_counts_match_part_3_and_part_4(check, root):
    card = pd.read_csv(root / "results" / "scorecard_hospitals.csv")
    doors = pd.read_csv(root / "results" / "doors_hospitals.csv")
    priority = pd.read_csv(root / "results" / "scorecard_priority.csv")
    step = set(doors.loc[doors["wait_step"], "facility_code"])
    got = check("Scorecard counts by peer group")
    assert [r["peer_group_label"].split(" ")[0].lower() for r in got] == ["large", "medium", "small"]
    for r in got:
        k = card[card["peer_group"] == r["peer_group_label"].split(" ")[0].lower()]
        assert r["hospitals"] == len(k)
        for trend in ("slipping", "no clear change", "improving"):
            assert r[trend] == (k["trend"] == trend).sum()
        assert r["below peers and slipping"] == ((k["level"] == "below peers") & (k["trend"] == "slipping")).sum()
        assert r["wait step"] == k["facility_code"].isin(step).sum()
    assert sum(r["below peers and slipping"] for r in got) == len(priority)


def test_large_priority_hospitals_match_part_3(check, root):
    priority = pd.read_csv(root / "results" / "scorecard_priority.csv")
    doors = pd.read_csv(root / "results" / "doors_hospitals.csv").set_index("facility_name")
    want = priority[priority["peer_group"] == "large"].sort_values("within")
    got = check("Large hospitals below peers and slipping")
    assert [r["hospital_name"] for r in got] == want["facility_name"].tolist()
    for r, w in zip(got, want.itertuples()):
        assert r["change (points)"] == pytest.approx(w.change, abs=5e-5)
        assert r["within category (points)"] == pytest.approx(w.within)
        # the model's rate is the published figure, to the rounding of the category rates
        assert 100 * r["4-hour stays, start"] == pytest.approx(w.published_0, abs=0.1)
        assert 100 * r["4-hour stays, latest"] == pytest.approx(w.published_1, abs=0.1)
        assert r["slipping in"] == doors.loc[r["hospital_name"], "pattern"]


def test_blank_as_zero_fits_the_published_figure_and_dropping_does_not(check):
    got = check("A blank that means zero (Oct-Dec 2023)")
    assert [r["hospital_name"] for r in got] == sorted(powerbi_checks.TRAP_HOSPITALS)
    for r in got:
        assert abs(r["admitted"] - r["published"]) <= 0.005          # rounds to the published whole number
        assert r["admitted if blank rows are dropped"] > r["admitted"]
    assert sum(abs(r["admitted if blank rows are dropped"] - r["published"]) > 0.005 for r in got) == len(got)


def test_blank_as_zero_fits_better_across_all_four_quarters(hospitals):
    """The rule's evidence, in pandas: wherever a category's admitted share is
    blank in the four dash quarters, compare both readings with the published
    all-categories figure (a whole number, so 'fits' means within 1 point)."""
    cats = hospitals[(hospitals["triage"] != "ALL") & (hospitals["attendances"] > 0)]
    allrows = hospitals[hospitals["triage"] == "ALL"].set_index(["quarter", "facility_code"])
    zero_fits = drop_fits = n = 0
    for (q, code), g in cats.groupby(["quarter", "facility_code"]):
        published = allrows.loc[(q, code), "admitted_pct"]
        if not g["admitted_pct"].isna().any() or pd.isna(published):
            continue
        known = g[g["admitted_pct"].notna()]
        n += 1
        zero = (g["attendances"] * g["admitted_pct"].fillna(0)).sum() / g["attendances"].sum()
        zero_fits += abs(zero - published) <= 1.0
        if len(known):
            dropped = (known["attendances"] * known["admitted_pct"]).sum() / known["attendances"].sum()
            drop_fits += abs(dropped - published) <= 1.0
    assert (n, zero_fits, drop_fits) == (83, 83, 62)


def test_blank_evidence_in_checks_is_the_pandas_count(exported):
    out, _ = exported
    e = powerbi_checks.blank_evidence(powerbi_checks.connect(out))
    assert e == {"hospital_quarters": 83, "zero_fits": 83, "dropped_fits": 62, "quarters": 4}


def test_totals_match_the_snapshot(check, hospitals):
    got = {r["column"]: r["value"] for r in check("Totals")}
    allrows = hospitals[hospitals["triage"] == "ALL"]
    cats = hospitals[hospitals["triage"] != "ALL"]
    assert got["fact rows"] == len(cats)
    assert got["attendances, all quarters"] == allrows["attendances"].sum()
    assert got["did not wait, all quarters"] == allrows["did_not_wait"].sum()
    assert got["hospitals"] == hospitals["facility_code"].nunique()
    assert got["quarters"] == hospitals["quarter"].nunique()
    over = (cats["attendances"] * (100 - cats["stay_within_4h_pct"].fillna(0)) / 100)[cats["attendances"] > 0].sum()
    assert got["stays over 4 hours, all quarters"] == pytest.approx(over, abs=1e-6)


def test_fit_table_matches_its_own_claim(exported):
    out, _ = exported
    f = powerbi_checks.fit(powerbi_checks.connect(out))
    for key in ("decimal", "whole"):
        assert f[key]["stay_within_tolerance"] == f[key]["hospital_quarters"]
    assert f["decimal"]["hospital_quarters"] + f["whole"]["hospital_quarters"] == 1457


# ---- measures.dax, checked statically ---------------------------------------

@pytest.fixture(scope="module")
def dax(powerbi):
    return (powerbi / "measures.dax").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(dax):
    return re.sub(r"//[^\n]*", "", dax)   # comments out


@pytest.fixture(scope="module")
def defined(code):
    return re.findall(r"MEASURE\s+(\w+)\[([^\]]+)\]", code)


@pytest.fixture(scope="module")
def manifest(powerbi):
    return json.loads((powerbi / "data" / "MANIFEST.json").read_text())["tables"]


def test_every_measure_used_is_defined_once(code, defined):
    names = [m for _, m in defined]
    assert len(names) == len(set(names)), "a measure is defined twice"
    # [Name] not preceded by a table name is a measure, or a column a query named
    used = set(re.findall(r"(?<![\w'\]])\[([^\]]+)\]", code))
    query_columns = set(re.findall(r'"([^"]+)"\s*,', code))
    assert used - set(names) - query_columns == set()


def test_dax_tables_and_columns_exist_in_the_export(code, manifest):
    pairs = re.findall(r"\b([a-z_]+)\[([a-z_0-9]+)\]", code)
    assert pairs
    assert {t for t, _ in pairs} <= set(manifest)
    for table, column in pairs:
        assert column in {c["name"] for c in manifest[table]["columns"]}, f"{table}[{column}]"
    # every exported table is used by the model's DAX
    used = {t for t, _ in pairs} | set(re.findall(r"\(\s*([a-z_]+)\s*\)", code))
    assert set(manifest) <= used


def test_measures_sit_on_exported_tables_and_follow_the_rules(code, defined, manifest):
    assert {t for t, _ in defined} <= set(manifest)
    assert "= BLANK" not in code, "use ISBLANK: in DAX 0 = BLANK() is true"
    assert "AVERAGE" not in code, "rates are ratios of sums, never averages"
    # no measure sums or averages a published percentage of the triage fact
    assert not re.search(r"SUM\s*\(\s*fct_ed_triage_quarter\[\w+_published\]", code)
    names = [m for _, m in defined]
    assert "Not Admitted 4-hour Stay % (implied)" in names
    assert not [m for m in names if "Not Admitted" in m and "implied" not in m]


def test_dax_literals_exist_in_the_data(code, exported):
    out, _ = exported
    con = powerbi_checks.connect(out)

    def values(table, column):
        return {v for (v,) in con.execute(f"select distinct {column} from {table}").fetchall()}
    for trend in re.findall(r'hospital_scorecard\[trend\] = "([^"]+)"', code):
        assert trend in values("hospital_scorecard", "trend")
    for role in re.findall(r'dim_quarter\[comparison_role\] = "([^"]+)"', code):
        assert role in values("dim_quarter", "comparison_role")
    for name in powerbi_checks.TRAP_HOSPITALS:
        assert f'"{name}"' in code and name in values("dim_hospital", "hospital_name")
    assert f"{{ {powerbi_checks.TRAP_QUARTER} }}" in code
    assert '{ "large" }' in code and "large" in values("dim_hospital", "peer_group")


def test_one_check_query_per_checks_section(dax, powerbi):
    evaluates = re.findall(r"// (\d)\. ([^\n]+)\nEVALUATE", dax)
    sections = re.findall(r"^### (\d)\. (.+)$", (powerbi / "CHECKS.md").read_text(encoding="utf-8"), re.M)
    assert evaluates == sections
    assert len(evaluates) == len(re.findall(r"^EVALUATE", dax, re.M)) == 8


def test_check_notes_name_only_defined_measures(exported, defined):
    out, _ = exported
    names = {m for _, m in defined}
    for c in powerbi_checks.checks(powerbi_checks.connect(out)):
        listed = re.match(r"Measures?: ([^.]*?)(?:[.;]|, next to)", c["note"])
        if not listed:
            continue
        for name in listed.group(1).split(", "):
            assert name.strip() in names, f"{c['query']}: {name!r}"


# ---- the guide ---------------------------------------------------------------

@pytest.fixture(scope="module")
def guide(powerbi):
    return (powerbi / "POWERBI_GUIDE.md").read_text(encoding="utf-8")


def test_guide_row_counts_match_the_manifest(guide, manifest):
    loads = re.findall(r"^\| `(\w+)` \| `(\w+)\.parquet` \| ([\d,]+) \|", guide, re.M)
    assert {t for t, _, _ in loads} == set(manifest)
    for query, table, rows in loads:
        assert query == table
        assert int(rows.replace(",", "")) == manifest[table]["rows"], table


def test_guide_relationships_and_sort_columns_exist(guide, manifest):
    columns = {t: {c["name"] for c in info["columns"]} for t, info in manifest.items()}
    refs = re.findall(r"`(\w+)\[(\w+)\]`", guide)
    assert len(refs) > 20
    for table, column in refs:
        assert column in columns[table], f"{table}[{column}]"
    relationships = re.findall(r"^\| `(\w+)\[(\w+)\]` \| `(\w+)\[(\w+)\]` \| (Many to one|One to one) \|", guide, re.M)
    assert len(relationships) == 7
    assert len(re.findall(r"^    \w+ +\|\|--", guide, re.M)) == 7       # the diagram shows the same seven
    for many, key, one, one_key in (r[:4] for r in relationships):
        assert key == one_key


def test_guide_names_only_defined_measures(guide, defined):
    names = {m for _, m in defined}
    pages = guide[guide.index("## 6. Report pages"):guide.index("## 7. Save and share")]
    quoted = set(re.findall(r"`([A-Z4][^`\[\]]*)`", pages))
    assert len(quoted) >= 15
    assert quoted <= names, quoted - names


def test_guide_counts_the_check_queries(guide, dax):
    n = len(re.findall(r"^EVALUATE", dax, re.M))
    assert f"plus {n} check queries" in guide and f"Run the {n} `EVALUATE` queries" in guide


def test_guide_figures_match_the_analysis(guide, snapshot, periods, exported):
    out, _ = exported
    # "Averaging the 4-hour figure across hospitals gives 79.2% for a state whose real figure is 56.1%"
    latest = snapshot[(snapshot["quarter"] == periods["q1"]) & (snapshot["triage"] == "ALL")]
    plain = latest.loc[~latest["is_state_total"], "stay_within_4h_pct"].mean()
    state = latest.loc[latest["is_state_total"], "stay_within_4h_pct"].iloc[0]
    assert guide.count(f"{plain:.1f}% for a state") == 2 and f"{state:.1f}%" in guide
    size = sum(p.stat().st_size for p in out.glob("*.parquet"))
    assert "under 0.5 MB" in guide and size < 0.5 * 1024 * 1024
    assert "first five quarters were published as whole-number percentages" in guide and len(periods["whole"]) == 5
    assert f"{mix_report.B.qname(periods['q0'])} to {mix_report.B.qname(periods['q1'])}" in guide
    assert "Apr-Jun 2023 to Jan-Mar 2024 publish a zero as `-`" in guide
