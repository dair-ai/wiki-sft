"""
Build chat-format JSONL for Fireworks SFT from parsed_with_abstracts.json.

Output format (one JSON object per line):
{
  "messages": [
    {"role": "system", "content": "<style instruction>"},
    {"role": "user", "content": "<title + abstract>"},
    {"role": "assistant", "content": "<cleaned wiki summary>"}
  ]
}

Cleanup applied to the assistant summary:
- Replace HTML <br> with newlines
- Normalize bullet markers (●, •) to "- "
- Collapse repeated whitespace

Splits: 90/10 train/val, seeded so runs are reproducible.
"""

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).parent
IN = HERE / "parsed_with_abstracts.json"
TRAIN = HERE / "train.jsonl"
VAL = HERE / "val.jsonl"
FULL = HERE / "all.jsonl"

SYSTEM_PROMPT = (
    "You write concise, structured summaries of AI research papers in the "
    "style of DAIR.AI's Top AI Papers of the Week. Open with a one-paragraph "
    "lede that names the authors' affiliation and the core contribution, then "
    "follow with three to five bulleted takeaways. Each bullet begins with a "
    "bolded short label, a colon, then a crisp explanation. Keep the tone "
    "analytical, specific, and free of hype."
)

BR_RE = re.compile(r"<br\s*/?>", re.I)
BULLET_RE = re.compile(r"[●•]\s*")
WS_RE = re.compile(r"[ \t]+")
BLANK_RE = re.compile(r"\n{3,}")


def clean_summary(text: str) -> str:
    t = BR_RE.sub("\n", text)
    t = BULLET_RE.sub("\n- ", t)
    # If the first bullet became a leading newline, strip it
    t = t.lstrip("\n").rstrip()
    # Collapse runs of spaces, but preserve newlines
    lines = [WS_RE.sub(" ", ln).rstrip() for ln in t.split("\n")]
    t = "\n".join(lines)
    t = BLANK_RE.sub("\n\n", t)
    return t.strip()


def build_user_msg(title: str, abstract: str) -> str:
    return (
        f"Paper: {title}\n\n"
        f"Abstract:\n{abstract}\n\n"
        "Write a Top AI Papers of the Week style summary."
    )


def main():
    entries = json.loads(IN.read_text())
    usable = [e for e in entries if e.get("abstract")]
    print(f"Total entries: {len(entries)}")
    print(f"Usable (has abstract): {len(usable)}")

    records = []
    for e in usable:
        cleaned = clean_summary(e["summary"])
        records.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_msg(e["title"], e["abstract"])},
                    {"role": "assistant", "content": cleaned},
                ],
                "_meta": {
                    "week": e["week"],
                    "rank": e["rank"],
                    "title": e["title"],
                    "arxiv_id": e.get("arxiv_id"),
                },
            }
        )

    # Write the full unfiltered file for inspection (with _meta)
    FULL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records))

    # Strip _meta for the actual training files
    def for_train(r):
        return {"messages": r["messages"]}

    rng = random.Random(42)
    rng.shuffle(records)
    n_val = max(1, round(len(records) * 0.10))
    val = records[:n_val]
    train = records[n_val:]

    TRAIN.write_text("\n".join(json.dumps(for_train(r), ensure_ascii=False) for r in train))
    VAL.write_text("\n".join(json.dumps(for_train(r), ensure_ascii=False) for r in val))

    print(f"\nTrain: {len(train)} -> {TRAIN.name}")
    print(f"Val:   {len(val)} -> {VAL.name}")
    print(f"All (with _meta): {len(records)} -> {FULL.name}")

    # Show one cleaned example
    print("\n=== Sample assistant message (cleaned) ===")
    print(records[0]["messages"][2]["content"][:1200])


if __name__ == "__main__":
    main()
