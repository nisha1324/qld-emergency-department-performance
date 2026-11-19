"""Build the tidy snapshot in data/ from the raw quarterly files in data/raw/.

    python scripts/build_snapshot.py

Writes
- data/ed_quarterly.csv        one row per facility x quarter x triage category
- data/facility_names.csv      every spelling each facility code has had
- data/SNAPSHOT.json           hashes of the inputs and outputs

The outputs are plain text and rebuild byte for byte from the same raw files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from edperf import load, source  # noqa: E402

DATA = ROOT / "data"
RAW = DATA / "raw"


def csv_bytes(df) -> bytes:
    return df.to_csv(index=False, lineterminator="\n", float_format="%.10g").encode("utf-8")


def main() -> int:
    inputs = {}
    for quarter, (_, pinned) in source.RESOURCES.items():
        path = RAW / source.raw_name(quarter)
        digest = source.sha256(path.read_bytes())
        if digest != pinned:
            print(f"{path.name} differs from the pinned version; run scripts/download_data.py",
                  file=sys.stderr)
            return 1
        inputs[path.name] = digest

    tidy = load.build(RAW)
    names = load.name_variants(RAW)
    outputs = {}
    for name, frame in {"ed_quarterly.csv": tidy, "facility_names.csv": names}.items():
        data = csv_bytes(frame)
        (DATA / name).write_bytes(data)
        outputs[name] = {"sha256": source.sha256(data), "rows": len(frame)}
        print(f"{name}: {len(frame):,} rows, {len(data):,} bytes")

    snapshot = {
        "source": source.DATASET_URL,
        "licence": "CC BY 4.0, Queensland Health",
        "quarters": [min(source.RESOURCES), max(source.RESOURCES)],
        "inputs": inputs,
        "outputs": outputs,
    }
    (DATA / "SNAPSHOT.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
