"""
Test the freshly Pilot-Agent-deployed model on the same 3 papers used in
before_after.py. Verifies the new deployment qwen3-8b-sft-wiki-2026 produces
DAIR.AI-style summaries (style transfer working).
"""

import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
OUT_MD = HERE / "new_deployment_samples.md"
OUT_JSON = HERE / "new_deployment_samples.json"

env_path = HERE / ".env"
for line in env_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

API_KEY = os.environ["FIREWORKS_API_KEY"]

# Today's run from Pilot Agent
NEW_MODEL = "accounts/<your-account>/models/<your-fine-tuned-model>"
NEW_DEPLOYMENT = "accounts/<your-account>/deployments/<your-deployment>"
PINNED = f"{NEW_MODEL}#{NEW_DEPLOYMENT}"

SYSTEM = (
    "You write concise, structured summaries of AI research papers in the "
    "style of DAIR.AI's Top AI Papers of the Week. Open with a one-paragraph "
    "lede that names the authors' affiliation and the core contribution, then "
    "follow with three to five bulleted takeaways. Each bullet begins with a "
    "bolded short label, a colon, then a crisp explanation. Keep the tone "
    "analytical, specific, and free of hype."
)

TEST_PAPERS = [
    {"title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models", "arxiv_id": "2201.11903"},
    {"title": "Direct Preference Optimization: Your Language Model is Secretly a Reward Model", "arxiv_id": "2305.18290"},
    {"title": "Mamba: Linear-Time Sequence Modeling with Selective State Spaces", "arxiv_id": "2312.00752"},
]


def fetch_abstract(arxiv_id):
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "dair-wiki-sft/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    summary = root.find("atom:entry", ns).find("atom:summary", ns).text
    return " ".join(summary.split())


def build_user_msg(title, abstract):
    return (
        f"Paper: {title}\n\nAbstract:\n{abstract}\n\n"
        "Write a Top AI Papers of the Week style summary."
    )


def call_model(model_id, messages, max_retries=8):
    import time
    body = json.dumps({
        "model": model_id, "messages": messages,
        "temperature": 0.0, "max_tokens": 2500,
    }).encode()
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                "https://api.fireworks.ai/inference/v1/chat/completions",
                data=body,
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (503, 502, 504, 429) and attempt < max_retries - 1:
                wait = min(60, 15 + 15 * attempt)
                print(f"    {e.code} — cold start? retrying in {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            raise
    raise last_err


def strip_think(text):
    # Qwen3 emits <think>...</think> blocks; strip for clean display
    if "</think>" in text:
        return text.split("</think>", 1)[1].lstrip()
    return text


def main():
    results = []
    for p in TEST_PAPERS:
        print(f"\n=== {p['title']} ===")
        abstract = fetch_abstract(p["arxiv_id"])
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_user_msg(p["title"], abstract)},
        ]
        print("  calling new deployment...")
        raw = call_model(PINNED, messages)
        clean = strip_think(raw)
        results.append({
            "title": p["title"], "arxiv_id": p["arxiv_id"],
            "abstract": abstract, "output": clean, "raw": raw,
        })

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    lines = ["# New Deployment Samples (qwen3-8b-sft-wiki-2026, Pilot-Agent-deployed)", ""]
    for r in results:
        lines.append(f"## {r['title']}")
        lines.append(f"arXiv: {r['arxiv_id']}")
        lines.append("")
        lines.append("### Output")
        lines.append(r["output"])
        lines.append("")
        lines.append("---")
        lines.append("")
    OUT_MD.write_text("\n".join(lines))
    print(f"\nSaved: {OUT_MD}")


if __name__ == "__main__":
    main()
