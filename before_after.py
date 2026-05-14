"""
Run baseline qwen3-8b vs fine-tuned qwen3-8b on the same paper prompt
to generate before/after demo examples for the post.

Uses a paper OUTSIDE the training set (2025 or earlier) to prove
generalization rather than memorization.
"""

import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "before_after_samples.json"
OUT_MD = HERE / "before_after_samples.md"

# Load env
env_path = HERE / ".env"
for line in env_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

API_KEY = os.environ.get("FIREWORKS_API_KEY") or os.environ["PI_API_KEY"]

BASE_MODEL = "accounts/fireworks/models/qwen3-8b"
FT_MODEL = "accounts/<your-account>/models/<your-fine-tuned-model>"
FT_DEPLOYMENT = "accounts/<your-account>/deployments/<your-deployment>"
# Fireworks inference uses <model>#<deployment> to pin routing to a specific deployment
FT_MODEL_PINNED = f"{FT_MODEL}#{FT_DEPLOYMENT}"

SYSTEM = (
    "You write concise, structured summaries of AI research papers in the "
    "style of DAIR.AI's Top AI Papers of the Week. Open with a one-paragraph "
    "lede that names the authors' affiliation and the core contribution, then "
    "follow with three to five bulleted takeaways. Each bullet begins with a "
    "bolded short label, a colon, then a crisp explanation. Keep the tone "
    "analytical, specific, and free of hype."
)

# Three test papers, all OUTSIDE the 2026 training set
TEST_PAPERS = [
    {
        "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
        "arxiv_id": "2201.11903",
    },
    {
        "title": "Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
        "arxiv_id": "2305.18290",
    },
    {
        "title": "Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
        "arxiv_id": "2312.00752",
    },
]


def fetch_abstract(arxiv_id: str) -> str:
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "dair-wiki-sft/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    summary = entry.find("atom:summary", ns).text
    return " ".join(summary.split())


def build_user_msg(title: str, abstract: str) -> str:
    return (
        f"Paper: {title}\n\n"
        f"Abstract:\n{abstract}\n\n"
        "Write a Top AI Papers of the Week style summary."
    )


def call_model(model_id: str, messages: list) -> str:
    body = json.dumps(
        {
            "model": model_id,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 2500,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.fireworks.ai/inference/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def main():
    results = []
    for p in TEST_PAPERS:
        print(f"\n=== {p['title']} ===")
        abstract = fetch_abstract(p["arxiv_id"])
        print(f"Abstract ({len(abstract)} chars) fetched")
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_user_msg(p["title"], abstract)},
        ]
        print("  calling baseline...")
        baseline = call_model(BASE_MODEL, messages)
        print("  calling fine-tuned...")
        try:
            finetuned = call_model(FT_MODEL, messages)
        except Exception as e1:
            print(f"  (plain FT id failed: {e1}; retrying with deployment pin)")
            finetuned = call_model(FT_MODEL_PINNED, messages)
        results.append(
            {
                "title": p["title"],
                "arxiv_id": p["arxiv_id"],
                "abstract": abstract,
                "baseline": baseline,
                "finetuned": finetuned,
            }
        )

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nSaved JSON: {OUT}")

    # Also write a readable markdown
    lines = ["# Before / After Samples", ""]
    for r in results:
        lines.append(f"## {r['title']}")
        lines.append(f"arXiv: {r['arxiv_id']}")
        lines.append("")
        lines.append("### BASELINE (qwen3-8b)")
        lines.append(r["baseline"])
        lines.append("")
        lines.append("### FINE-TUNED (qwen3-8b-ft)")
        lines.append(r["finetuned"])
        lines.append("")
        lines.append("---")
        lines.append("")
    OUT_MD.write_text("\n".join(lines))
    print(f"Saved MD:   {OUT_MD}")


if __name__ == "__main__":
    main()
