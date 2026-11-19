"""Download the Queensland Health emergency department quarterly data into data/raw/.

One JSON file per quarter (14 quarters, January-March 2023 to April-June 2026),
read from the Queensland Government open data portal's public datastore API.
No key or sign-up is needed. See edperf/source.py for the source and licence.

Every file's SHA-256 is pinned in edperf/source.py. Queensland Health can
revise a quarter after publishing it; a file that differs from the pinned one
stops the download instead of silently changing the analysis. To accept a
revision on purpose, run with --update-pins and review the diff in data/raw/.

    python scripts/download_data.py            # fetch what is missing, verify all
    python scripts/download_data.py --force    # fetch everything again
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edperf import source  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="download again even if the file exists")
    ap.add_argument("--update-pins", action="store_true",
                    help="print the new hashes instead of failing on a mismatch")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    bad = 0
    for quarter, (resource_id, pinned) in source.RESOURCES.items():
        path = RAW / source.raw_name(quarter)
        if path.exists() and not args.force:
            data, how = path.read_bytes(), "on disk"
        else:
            data = source.serialise(source.fetch_resource(resource_id))
            how = "downloaded"
            time.sleep(0.3)
        digest = source.sha256(data)
        if digest == pinned:
            if how == "downloaded":
                path.write_bytes(data)
            print(f"ok        {path.name}  {len(data):>7,} bytes  ({how})")
        elif args.update_pins:
            path.write_bytes(data)
            print(f'new pin   "{quarter}": ("{resource_id}", "{digest}"),')
        else:
            bad += 1
            if how == "downloaded":
                path.with_suffix(".json.part").write_bytes(data)
            print(f"MISMATCH  {path.name}: expected {pinned[:12]}…, got {digest[:12]}… ({how})",
                  file=sys.stderr)
    if bad:
        print(f"{bad} file(s) differ from the pinned version. The source may have been revised; "
              "see the docstring.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
