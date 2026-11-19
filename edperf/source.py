"""Where the data comes from, and how one quarter is fetched.

Source: Queensland Health, "Emergency departments - quarterly data",
https://www.data.qld.gov.au/dataset/emergency-departments-quarterly-data
Licence: Creative Commons Attribution 4.0 (stated on the dataset page).

Each quarter is a separate resource on the Queensland Government open data
portal. The 14 quarters from January-March 2023 onwards are loaded into the
portal's datastore, so they can be read through its public API
(`datastore_search`, no key or sign-up). The nine earlier quarters
(October-December 2020 to October-December 2022) exist only as XLS/XLSX/CSV
files and are not used here.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request

DATASET_URL = "https://www.data.qld.gov.au/dataset/emergency-departments-quarterly-data"
API = "https://www.data.qld.gov.au/api/3/action/datastore_search"
USER_AGENT = "qld-emergency-department-performance (python-urllib)"

# quarter (its last month, YYYY-MM) -> (datastore resource id, SHA-256 of the saved file)
RESOURCES: dict[str, tuple[str, str]] = {
    "2023-03": (
        "3dbe0fc7-6243-41c5-9fa1-9bbfbac125ef",
        "7c43aec4e4c5cf16704b2f4a062bb339fc011e4d868de658e5553712692e4036",
    ),
    "2023-06": (
        "bbdbdee1-5ced-4f91-abec-52c33b8928bb",
        "c443194856f93284f34b335bf7d78fed746322bbd7c26d31d0e2eef0e833302e",
    ),
    "2023-09": (
        "400c41fe-9112-4023-aec3-c906393abd14",
        "56d0d06e6c64ca20c8888dc9be64a2e9f5abff97a7deb9e641cc9b08a6ee221e",
    ),
    "2023-12": (
        "fff38b0c-b6c3-4b73-8c4c-c43dd0d9797d",
        "c74ea99995dcbac0e6ed0fd1ce16ab484f56f49a17370f71cea9200cddcc6641",
    ),
    "2024-03": (
        "ce4b7a8c-11bd-489b-bf55-fc0872dc540f",
        "23f5a3fa6a5ffac3ba3100c79d7925902fd4990b6a71e828005fa7be10bb84c0",
    ),
    "2024-06": (
        "f1229647-ac37-43d5-91ba-092a6f59152c",
        "0b2bd6a5976a62474ba456c2a8a972d1d902a4a11b9c2d39ada42fa96bd70ff5",
    ),
    "2024-09": (
        "adfe4a98-a479-4c1e-a34b-1050a6386ff4",
        "71d70dea19ec31a165ca878e7fc4b54304e042c173b96af4f13b444e5f997ec0",
    ),
    "2024-12": (
        "81455b62-578a-441a-a7dd-830dc2634cba",
        "d624f37b1f8390cb9da97c70792199edf9a86ce077a468d658a0e4af7738d933",
    ),
    "2025-03": (
        "5ff94eab-e75d-4166-b80a-98b73262f971",
        "4d0d927a27aa9ddcdd1153c825492fd49e60348dd6c77a6441ec021131b94f4c",
    ),
    "2025-06": (
        "e634fc0f-c77d-45bc-8196-5a983ddcffdd",
        "51226e0b8af6725c6ecffcb65dc7ef99955c55526a6904be71f2310419c1914d",
    ),
    "2025-09": (
        "a9634f60-dd88-4d40-8e80-efaf9b6135c5",
        "0a0fa2615d0e640ee565c43cad6a9f564dc74deb03636e5e8f936a171d65c6ca",
    ),
    "2025-12": (
        "2fb4b0d7-56e3-498e-8219-5334e0a898f3",
        "575b0c37ac3638de349cba22996ff4bccc7f426673102c88829da49cb8f5507b",
    ),
    "2026-03": (
        "a0a98a66-145d-49ce-a9cc-2b69cceee364",
        "9a696a68e362074e7151dec88dce071e48e884c52f9a4af8ef97b058ffd7b4da",
    ),
    "2026-06": (
        "ccffa9b4-0458-4642-abc0-6982c614799b",
        "1b77c654edd814615e2293b911c94fcfc2ca7925c876e490d5beb0f510b9fcda",
    ),
}


def raw_name(quarter: str) -> str:
    return f"ed_{quarter}.json"


def _get(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_resource(resource_id: str, page: int = 1000, pause: float = 0.3, get=_get) -> dict:
    """All rows of one datastore resource, in the portal's row order (`_id`)."""
    fields, records, offset = None, [], 0
    while True:
        query = urllib.parse.urlencode(
            {"resource_id": resource_id, "limit": page, "offset": offset, "sort": "_id"}
        )
        body = get(f"{API}?{query}")
        if not body.get("success"):
            raise RuntimeError(f"datastore_search failed for {resource_id}")
        result = body["result"]
        if fields is None:
            fields = [f["id"] for f in result["fields"]]
        records.extend(result["records"])
        offset += page
        if not result["records"] or offset >= result["total"]:
            break
        time.sleep(pause)
    if len(records) != result["total"]:
        raise RuntimeError(f"{resource_id}: got {len(records)} rows, portal says {result['total']}")
    return {"resource_id": resource_id, "fields": fields, "records": records}


def serialise(payload: dict) -> bytes:
    """A stable text form: one record per line, keys in the portal's field order."""
    fields = payload["fields"]
    lines = [
        "{",
        f' "resource_id": {json.dumps(payload["resource_id"])},',
        f' "fields": {json.dumps(fields, ensure_ascii=False)},',
        ' "records": [',
    ]
    rows = [
        "  " + json.dumps([rec.get(f) for f in fields], ensure_ascii=False)
        for rec in payload["records"]
    ]
    lines.append(",\n".join(rows))
    lines += [" ]", "}"]
    return ("\n".join(lines) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
