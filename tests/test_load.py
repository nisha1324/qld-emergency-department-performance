import json

import pandas as pd
import pytest

from edperf import load, source
from scripts import build_snapshot

FIELDS = ["_id"] + [c for c in load.COLUMNS if c != "Triage_Category"]


def raw_frame(rows, fields=FIELDS):
    return pd.DataFrame(rows, columns=fields, dtype=object)


def row(i, code="15", name="Ipswich Hospital", label="Jun-26", tri="1", att="10", change="5.5",
        seen="90", wait="3", dnw_pct="0", adm="20", adm4="50", stay="80", lat="1", lat_pct="10", dnw="0"):
    return [i, code, name, label, tri, att, change, seen, wait, dnw_pct, adm, adm4, stay, lat, lat_pct, dnw]


def test_tidy_quarter_cleans_names_types_and_missing_values():
    raw = raw_frame([
        row(1, tri="1", att="0", change="-", seen=None, wait="-", dnw_pct="", adm="NULL", adm4="-", stay="-",
            lat="0", lat_pct="-"),
        row(2, tri="All", att="1234", name=" Ipswich Hospital "),
        row(3, code="99999", name="QUEENSLAND", tri="ALL", att="5000"),
    ])
    out = load.tidy_quarter(raw, "2026-06")
    assert list(out.columns) == load.TIDY
    assert out["triage"].tolist() == ["1", "ALL", "ALL"]
    assert out["facility_name"].tolist()[1] == "Ipswich Hospital"
    assert out["is_state_total"].tolist() == [False, False, True]
    assert out["attendances"].tolist() == [0, 1234, 5000] and out["attendances"].dtype == int
    first = out.iloc[0]
    for col in load.RATES:
        assert pd.isna(first[col]), col
    assert out.iloc[1]["attendances_change_pct"] == 5.5 and out.iloc[1]["seen_on_time_pct"] == 90


def test_tidy_quarter_accepts_both_triage_headers_and_drops_the_traffic_light():
    fields = [f.replace("Triage Category", "Triage_Category") for f in FIELDS] + ["Median Wait Traffic Light"]
    out = load.tidy_quarter(raw_frame([row(1) + ["2"]], fields), "2026-06")
    assert "Median Wait Traffic Light" not in out.columns and out["triage"].tolist() == ["1"]


@pytest.mark.parametrize("change, match", [
    (dict(label="Mar-26"), "file says"),
    (dict(tri="6"), "triage"),
    (dict(att="12.5"), "whole"),
    (dict(att="-"), "whole"),
])
def test_tidy_quarter_rejects_bad_rows(change, match):
    with pytest.raises(ValueError, match=match):
        load.tidy_quarter(raw_frame([row(1, **change)]), "2026-06")


def test_tidy_quarter_rejects_unknown_columns_duplicates_and_text_in_numbers():
    with pytest.raises(ValueError, match="unexpected column"):
        load.tidy_quarter(raw_frame([row(1) + ["x"]], FIELDS + ["New column"]), "2026-06")
    with pytest.raises(ValueError, match="missing column"):
        load.tidy_quarter(raw_frame([row(1)[:-1]], FIELDS[:-1]), "2026-06")
    with pytest.raises(ValueError, match="duplicate"):
        load.tidy_quarter(raw_frame([row(1), row(2)]), "2026-06")
    with pytest.raises(ValueError):
        load.tidy_quarter(raw_frame([row(1, seen="n/a")]), "2026-06")


def test_combine_uses_the_latest_name_for_each_code():
    q1 = load.tidy_quarter(raw_frame([row(1, label="Mar-26", name="Ipswich Hospital"),
                                      row(2, label="Mar-26", code="16", name="Redcliffe Hospital")]), "2026-03")
    q2 = load.tidy_quarter(raw_frame([row(1, name="Ipswich")]), "2026-06")
    out = load.combine({"2026-06": q2, "2026-03": q1})
    assert out["quarter"].tolist() == ["2026-03", "2026-03", "2026-06"]
    assert out["facility_name"].tolist() == ["Ipswich", "Redcliffe Hospital", "Ipswich"]


def test_snapshot_invariants(snapshot):
    df = snapshot
    assert list(df.columns) == load.TIDY
    assert len(df) == 8826 and df["quarter"].nunique() == 14
    assert not df.duplicated(["quarter", "facility_code", "triage"]).any()
    assert set(df["triage"]) == set(load.TRIAGE)
    assert df.groupby(["quarter", "facility_code"]).size().eq(6).all()
    assert df.groupby("facility_code")["facility_name"].nunique().eq(1).all()
    assert df.groupby("facility_name")["facility_code"].nunique().eq(1).all()
    assert df.loc[df["is_state_total"], "facility_name"].unique().tolist() == ["Queensland"]
    assert (df[load.COUNTS] >= 0).all().all()
    pct = [c for c in load.RATES if c not in ("attendances_change_pct", "median_wait_min")]
    assert df[pct].min().min() >= 0 and df[pct].max().max() <= 100
    assert (df["did_not_wait"] + df["left_after_treatment"] <= df["attendances"]).all()


def test_snapshot_rebuilds_byte_for_byte_from_raw(root):
    raw = root / "data" / "raw"
    for name, frame in {"ed_quarterly.csv": load.build(raw), "facility_names.csv": load.name_variants(raw)}.items():
        assert build_snapshot.csv_bytes(frame) == (root / "data" / name).read_bytes(), name
    snap = json.loads((root / "data" / "SNAPSHOT.json").read_text())
    for name, meta in snap["outputs"].items():
        assert source.sha256((root / "data" / name).read_bytes()) == meta["sha256"]
    assert snap["inputs"] == {source.raw_name(q): h for q, (_, h) in source.RESOURCES.items()}


def test_snapshot_keeps_every_raw_count(root):
    """The tidy table must carry the raw attendances unchanged, row for row."""
    total = 0
    for quarter in source.RESOURCES:
        raw = load.read_raw(root / "data" / "raw" / source.raw_name(quarter))
        total += raw["Number of Attendances"].astype(int).sum()
    assert total == load.read_snapshot(root / "data" / "ed_quarterly.csv")["attendances"].sum()
