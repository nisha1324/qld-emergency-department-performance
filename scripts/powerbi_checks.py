"""Part 5: check values for the Power BI model. Writes powerbi/CHECKS.md.

    python scripts/powerbi_checks.py

Power BI Desktop is Windows-only, so the DAX in powerbi/measures.dax is not
run here. Instead each check query in that file has a twin below: DuckDB SQL
over the same Parquet files, written with the same logic as the DAX (ratio of
sums, count over its base). CHECKS.md lists what the SQL returns. When the
report is built, the DAX queries should print the same numbers.

tests/test_powerbi.py ties these values back to the Python analysis of
Parts 1 to 4, so a match in Power BI means the report agrees with the README.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from edperf import star  # noqa: E402

DATA = ROOT / "powerbi" / "data"
OUT = ROOT / "powerbi" / "CHECKS.md"

TRAP_QUARTER = 202312
TRAP_HOSPITALS = ("Capricorn Coast", "Cunnamulla", "Dirranbandi")

# the measures, as SQL over fct_ed_triage_quarter (alias f)
RATE_4H = "sum(f.stays_within_4h) / sum(f.stays_4h_base)"
ADMITTED = "sum(f.admitted) / sum(f.admitted_base)"
ADMITTED_4H = "sum(f.stream_admitted_within_4h) / nullif(sum(f.stream_admitted), 0)"
NOT_ADMITTED_4H = "sum(f.stream_not_admitted_within_4h) / nullif(sum(f.stream_not_admitted), 0)"
SEEN = "sum(f.seen_on_time) / sum(f.seen_on_time_base)"
DNW = "sum(f.did_not_wait) / sum(f.attendances)"


def connect(data: Path = DATA) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with one view per exported Parquet file."""
    con = duckdb.connect()
    con.execute("set threads = 1")
    for table, _ in star.TABLES:
        path = str(data / f"{table}.parquet").replace("'", "''")
        con.execute(f"create view {table} as select * from read_parquet('{path}')")
    return con


