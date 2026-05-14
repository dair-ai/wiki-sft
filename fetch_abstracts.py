"""
Fetch arXiv abstracts for parsed entries that have arxiv_url.
Uses the arXiv Atom API: http://export.arxiv.org/api/query?id_list=<ids>
Polite: batches of 25, 3s between calls.
Writes parsed_with_abstracts.json.
"""

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
IN = HERE / "parsed_entries.json"
OUT = HERE / "parsed_with_abstracts.json"

ARXIV_ID_RE = re.compile(r"arxiv\.org/abs/([^/?#]+)")
NS = {"atom": "http://www.w3.org/2005/Atom"}


def extract_id(url: str) -> str | None:
    m = ARXIV_ID_RE.search(url)
    if not m:
        return None
    # Strip version suffix (v1, v2 ...) so id_list matches base record
    aid = m.group(1)
    return re.sub(r"v\d+$", "", aid)


def fetch_batch(ids: list[str]) -> dict[str, str]:
    url = f"http://export.arxiv.org/api/query?id_list={','.join(ids)}&max_results={len(ids)}"
    req = urllib.request.Request(url, headers={"User-Agent": "dair-wiki-sft/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    out = {}
    for entry in root.findall("atom:entry", NS):
        id_el = entry.find("atom:id", NS)
        summary_el = entry.find("atom:summary", NS)
        if id_el is None or summary_el is None:
            continue
        aid_full = id_el.text.strip()
        aid_m = ARXIV_ID_RE.search(aid_full)
        if not aid_m:
            continue
        aid = re.sub(r"v\d+$", "", aid_m.group(1))
        out[aid] = " ".join(summary_el.text.split())
    return out


def main():
    entries = json.loads(IN.read_text())
    to_fetch = []
    for e in entries:
        if e["arxiv_url"]:
            aid = extract_id(e["arxiv_url"])
            if aid:
                e["arxiv_id"] = aid
                to_fetch.append(aid)
            else:
                e["arxiv_id"] = None
        else:
            e["arxiv_id"] = None

    unique_ids = sorted(set(to_fetch))
    print(f"Fetching {len(unique_ids)} unique arXiv abstracts...")

    abstracts: dict[str, str] = {}
    BATCH = 25
    for i in range(0, len(unique_ids), BATCH):
        batch = unique_ids[i : i + BATCH]
        print(f"  batch {i//BATCH + 1}: {len(batch)} ids")
        try:
            got = fetch_batch(batch)
        except Exception as exc:
            print(f"  error: {exc}; retrying once after 10s")
            time.sleep(10)
            got = fetch_batch(batch)
        abstracts.update(got)
        print(f"    got {len(got)} / {len(batch)}")
        if i + BATCH < len(unique_ids):
            time.sleep(3)

    missing = [aid for aid in unique_ids if aid not in abstracts]
    print(f"\nFetched {len(abstracts)} / {len(unique_ids)} abstracts")
    if missing:
        print(f"Missing: {missing}")

    for e in entries:
        aid = e.get("arxiv_id")
        e["abstract"] = abstracts.get(aid) if aid else None

    OUT.write_text(json.dumps(entries, indent=2, ensure_ascii=False))
    with_abs = sum(1 for e in entries if e.get("abstract"))
    print(f"\nEntries with abstract: {with_abs} / {len(entries)}")
    print(f"Saved to {OUT}")


if __name__ == "__main__":
    main()
