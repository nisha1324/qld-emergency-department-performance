import json

import pytest

from edperf import source


def fake_portal(rows, fields=("_id", "A", "B")):
    calls = []

    def get(url):
        calls.append(url)
        offset = int(url.split("offset=")[1].split("&")[0])
        limit = int(url.split("limit=")[1].split("&")[0])
        return {"success": True, "result": {
            "fields": [{"id": f} for f in fields], "total": len(rows),
            "records": rows[offset:offset + limit]}}
    return get, calls


def test_fetch_pages_through_every_row():
    rows = [{"_id": i, "A": str(i), "B": None} for i in range(1, 8)]
    get, calls = fake_portal(rows)
    out = source.fetch_resource("abc", page=3, pause=0, get=get)
    assert out["records"] == rows and out["fields"] == ["_id", "A", "B"]
    assert len(calls) == 3 and all("sort=_id" in c and "resource_id=abc" in c for c in calls)


def test_fetch_fails_when_rows_are_short():
    rows = [{"_id": i, "A": "x", "B": "y"} for i in range(1, 6)]
    get, _ = fake_portal(rows)

    def lossy(url):
        body = get(url)
        body["result"]["records"] = body["result"]["records"][:-1]
        return body
    with pytest.raises(RuntimeError, match="portal says 5"):
        source.fetch_resource("abc", page=10, pause=0, get=lossy)


def test_fetch_fails_on_api_error():
    with pytest.raises(RuntimeError):
        source.fetch_resource("abc", get=lambda url: {"success": False})


def test_serialise_is_stable_and_keeps_nulls_apart_from_blanks():
    payload = {"resource_id": "abc", "fields": ["_id", "A", "B"],
               "records": [{"B": None, "A": "", "_id": 1}, {"_id": 2, "A": "-", "B": "é"}]}
    data = source.serialise(payload)
    assert data == source.serialise(json.loads(json.dumps(payload)))
    back = json.loads(data)
    assert back["records"] == [[1, "", None], [2, "-", "é"]]
    assert data.endswith(b"}\n") and data.count(b"\n") == 8


def test_every_quarter_is_pinned(root):
    assert len(source.RESOURCES) == 14
    assert list(source.RESOURCES) == sorted(source.RESOURCES)
    ids = [rid for rid, _ in source.RESOURCES.values()]
    assert len(set(ids)) == 14
    for quarter, (_, pinned) in source.RESOURCES.items():
        assert quarter[5:] in {"03", "06", "09", "12"}
        assert len(pinned) == 64
        raw = root / "data" / "raw" / source.raw_name(quarter)
        assert source.sha256(raw.read_bytes()) == pinned, quarter
