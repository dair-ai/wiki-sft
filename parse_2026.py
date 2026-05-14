"""
Parse 2026.md from AI-Papers-of-the-Week repo.
Extract top 5 papers per week with:
  - week header
  - rank (1-5)
  - title
  - summary (raw markdown, including bullet points)
  - arxiv_url (if present)
"""

import json
import re
from pathlib import Path

SRC = Path(__file__).parent.parent.parent.parent.parent / "experiments" / "fireworks-wiki-sft" / "2026.md"
OUT = Path(__file__).parent / "parsed_entries.json"

WEEK_RE = re.compile(r"^## Top AI Papers of the Week \((.+?)\) - 2026\s*$", re.M)
# Each paper row starts with "| N) **Title** - rest..."
ROW_RE = re.compile(r"^\|\s*(\d+)\)\s*\*\*(.+?)\*\*\s*-\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", re.M)
ARXIV_RE = re.compile(r"\[Paper\]\((https?://arxiv\.org/abs/[^)\s]+)\)")
ANY_PAPER_LINK_RE = re.compile(r"\[Paper\]\(([^)]+)\)")


def parse(text: str):
    # Split by week header
    week_positions = [(m.start(), m.group(1)) for m in WEEK_RE.finditer(text)]
    week_positions.append((len(text), None))
    entries = []
    for i in range(len(week_positions) - 1):
        start, week = week_positions[i]
        end, _ = week_positions[i + 1]
        block = text[start:end]
        for m in ROW_RE.finditer(block):
            rank = int(m.group(1))
            if rank > 5:
                continue
            title = m.group(2).strip()
            body = m.group(3).strip()
            links = m.group(4).strip()
            arxiv_m = ARXIV_RE.search(links)
            any_m = ANY_PAPER_LINK_RE.search(links)
            arxiv_url = arxiv_m.group(1) if arxiv_m else None
            paper_url = any_m.group(1) if any_m else None
            entries.append({
                "week": week,
                "rank": rank,
                "title": title,
                "summary": body,
                "arxiv_url": arxiv_url,
                "paper_url": paper_url,
                "has_arxiv": arxiv_url is not None,
            })
    return entries


def main():
    text = SRC.read_text(encoding="utf-8")
    entries = parse(text)

    # Summary stats
    weeks = sorted({e["week"] for e in entries})
    total = len(entries)
    with_arxiv = sum(1 for e in entries if e["has_arxiv"])
    print(f"Weeks found: {len(weeks)}")
    print(f"Total top-5 entries: {total}")
    print(f"Entries with arXiv link: {with_arxiv} ({with_arxiv/total:.0%})")
    print(f"Entries with non-arXiv paper link: {total - with_arxiv}")
    print()
    print("Weeks (chronological, reverse):")
    for w in weeks:
        c = sum(1 for e in entries if e["week"] == w)
        print(f"  {w}: {c} entries")

    OUT.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {total} entries to {OUT}")


if __name__ == "__main__":
    main()
