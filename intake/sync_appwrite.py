"""Copy Sprint intake documents from Appwrite into intake/submissions/.

Reads intake/appwrite.local.json (gitignored). Does not send email and
does not charge anyone. One JSON file per document, named by document id.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/workspace/vcore-sprint")
CONFIG = ROOT / "intake" / "appwrite.local.json"
STORE = ROOT / "intake" / "submissions"
FIELDS = (
    "buyer_contact",
    "track",
    "offer_details",
    "audience",
    "price",
    "intended_action",
    "urls_or_files",
    "brand_voice",
    "approved_factual_claims",
    "required_timing",
)


def load_config(path: Path = CONFIG) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("endpoint", "project", "databaseId", "collectionId", "secret"):
        if not data.get(key):
            raise ValueError(f"missing {key}")
    return data


def list_documents(config: dict) -> list[dict]:
    documents: list[dict] = []
    cursor = None
    while True:
        query = [urllib.parse.quote(json.dumps({"method": "limit", "values": [100]}))]
        if cursor:
            query.append(urllib.parse.quote(json.dumps({"method": "cursorAfter", "values": [cursor]})))
        qs = "&".join(f"queries[]={item}" for item in query)
        url = (
            f"{config['endpoint']}/databases/{config['databaseId']}"
            f"/collections/{config['collectionId']}/documents?{qs}"
        )
        req = urllib.request.Request(url)
        req.add_header("X-Appwrite-Project", config["project"])
        req.add_header("X-Appwrite-Key", config["secret"])
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        batch = payload.get("documents") or []
        documents.extend(batch)
        if len(batch) < 100:
            return documents
        cursor = batch[-1]["$id"]


def record_from_document(document: dict) -> dict:
    record = {field: document.get(field) if document.get(field) is not None else "" for field in FIELDS}
    record["track"] = str(record["track"]).strip().upper()
    record["appwrite_id"] = document.get("$id")
    record["received_at"] = document.get("$createdAt")
    return record


def sync(config: dict | None = None, store: Path = STORE) -> list[Path]:
    config = config or load_config()
    store.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for document in list_documents(config):
        doc_id = document.get("$id")
        if not doc_id:
            continue
        dest = store / f"{doc_id}.json"
        record = record_from_document(document)
        text = json.dumps(record, indent=2) + "\n"
        if dest.exists() and dest.read_text(encoding="utf-8") == text:
            continue
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(dest)
        written.append(dest)
    return written


def main() -> int:
    written = sync()
    for path in written:
        print(f"stored={path}")
    print(f"wrote={len(written)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
