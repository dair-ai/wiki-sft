# wiki-sft

Companion repo for the blog post **Automating the LLM Fine-Tuning Loop with Fireworks Training Agent**.

It contains everything you need to reproduce the run end to end, fine-tuning Qwen3-8B on a personal AI-papers wiki using Fireworks Training Agent (previously known as Pilot Agent).

## Contents

### Dataset
- `train.jsonl` — training split (chat format)
- `val.jsonl` — validation split
- `wiki-sft-2026.jsonl` — combined dataset for reference

### Data-build scripts
- `parse_2026.py` — parse the DAIR.AI Top AI Papers of the Week wiki into structured entries
- `fetch_abstracts.py` — fetch arXiv abstracts for each entry
- `build_jsonl.py` — assemble the chat-format training records

### Training Agent
- `pilot-agent.md` — Claude Code slash command that wraps `firectl` and handles event streaming, gate detection, and resume logic

### Inference and evaluation
- `test_new_deployment.py` — smoke test for the deployed model
- `before_after.py` — baseline vs. fine-tuned comparison

## Setup

Install the Fireworks CLI and sign in.

```bash
brew install fw-ai/firectl/firectl
firectl signin
```

Create a `.env` file in the project root with two keys.

```
PI_API_KEY=<service-account key for Training Agent>
FIREWORKS_API_KEY=<user-level key>
```

## Reproduce

Follow the walkthrough in the blog post. The short version:

```bash
# Upload the dataset
source .env && firectl dataset create wiki-sft-2026 \
  --display-name "Wiki SFT 2026 (top 5 papers/week)" \
  train.jsonl \
  --api-key $FIREWORKS_API_KEY

# Kick off the Training Agent
source .env && firectl session create \
  --api-key $PI_API_KEY \
  -n "Run end-to-end supervised fine-tuning on qwen3-8b using dataset accounts/<your-account>/datasets/wiki-sft-2026 and deploy the trained model to a working inference endpoint that I can call via the Fireworks chat completions API. Use validation loss for evaluation. The full flow including deployment must complete automatically."
```

Then stream events, approve the plan, approve the winning HP config, and call the deployed model with `test_new_deployment.py`.

## License

MIT
