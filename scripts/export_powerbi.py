"""Part 5: export the star schema for Power BI. Writes powerbi/data/*.parquet and MANIFEST.json.

    python scripts/export_powerbi.py

Reads the committed snapshot and the Part 3 and Part 4 hospital tables in
results/ (run scorecard_report.py and doors_report.py first if they changed).
Power BI Desktop reads Parquet natively, and the files are small and
committed, so the report can be built from a clone with no Python.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from edperf import load, star  # noqa: E402
from scripts import mix_report as R2  # noqa: E402

DATA, RESULTS = ROOT / "data", ROOT / "results"
OUT = ROOT / "powerbi" / "data"


def connect(data: Path = DATA, results: Path = RESULTS):
    """The star schema, built from the committed files."""
    snapshot = data / "ed_quarterly.csv"
    p = R2.periods(load.read_snapshot(snapshot))
    return star.build(snapshot, results / "scorecard_hospitals.csv", results / "doors_hospitals.csv",
                      p["q0"], p["q1"])


def export(out: Path = OUT, data: Path = DATA, results: Path = RESULTS) -> dict:
    con = connect(data, results)
    q0, q1 = con.execute("select q0, q1 from src_comparison").fetchone()
    manifest = {
        "source": "data/ed_quarterly.csv, results/scorecard_hospitals.csv, results/doors_hospitals.csv",
        "built_by": "sql/star_schema.sql (DuckDB)",
        "comparison": {"start": q0, "latest": q1},
        "tables": star.export(con, out),
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    manifest = export(args.out)
    for table, info in manifest["tables"].items():
        size = (args.out / f"{table}.parquet").stat().st_size / 1024
        print(f"wrote {table}.parquet: {info['rows']:,} rows, {len(info['columns'])} columns, {size:,.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
