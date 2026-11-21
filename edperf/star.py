"""Star schema for Power BI (Part 5).

The tables are built in DuckDB by sql/star_schema.sql from three committed
files: the tidy snapshot and the hospital-level results of Parts 3 and 4.
This module registers those files as views, runs the SQL, checks that the
star still adds up to the snapshot, and writes one Parquet file per table.

Why a star and not the tidy table: the source publishes percentages, and a
percentage cannot be summed or averaged across hospitals. The fact table
carries head counts instead (attendances x published rate), so every rate in
a report is a ratio of sums and stays right under any filter.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

SQL = Path(__file__).resolve().parents[1] / "sql" / "star_schema.sql"

# (table, sort key). Rows are written in key order so a rebuild of the same
# inputs writes the same file.
TABLES = [
    ("fct_ed_triage_quarter", "ed_row_id"),
    ("fct_hospital_quarter_published", "hospital_quarter_id"),
    ("dim_hospital", "hospital_key"),
    ("dim_quarter", "quarter_key"),
    ("dim_triage", "triage_key"),
    ("hospital_scorecard", "hospital_key"),
    ("state_published_quarter", "quarter_key"),
]

# Read the snapshot with fixed types, so nothing depends on type sniffing.
SNAPSHOT_COLUMNS = {
    "quarter": "VARCHAR", "facility_code": "INTEGER", "facility_name": "VARCHAR",
    "is_state_total": "BOOLEAN", "triage": "VARCHAR", "attendances": "INTEGER",
    "did_not_wait": "INTEGER", "left_after_treatment": "INTEGER",
    "attendances_change_pct": "DOUBLE", "seen_on_time_pct": "DOUBLE", "median_wait_min": "DOUBLE",
    "did_not_wait_pct": "DOUBLE", "left_after_treatment_pct": "DOUBLE", "admitted_pct": "DOUBLE",
    "admitted_within_4h_pct": "DOUBLE", "stay_within_4h_pct": "DOUBLE",
}

NUMERIC = ("DOUBLE", "INTEGER", "BIGINT")


class StarError(ValueError):
    """The star schema does not add up to its inputs."""


def _csv(path: Path, columns: dict[str, str] | None = None) -> str:
    p = str(path).replace("'", "''")
    if columns is None:
        return f"read_csv('{p}', header = true, sample_size = -1)"
    spec = ", ".join(f"'{k}': '{v}'" for k, v in columns.items())
    return f"read_csv('{p}', header = true, columns = {{{spec}}})"


def build(snapshot: Path, scorecard: Path, doors: Path, q0: str, q1: str) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB database holding the star schema."""
    con = duckdb.connect()
    con.execute("set threads = 1")
    con.execute(f"create view src_ed_quarterly as select * from {_csv(snapshot, SNAPSHOT_COLUMNS)}")
    con.execute(f"create view src_scorecard as select * from {_csv(scorecard)}")
    con.execute(f"create view src_doors as select * from {_csv(doors)}")
    # q0 and q1 come from scripts.mix_report.periods, never from user input
    con.execute("create table src_comparison as select ?::varchar as q0, ?::varchar as q1", [q0, q1])
    con.execute(SQL.read_text(encoding="utf-8"))
    check(con)
    return con


