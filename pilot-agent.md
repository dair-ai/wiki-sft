---
description: Run the Fireworks Agent to fine-tune a model end-to-end
argument-hint: "What would you like the Fireworks Agent to do?"
allowed-tools: Bash(source:*), Bash(firectl session create:*), Bash(firectl session get:*), Bash(firectl session events:*), Bash(firectl session list:*)
---

# Fireworks Agent

You are helping a user run the Fireworks Agent (`firectl session`), which handles data prep, model selection, hyperparameter sweeps, evals, and deployment automatically.

User input: $ARGUMENTS

> **Session continuity**: If the user references an existing session ID, always send follow-up actions to that same session via `session update`. Never create a new session for a follow-up.

> **Autonomy**: Run all read and initiation commands (`create`, `get`, `events`, `list`) without asking for user approval. Only pause for user confirmation on `session update` (sending a response to the agent), `session cancel`, and `session delete` — these are consequential and irreversible.

---

## Phase 0: Verify service account key

Source the `.env` file and check that `PI_API_KEY` is set:

```bash
source .env && [ -n "$PI_API_KEY" ] && echo "PI_API_KEY is set" || echo "PI_API_KEY is missing"
```

- If set and non-empty, proceed using `--api-key $PI_API_KEY` on every `firectl` command.
- If empty or unset, **stop immediately** and tell the user:

  > A Fireworks service account API key is required to run the Fireworks Agent.
  >
  > **To set one up:**
  > 1. Have an admin create a key for your service account:
  >    ```bash
  >    firectl api-key create --service-account=<your-service-account>
  >    ```
  > 2. Add it to the `.env` file in this project:
  >    ```
  >    PI_API_KEY=<your-api-key>
  >    ```
  > 3. Re-run this command once the key is set.

---

## Phase 1: Gather inputs

If `$ARGUMENTS` is already provided, skip this phase entirely and go straight to Phase 2 — do not ask for confirmation.

If `$ARGUMENTS` is empty, ask the user one question:

> "What would you like the Fireworks Agent to do?"

Use their response as the instruction in Phase 2. Do not ask follow-up questions about dataset, model, or anything else — pass the response as-is and let the Fireworks Agent handle the rest.

---

## Phase 2: Create the session

```bash
source .env && firectl session create \
  --api-key $PI_API_KEY \
  -i "<task description, model (if specified), and dataset in one sentence>"
```

**Confirmed flags:**
- `-i / --instruction` *(required)* — natural language instruction, e.g. `"Run supervised fine-tuning on Qwen 32B using dataset accounts/<your-account>/datasets/<your-dataset>"`
- `--scope` *(default: optimize)*
- `--dry-run` — print the request without executing, useful for verifying before launch
- `-o / --output` — output format: `text`, `json`, or `flag` (default: text)

Print the returned session ID and immediately move to Phase 3.

---

## Phase 3: Stream and monitor

Run autonomously — do not ask the user for permission to monitor.

### Initial stream (first run)

On the first stream after session creation, show the full history:

```bash
source .env && firectl session events <session-id> --api-key $PI_API_KEY --wait
```

**Confirmed flags:**
- `-w / --wait` — keeps streaming until session completes or enters `waiting`. **Always use this** — without it, the command dumps existing events and exits immediately.
- `--scope` *(default: optimize)*

Summarize stages as they appear: dataset inspection, model resolution, HP sweep planning, job launches, promotion gate, full training, final report.

If the stream exits with `waiting` → go to Phase 4.
If the stream exits with `succeeded` → go to Phase 5.
If the stream exits with `failed` → go to Phase 6.

### Fallback: poll with `get`

If the stream drops unexpectedly (network error, timeout), fall back to polling:

```bash
source .env && until firectl session get <session-id> --api-key $PI_API_KEY 2>/dev/null | grep -E "waiting|succeeded|failed|cancelled"; do sleep 10; done && firectl session get <session-id> --api-key $PI_API_KEY
```

---

## Phase 4: Handle waiting states