def _rows(con, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def checks(con) -> list[dict]:
    """One entry per check query: title, how to read it, headers, raw rows and
    a format per column ('text', 'int', 'pct', 'pts', 'num')."""
    out = []

    out.append({
        "query": "1. Queensland by quarter",
        "note": "Measures: Hospitals Reporting, Attendances, 4-hour Stay %, Queensland 4-hour Stay % (published), "
                "Admitted %, Did Not Wait %. As a visual: a table by `quarter_label` (sorted by `quarter_key`). "
                "The model adds the hospitals up from rounded category rates, so its 4-hour figure is close to the "
                "published one, not identical: within 0.1 points where the source has one decimal place and "
                "within 0.5 in the five whole-number quarters.",
        "headers": ["quarter_label", "hospitals", "attendances", "4-hour stays", "published", "admitted", "did not wait"],
        "formats": ["text", "int", "int", "pct", "pct1", "pct", "pct"],
        "rows": _rows(con, f"""
            select q.quarter_label, count(distinct f.hospital_key), sum(f.attendances), {RATE_4H},
                   max(s.stay_within_4h_pct) / 100, {ADMITTED}, {DNW}
            from fct_ed_triage_quarter f
            join dim_quarter q using (quarter_key)
            join state_published_quarter s using (quarter_key)
            group by q.quarter_key, q.quarter_label order by q.quarter_key"""),
    })

    out.append({
        "query": "2. Peer groups at the two comparison quarters",
        "note": "Measures: Hospitals Reporting, Attendances, 4-hour Stay %, Admitted %, Admitted 4-hour Stay %, "
                "Not Admitted 4-hour Stay % (implied). As a visual: a matrix with `peer_group_label` on rows and "
                "`quarter_label` on columns, filtered to `comparison_role` = start or latest.",
        "headers": ["peer_group_label", "quarter_label", "hospitals", "attendances", "4-hour stays", "admitted",
                    "admitted: 4-hour stays", "not admitted: 4-hour stays (implied)"],
        "formats": ["text", "text", "int", "int", "pct", "pct", "pct", "pct"],
        "rows": _rows(con, f"""
            select h.peer_group_label, q.quarter_label, count(distinct f.hospital_key), sum(f.attendances),
                   {RATE_4H}, {ADMITTED}, {ADMITTED_4H}, {NOT_ADMITTED_4H}
            from fct_ed_triage_quarter f
            join dim_hospital h using (hospital_key)
            join dim_quarter q using (quarter_key)
            where q.comparison_role in ('start', 'latest')
            group by h.peer_group_sort, h.peer_group_label, q.quarter_key, q.quarter_label
            order by h.peer_group_sort, q.quarter_key"""),
    })

    out.append({
        "query": "3. Triage categories, latest quarter",
        "note": "Measures: Attendances, Triage Share %, 4-hour Stay %, Admitted %, Seen On Time % (rebuilt). "
                "As a visual: a table by `triage_label`, filtered to `comparison_role` = latest.",
        "headers": ["triage_label", "attendances", "share", "4-hour stays", "admitted", "seen on time (rebuilt)"],
        "formats": ["text", "int", "pct", "pct", "pct", "pct"],
        "rows": _rows(con, f"""
            select t.triage_label, sum(f.attendances),
                   sum(f.attendances) / sum(sum(f.attendances)) over (), {RATE_4H}, {ADMITTED}, {SEEN}
            from fct_ed_triage_quarter f
            join dim_triage t using (triage_key)
            join dim_quarter q using (quarter_key)
            where q.comparison_role = 'latest'
            group by t.triage_key, t.triage_label order by t.triage_key"""),
    })

    out.append({
        "query": "4. Change on the same quarter a year earlier",
        "note": "Measures: 4-hour Stay %, 4-hour Stay % Year Earlier, 4-hour Stay Change On Year (points), "
                "Attendances Change On Year %. All hospitals. The first four quarters have no year-earlier "
                "quarter, so they are blank and the query leaves them out.",
        "headers": ["quarter_label", "4-hour stays", "year earlier", "change (points)", "attendances change"],
        "formats": ["text", "pct", "pct", "pts", "spct"],
        "rows": _rows(con, f"""
            with by_quarter as (
                select q.quarter_index, q.quarter_key, q.quarter_label,
                       {RATE_4H} as rate, sum(f.attendances) as attendances
                from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
                group by q.quarter_index, q.quarter_key, q.quarter_label
            )
            select a.quarter_label, a.rate, b.rate, (a.rate - b.rate) * 100,
                   (a.attendances - b.attendances) / b.attendances
            from by_quarter a join by_quarter b on b.quarter_index = a.quarter_index - 4
            order by a.quarter_key"""),
    })

    out.append({
        "query": "5. Scorecard counts by peer group",
        "note": "Measures: Hospitals Scored, Hospitals Slipping, Hospitals No Clear Change, Hospitals Improving, "
                "Hospitals Below Peers And Slipping, Hospitals With Wait Step. As a visual: a table by "
                "`peer_group_label`. One medium hospital is new in the latest quarter and has no trend, "
                "so the three trend columns add up to one less than `hospitals` there.",
        "headers": ["peer_group_label", "hospitals", "slipping", "no clear change", "improving",
                    "below peers and slipping", "wait step"],
        "formats": ["text", "int", "int", "int", "int", "int", "int"],
        "rows": _rows(con, """
            select h.peer_group_label, count(*),
                   count(*) filter (where s.trend = 'slipping'),
                   count(*) filter (where s.trend = 'no clear change'),
                   count(*) filter (where s.trend = 'improving'),
                   count(*) filter (where s.below_peers_and_slipping),
                   count(*) filter (where s.wait_step)
            from hospital_scorecard s join dim_hospital h using (hospital_key)
            group by h.peer_group_sort, h.peer_group_label order by h.peer_group_sort"""),
    })

    out.append({
        "query": "6. Large hospitals below peers and slipping",
        "note": "Measures: 4-hour Stay % Start, 4-hour Stay % Latest, 4-hour Stay Change Start To Latest (points); "
                "columns `within_category_effect` and `slipping_pattern` of `hospital_scorecard`. The change is "
                "recalculated by the model from the fact table; the within-category effect comes from Part 3.",
        "headers": ["hospital_name", "4-hour stays, start", "4-hour stays, latest", "change (points)",
                    "within category (points)", "slipping in"],
        "formats": ["text", "pct", "pct", "pts", "pts", "text"],
        "rows": _rows(con, f"""
            with rates as (
                select f.hospital_key,
                       {RATE_4H.replace("sum(f.stays_within_4h)", "sum(f.stays_within_4h) filter (where q.comparison_role = 'start')")
                               .replace("sum(f.stays_4h_base)", "sum(f.stays_4h_base) filter (where q.comparison_role = 'start')")} as r0,
                       {RATE_4H.replace("sum(f.stays_within_4h)", "sum(f.stays_within_4h) filter (where q.comparison_role = 'latest')")
                               .replace("sum(f.stays_4h_base)", "sum(f.stays_4h_base) filter (where q.comparison_role = 'latest')")} as r1
                from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
                group by f.hospital_key
            )
            select h.hospital_name, r.r0, r.r1, (r.r1 - r.r0) * 100, s.within_category_effect, s.slipping_pattern
            from hospital_scorecard s
            join dim_hospital h using (hospital_key)
            join rates r using (hospital_key)
            where h.peer_group = 'large' and s.below_peers_and_slipping
            order by s.within_category_effect"""),
    })

    names = ", ".join(f"'{n}'" for n in TRAP_HOSPITALS)
    out.append({
        "query": "7. A blank that means zero (Oct-Dec 2023)",
        "note": "Measure: Admitted %, next to the same sum divided only by rows whose admitted share was not "
                "blank, and the published all-categories figure (a whole number in this quarter). Four quarters "
                "publish a zero as `-`. The model reads those blanks as 0%; dropping the rows instead would "
                "overstate the admitted share.",
        "headers": ["hospital_name", "attendances", "admitted", "admitted if blank rows are dropped", "published"],
        "formats": ["text", "int", "pct", "pct", "pct0"],
        "rows": _rows(con, f"""
            select h.hospital_name, sum(f.attendances), {ADMITTED},
                   sum(f.admitted) / sum(f.attendances) filter (where f.admitted_pct_published is not null),
                   max(p.admitted_pct) / 100
            from fct_ed_triage_quarter f
            join dim_hospital h using (hospital_key)
            join fct_hospital_quarter_published p using (hospital_key, quarter_key)
            where f.quarter_key = {TRAP_QUARTER} and h.hospital_name in ({names})
            group by h.hospital_name order by h.hospital_name"""),
    })

    totals = _rows(con, """
        select (select count(*) from fct_ed_triage_quarter),
               (select sum(attendances) from fct_ed_triage_quarter),
               (select sum(stays_4h_base) - sum(stays_within_4h) from fct_ed_triage_quarter),
               (select sum(did_not_wait) from fct_ed_triage_quarter),
               (select count(*) from dim_hospital),
               (select count(*) from dim_quarter)""")[0]
    labels = ["fact rows", "attendances, all quarters", "stays over 4 hours, all quarters",
              "did not wait, all quarters", "hospitals", "quarters"]
    out.append({
        "query": "8. Totals",
        "note": "A single row in DAX; shown here as one line per value. Stays over 4 hours is a sum of "
                "attendances x published rates, so it is not a whole number.",
        "headers": ["column", "value"],
        "formats": ["text", "num"],
        "rows": list(zip(labels, totals)),
    })
    return out


def fmt(value, how: str) -> str:
    if value is None:
        return "(blank)"
    if how == "text":
        return str(value)
    if how == "int":
        return f"{int(value):,}"
    if how == "pct":
        return f"{100 * value:.2f}%"
    if how == "pct1":
        return f"{100 * value:.1f}%"
    if how == "pct0":
        return f"{100 * value:.0f}%"
    if how == "spct":
        return f"{100 * value:+.2f}%".replace("-", "−")
    if how == "pts":
        return f"{value:+.2f}".replace("-", "−")
    if how == "num":
        return f"{value:,.2f}" if isinstance(value, float) and value != int(value) else f"{int(value):,}"
    raise ValueError(how)


def fit(con) -> dict:
    """How closely the model's hospital figures rebuild the published
    all-categories rows, split by the precision the quarter was published to."""
    out = {}
    for whole, n, stay_max, stay_within, admitted_max in _rows(con, """
        with model as (
            select hospital_key, quarter_key,
                   100 * sum(stays_within_4h) / sum(stays_4h_base) as stay,
                   100 * sum(admitted) / sum(admitted_base)        as admitted
            from fct_ed_triage_quarter group by hospital_key, quarter_key
        )
        select q.whole_number_rates, count(*),
               max(abs(m.stay - p.stay_within_4h_pct)),
               count(*) filter (where abs(m.stay - p.stay_within_4h_pct) <= if(q.whole_number_rates, 1.0, 0.1)),
               max(abs(m.admitted - coalesce(p.admitted_pct, 0)))
        from model m
        join fct_hospital_quarter_published p using (hospital_key, quarter_key)
        join dim_quarter q using (quarter_key)
        group by q.whole_number_rates order by q.whole_number_rates"""):
        out["whole" if whole else "decimal"] = {
            "hospital_quarters": n, "stay_max_gap": stay_max, "stay_within_tolerance": stay_within,
            "admitted_max_gap": admitted_max}
    return out


def blank_evidence(con) -> dict:
    """Hospital-quarters where a category with attendances has a blank admitted
    share and the all-categories share is published: how many does each
    reading of the blank rebuild to within 1 point (the published figure is a
    whole number in these quarters)?"""
    n, zero, dropped = _rows(con, """
        with g as (
            select hospital_key, quarter_key,
                   sum(attendances)                                                      as att,
                   sum(attendances) filter (where admitted_pct_published is not null)    as att_known,
                   sum(attendances * coalesce(admitted_pct_published, 0))                as admitted_x100,
                   count(*) filter (where admitted_pct_published is null)                as blanks
            from fct_ed_triage_quarter where attendances > 0
            group by hospital_key, quarter_key
        )
        select count(*),
               count(*) filter (where abs(admitted_x100 / att - p.admitted_pct) <= 1.0),
               count(*) filter (where att_known > 0 and abs(admitted_x100 / att_known - p.admitted_pct) <= 1.0)
        from g join fct_hospital_quarter_published p using (hospital_key, quarter_key)
        where g.blanks > 0 and p.admitted_pct is not null""")[0]
    quarters = [q for (q,) in _rows(con, """
        select distinct q.quarter_label from fct_ed_triage_quarter f join dim_quarter q using (quarter_key)
        where f.attendances > 0 and f.admitted_pct_published is null""")]
    return {"hospital_quarters": n, "zero_fits": zero, "dropped_fits": dropped, "quarters": len(quarters)}


def build(data: Path = DATA) -> str:
    con = connect(data)
    L = ["# Power BI check values", "",
         "*Generated by `scripts/powerbi_checks.py` from the Parquet files in `powerbi/data/`. "
         "Do not edit by hand.*", "",
         "Once the measures are in the model, run the `EVALUATE` queries at the end of "
         "[`measures.dax`](measures.dax) in DAX query view and compare. The DAX results also show their sort "
         "columns (`quarter_key`, `peer_group_sort`, `triage_key`). Rates are shown to two decimal places; "
         "Power BI's numbers should match to the last digit shown. Each value here is computed from the "
         "Parquet files with the same logic as the DAX, and tests tie the values to the Python analysis "
         "behind the README.", ""]
    f = fit(con)
    d, w = f["decimal"], f["whole"]
    L += ["## Does the model rebuild the published figures?", "",
          "The fact table turns published percentages back into head counts. Adding a hospital's five "
          "triage categories up again should give its published all-categories figure, to rounding.", "",
          "| Quarters published to | Hospital-quarters | 4-hour stays: largest gap (points) | Within tolerance | "
          "Admitted share: largest gap (points) |",
          "| --- | ---: | ---: | ---: | ---: |",
          f"| one decimal place | {d['hospital_quarters']:,} | {d['stay_max_gap']:.2f} | "
          f"{d['stay_within_tolerance']:,} (within 0.1) | {d['admitted_max_gap']:.2f} |",
          f"| whole numbers | {w['hospital_quarters']:,} | {w['stay_max_gap']:.2f} | "
          f"{w['stay_within_tolerance']:,} (within 1.0) | {w['admitted_max_gap']:.2f} |", ""]
    e = blank_evidence(con)
    L += ["## Is a blank a zero?", "",
          f"In {e['quarters']} quarters some triage categories with attendances have a blank admitted share. "
          f"In {e['hospital_quarters']} hospital-quarters that happens while the all-categories share is published, "
          "so the two readings of the blank can be compared with it (a whole number, so a fit is within 1 point).", "",
          "| Reading of the blank | Hospital-quarters that rebuild the published share |",
          "| --- | ---: |",
          f"| zero (used by the model) | {e['zero_fits']} of {e['hospital_quarters']} |",
          f"| no data: drop the row | {e['dropped_fits']} of {e['hospital_quarters']} |", ""]
    for c in checks(con):
        L += [f"### {c['query']}", "", c["note"], "",
              "| " + " | ".join(c["headers"]) + " |", "|" + " --- |" * len(c["headers"])]
        for row in c["rows"]:
            L.append("| " + " | ".join(fmt(v, how) for v, how in zip(row, c["formats"])) + " |")
        L.append("")
    return "\n".join(L)


def main() -> int:
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