def _one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def check(con) -> None:
    """Stop if the star lost, duplicated or changed anything from the snapshot."""
    problems = []

    def expect(what: str, got, want) -> None:
        if got != want:
            problems.append(f"{what}: {got!r}, expected {want!r}")

    src_rows = _one(con, "select count(*) from src_ed_quarterly where triage <> 'ALL' and not is_state_total")
    expect("fact rows", _one(con, "select count(*) from fct_ed_triage_quarter"), src_rows)
    for table, key in TABLES:
        expect(f"{table}: duplicate {key}",
               _one(con, f"select count(*) - count(distinct {key}) from {table}"), 0)
    for column in ("attendances", "did_not_wait", "left_after_treatment"):
        expect(f"sum of {column}",
               _one(con, f"select sum({column}) from fct_ed_triage_quarter"),
               _one(con, f"select sum({column}) from src_ed_quarterly where triage = 'ALL' and not is_state_total"))
    # every fact row finds its three dimension rows
    for dim, key in (("dim_hospital", "hospital_key"), ("dim_quarter", "quarter_key"), ("dim_triage", "triage_key")):
        for fact in ("fct_ed_triage_quarter", "fct_hospital_quarter_published"):
            if dim == "dim_triage" and fact != "fct_ed_triage_quarter":
                continue
            expect(f"{fact} rows with no {dim}",
                   _one(con, f"select count(*) from {fact} f anti join {dim} d using ({key})"), 0)
    expect("scorecard rows with no hospital",
           _one(con, "select count(*) from hospital_scorecard s anti join dim_hospital d using (hospital_key)"), 0)
    expect("hospitals with no scorecard row",
           _one(con, "select count(*) from dim_hospital d anti join hospital_scorecard s using (hospital_key)"), 0)
    # the two streams add back to attendances and to stays within 4 hours
    gap = _one(con, """
        select max(greatest(
            abs(stream_admitted + stream_not_admitted - attendances),
            abs(stream_admitted_within_4h + stream_not_admitted_within_4h - stays_within_4h)))
        from fct_ed_triage_quarter where stream_admitted is not null""")
    if gap is None or gap > 1e-9:
        problems.append(f"streams do not add back to the category (largest gap {gap!r})")
    # a count never exceeds its base; a count and its base are missing together
    for count, base in (("seen_on_time", "seen_on_time_base"), ("stays_within_4h", "stays_4h_base"),
                        ("admitted", "admitted_base"), ("stream_admitted_within_4h", "stream_admitted")):
        expect(f"{count} above {base}",
               _one(con, f"select count(*) from fct_ed_triage_quarter where {count} > {base} + 1e-9"), 0)
        expect(f"{count} and {base} not missing together",
               _one(con, f"select count(*) from fct_ed_triage_quarter where ({count} is null) <> ({base} is null)"), 0)
    expect("comparison quarters in dim_quarter",
           _one(con, "select count(*) from dim_quarter where comparison_role is not null"), 2)
    if problems:
        raise StarError("star schema check failed:\n  " + "\n  ".join(problems))


def profile(con, relation: str) -> dict:
    """Row count, schema, null counts and numeric totals of a table or file."""
    columns = con.execute(f"describe select * from {relation}").fetchall()
    exprs = ["count(*)"]
    for name, dtype, *_ in columns:
        exprs.append(f'count(*) - count("{name}")')
        if dtype in NUMERIC:
            exprs.append(f'sum("{name}")')
    values = list(con.execute(f"select {', '.join(exprs)} from {relation}").fetchone())
    out = {"rows": values.pop(0), "columns": []}
    for name, dtype, *_ in columns:
        col = {"name": name, "type": dtype, "nulls": values.pop(0)}
        if dtype in NUMERIC:
            total = values.pop(0)
            if total is None:
                col["sum"] = None
            else:
                # rounded so float summation order can't change the manifest
                col["sum"] = round(float(total), 4) if dtype == "DOUBLE" else int(total)
        out["columns"].append(col)
    return out


def export(con, out: Path) -> dict:
    """Write one Parquet file per table, read each back and compare it with
    the table it came from. Returns the manifest."""
    out.mkdir(parents=True, exist_ok=True)
    tables = {}
    for table, key in TABLES:
        path = out / f"{table}.parquet"
        target = str(path).replace("'", "''")
        con.execute(f"copy (select * from {table} order by {key}) to '{target}' (format parquet, compression zstd)")
        expected = profile(con, table)
        got = profile(duckdb.connect(), f"read_parquet('{target}')")
        if got != expected:
            raise StarError(f"{path.name} doesn't match {table}:\n{expected}\n{got}")
        tables[table] = expected
    return tables