This phase and Phase 3 form a reactive loop that continues until the session is done.

### Step 1 — capture last timestamp

Before doing anything else, record the timestamp of the last event currently in the stream. This is used to filter out history on the next stream:

```bash
source .env && LAST_TS=$(firectl session events <session-id> --api-key $PI_API_KEY 2>/dev/null \
  | grep -oE '^\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\]' | tail -1)
```

### Step 2 — surface the exact agent question

Extract the last `status_info` block — everything from the final `status_info` line up to `[done] session status: waiting`:

```bash
source .env && firectl session events <session-id> --api-key $PI_API_KEY 2>/dev/null \
  | awk '/\] status_info:/{buf=""} {buf=buf"\n"$0} /\[done\] session status: waiting/{print buf}'
```

Show the agent's **exact question** to the user — do not paraphrase. **Wait for their response before proceeding.**

### Step 3 — send the response

**⚠️ Always confirm with the user before running `session update`** — this sends a message directly to the fine-tuning agent and influences training decisions.

```bash
source .env && firectl session update <session-id> --api-key $PI_API_KEY -i "<user response>"
```

**Confirmed flags:**
- `-i / --instruction` *(required)* — the response to send
- `--scope` *(default: optimize)*

**Common agent questions and good responses:**
- Evaluation path → `"validation loss is fine"` (selects Path A, no evaluator)
- Plan approval → `"Approved, proceed."`
- HP results / promotion gate → `"Proceed with the winning config."`

### Step 4 — resume streaming from where we left off

After sending the update, stream again but filter out everything at or before `LAST_TS` so the user only sees new traces:

```bash
source .env && firectl session events <session-id> --api-key $PI_API_KEY --wait 2>/dev/null \
  | awk -v ts="$LAST_TS" '/^\[20/{show=($0>ts)} show{print}'
```

The `awk` logic:
- Lines starting with a timestamp: set `show=1` if newer than `LAST_TS`, else `show=0`
- Continuation lines (no timestamp): inherit `show` from the previous timestamped line

**This loop — stream → waiting → capture timestamp → surface question → get response → update → filtered stream — repeats until the session reaches `succeeded`, `failed`, or `cancelled`.**

---

## Phase 5: Completion

When status is `succeeded`, report:
- Deployed model ID
- Deployment ID and inference endpoint
- Final training and eval loss
- Suggested next steps (e.g. query via the Fireworks inference API)

---

## Phase 6: Handle failures

When status is `failed`, surface the error by checking the last events:

```bash
source .env && firectl session events <session-id> --api-key $PI_API_KEY 2>/dev/null | grep -E "error|failed|status_info" | tail -20
```

Show the error clearly to the user and present options:
1. **Retry** — create a new session with the same instruction
2. **Modify and retry** — adjust the instruction based on the error and create a new session
3. **Abandon** — cancel and clean up if needed

Do not retry automatically — let the user decide.

---

## Phase 7: Cancel or delete

**⚠️ Always confirm with the user before running either of these commands.**

**Cancel** (stops a running session, keeps the record):
```bash
source .env && firectl session cancel <session-id> --api-key $PI_API_KEY
```

**Delete** (removes the session record entirely — irreversible):
```bash
source .env && firectl session delete <session-id> --api-key $PI_API_KEY
```

Both accept `--scope` (default: optimize).

---

## Phase 8: Update this skill after every run

After every session, update this file with anything newly confirmed:
- Correct any flags that failed and replace with the confirmed working version
- Never document unverified flags — only what was confirmed in an actual run

---

## Reference: List sessions

```bash
source .env && firectl session list --api-key $PI_API_KEY
```

**Confirmed flags:**
- `--filter` — AIP-160 filter expression (e.g. `status=waiting`)
- `--order-by` — field to sort by, append ` desc` for descending
- `--no-paginate` — return all results without pagination
- `--page-size` — max results per page
- `--page-token` — specific page to fetch
- `--scope` *(default: optimize)*
- `-o / --output` — `text` or `json` (default: text)
- Alias: `ls`
