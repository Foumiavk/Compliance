# Enterprise Compliance Evidence Copilot

An enterprise agentic AI capstone for audit-evidence readiness and governed
remediation planning. Compare the same assessment as a **monolithic agent** and
a **capability-scoped multi-agent system**, using the same controls, evidence,
tools, persistence and evaluation cases.

Inspired by IncidentOps' evidence -> playbook -> proposal -> draft -> audit
timeline workflow, adapted to compliance operations.

**Synthetic teaching application, not legal advice, compliance certification,
or an implementation of an entire regulatory framework. No real compliance
documents or credentials are included. No Git repository is initialized.**

## What it does

- Maps evidence to three illustrative internal controls and their owners.
- Checks evidence freshness and scope at a fixed fixture reference date.
- Distinguishes `supported`, `gap`, and `insufficient_evidence`.
- Retrieves internal remediation playbooks with stable identifiers.
- Creates owner-approval proposals and unpublished internal summary drafts.
- Persists audit-scoped history, complete runs, tool outputs and artifacts in SQLite.
- Exposes FastAPI endpoints and a local Gradio comparison UI.
- Runs 12 evaluation scenarios against both architectures, with latency, model
  calls, provider-reported tokens, tool counts and contract checks.

## Quick start: macOS / Linux

Requires **Python 3.11 or newer**. If `python3` is an older system interpreter,
use the executable for a supported installation, such as `python3.11`.

```bash
cd /Users/FVA01/code/Compliance
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn complianceops.api:app --reload --host 127.0.0.1
```

No `.env` file is required for offline mode; the application uses offline
defaults. To override settings locally, create a `.env` file in the project
root. It is ignored by Git and should not be committed.

Open <http://127.0.0.1:8000/docs>. In another activated terminal, launch the UI:

```bash
python app.py
```

Open the local address printed by Gradio, normally <http://127.0.0.1:7860>.
The UI calls the same service directly; the API does not have to be running.
Both use the same configured SQLite database.

The default is **offline mode**, which requires no model credentials and makes
no LLM calls. It runs deterministic tool workflows and a template answer.
Scope and explicit flags drive this mode; it does **not** interpret free-text
requests or simulate model reasoning. Its zero token/model-call counts are real.

The supplied environment already has a Python 3.11 virtual environment and
installed dependencies; on that machine you can start with
`source .venv/bin/activate`.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn complianceops.api:app --reload --host 127.0.0.1
```

Dependencies are declared once in [pyproject.toml](./pyproject.toml).
[requirements.txt](./requirements.txt) installs this project and its test
dependencies in editable mode; it is not a separate, drifting dependency list.

## Live model mode

Create or edit `.env` in the project root with your own model credentials:

```dotenv
RUNTIME_MODE=live
OPENAI_API_KEY=your-own-key
OPENAI_MODEL=gpt-4o-mini
```

Restart the API/UI after changing configuration. `OPENAI_API_BASE` optionally
targets an OpenAI-compatible endpoint. Missing credentials or provider failures
are explicit errors, not an automatic offline fallback.

Live mode uses LangChain tool-calling agents. Each stage first performs mandatory
deterministic evidence/governance checks; the LLM receives those records and can
make additional calls within its tool scope. The monolith has one agent, while
the multi-agent version invokes selected specialists sequentially and then a
tool-free supervisor. A tool loop can make multiple model calls.

The LLM explains findings; it does not determine the authoritative finding
status, approval status, evidence metadata or whether an action occurred.
Review live prose against the structured response before relying on it.

Only synthetic fixtures are wired here. Live mode sends the request, applicable
audit history and synthetic tool records to your configured model endpoint.
Do not enter real confidential evidence without authorization and appropriate
data-handling controls. Offline mode remains the safe classroom default.

## LangSmith tracing (optional)

Tracing is **off by default**. To record every assessment in [LangSmith](https://smith.langchain.com),
add to your local `.env` and restart the API/UI:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=compliance-evidence-copilot
```

Each assessment becomes one root trace, `compliance_assessment`, tagged with the architecture and
runtime mode and carrying `audit_id`, `architecture`, `runtime_mode` and `prompt_strategy` metadata.
Tool calls appear as child runs. In live mode each agent run (`compliance_monolith`,
`evidence_agent`, ..., `supervisor`) and its model calls are nested beneath it, so you can inspect
prompts, tool loops, tokens and latency. The legacy `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY`
names also work. Enabling tracing without a key is an explicit startup error.

Traces contain the request, audit-scoped tool records and the answer, and live traces contain full
prompts. Enable tracing only with the synthetic fixtures, or with data you are authorized to send to
LangSmith.

## Example assessment

```bash
curl -sS http://127.0.0.1:8000/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{
    "audit_id": "AUD-20261025",
    "architecture": "multi_agent",
    "control_ids": ["AC-01", "BC-01", "VR-01"],
    "request": "Assess evidence readiness, identify gaps and unknowns, propose next steps and draft an internal summary.",
    "propose_remediation": true,
    "draft_summary": true
  }'
```

Use `"architecture": "monolith"` for the baseline. Omit the architecture to use
`DEFAULT_ARCHITECTURE`. Scope is explicit, nonempty, unique and limited to known
control IDs. Audit IDs follow `AUD-` plus 1-64 letters, digits or hyphens.

### Expected baseline findings

All ages are evaluated as of **2026-10-25**, not today's wall clock:

| Control | Policy | Evidence condition | Finding |
|---|---|---|---|
| AC-01: quarterly production access review | POL-ACCESS-01 | Production record is stale; recent staging record is out of scope | `insufficient_evidence` |
| BC-01: backup restoration test | POL-RESILIENCE-02 | Current successful production restore record | `supported` |
| VR-01: annual critical-vendor review | POL-VENDOR-03 | No evidence supplied | `insufficient_evidence` |

With both flags enabled, the baseline produces two proposals (AC-01, VR-01) and
one internal draft. A current in-scope failure yields `gap`; conflicting current
pass/fail records also yield `gap` pending review. Future-dated records are
rejected. The maximum age is inclusive.

**Missing evidence is not proof that a control failed.** These controls are
SOC 2-inspired internal examples, not official framework mappings or auditor
opinions.

## Architecture

```text
FastAPI / Gradio
       |
Validated audit scope + explicit artifact flags
       |
Bounded audit memory + run-scoped tool session
       |
       +----------------------------+
       |                            |
 MONOLITH                     MULTI-AGENT
 one agent                    evidence specialist
 all enabled tools                   |
       |                      remediation specialist (optional)
       |                             |
       |                      reporting specialist (optional)
       |                             |
       |                      tool-free supervisor
       +----------------------------+
                     |
 authoritative findings + proposals + draft + trace
                     |
          transactional SQLite run record
```

| Principal | Tools |
|---|---|
| `compliance_monolith` | All enabled tools |
| `evidence_agent` | `lookup_control`, `list_evidence`, `assess_control` |
| `remediation_agent` | `search_compliance_playbooks`, `propose_remediation` |
| `reporting_agent` | `draft_audit_summary` |
| `supervisor` | None |

Routing uses explicit flags, not keywords inside untrusted requests. Disabling
an artifact removes its tool even from the monolith. Scope is checked again
inside control-specific tools. No execution, approval or publication tool exists.
Proposals and drafts are idempotent within one run; a later assessment creates
new artifact IDs and retains the earlier run.

The monolith always consults playbooks; the multi-agent workflow consults them
when the remediation specialist is selected. Specialists receive earlier raw
tool records and reports, so the supervisor can check handoffs against facts.
More agents are not automatically better: compare reasoning quality, latency,
tokens, extra tool calls and handoff errors in **live** mode.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Process liveness, not a provider-readiness check |
| GET | `/v1/controls` | Control catalog and fixture date |
| POST | `/v1/assessments` | Run an assessment |
| GET | `/v1/audits/{audit_id}/memory` | Inspect bounded history and total saved run count |
| GET | `/v1/audits/{audit_id}/runs/{run_id}` | Retrieve a complete saved run for that audit |
| DELETE | `/v1/audits/{audit_id}/memory` | Erase that audit's history and saved runs |

Responses include `findings`, `proposals`, `draft`, `answer`, `route`,
`tool_calls`, `tool_results`, `latency_seconds`, `token_count`, `model_calls`,
`runtime_mode`, `fixture_as_of`, `run_id` and limitations.

Invalid contracts return 422, unavailable audit/run combinations return 404,
and model execution errors return 502. Errors are logged server-side.
Failed model runs record an error event but no completed run or artifact record.
Successful runs persist all findings, trace and artifacts in one transaction.

```bash
curl -sS http://127.0.0.1:8000/v1/audits/AUD-20261025/memory
# Destructive for this synthetic audit only:
curl -sS -X DELETE http://127.0.0.1:8000/v1/audits/AUD-20261025/memory
```

## Tests and evaluations

```bash
python -m pytest -q
python -m complianceops.evaluation --mode offline --output data/eval-results-offline.json
# Equivalent installed console script:
compliance-eval --mode offline
```

The dataset is [eval_cases.jsonl](./src/complianceops/fixtures/eval_cases.jsonl).
It ships inside the installed package along with the catalog, so evaluations
also run outside the source directory. Each scenario/architecture gets an
isolated temporary SQLite database, which is cleaned up after evaluation.
Persisted JSON reports contain complete outputs/traces for later review.

The 12 cases cover stale evidence, wrong scope, missing evidence, supported
controls, full readiness, read-only scope, proposal-only requests, hostile user
instructions, failed tests, future dates, hostile evidence content, conflicting
records and the 90-day freshness boundary (some cases cover multiple concerns).

```bash
# Makes paid model calls and sends synthetic inputs to your configured provider:
python -m complianceops.evaluation --mode live --architecture both \
  --output data/eval-results-live.json

# Run a different dataset or only one architecture:
compliance-eval --cases path/to/cases.jsonl --architecture monolith --mode offline
```

The evaluation runner requires **100%** of its automated checks to pass and
exits nonzero otherwise. Checks cover finding statuses, proposal scope, rejected
evidence, citation presence, tool coverage, capability scope, proposal/draft
contracts and a narrow false-execution-claim red-flag detector.

**These checks do not prove semantic groundedness or prompt-injection
resistance.** Offline tests validate deterministic boundaries, not LLM reasoning.
Live reviews must examine unsupported claims, whether citations actually
support claims, overconfident legal conclusions, instruction following and
handoff quality. See the rubric in [FINAL_CLASS_GUIDE.md](./FINAL_CLASS_GUIDE.md).
Token usage is provider-reported; zero can mean usage metadata was unavailable.

### Verified local baseline

- 73 tests passed, including API/UI contracts, mocked live orchestration, prompt
  strategies, the baseline agent and LangSmith tracing (with a stub client).
- 24/24 offline evaluation runs passed (12 cases x 2 architectures).
- Dependency consistency and wheel packaging passed.
- Actual local FastAPI and Gradio servers passed HTTP smoke checks and were stopped.
- Live provider calls were not run.

The saved offline report is generated at `data/eval-results-offline.json`;
rerun the evaluation command after modifying fixtures or rules.

## Build phases and prompt strategies

This project is documented as three phases, each with a deliverable in [docs/](./docs):

| Phase | Deliverable |
|---|---|
| 1. Understand the problem and define success | [phase1-problem-definition.md](./docs/phase1-problem-definition.md) |
| 2. Build a basic working agent | [phase2-baseline-agent.md](./docs/phase2-baseline-agent.md), [sample interactions](./docs/phase2-baseline-interactions.md) |
| 3. Make the agent smarter (LLM and prompts) | [phase3-prompt-strategies.md](./docs/phase3-prompt-strategies.md) |

```bash
python -m complianceops.baseline "What is the status of the access review?"   # Phase 2 baseline
python -m complianceops.prompt_compare --mode live --output data/prompt-compare-live.json \
  --report docs/phase3-prompt-comparison-results.md                           # Phase 3 comparison
```

`PROMPT_STRATEGY` selects the live system prompt. The comparison runs every strategy over the same
12 cases and both architectures with the same automated checks. It makes paid model calls.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `RUNTIME_MODE` | `offline` | `offline` or `live` |
| `OPENAI_MODEL` | `gpt-4o-mini` | Live model identifier |
| `OPENAI_API_KEY` | unset | Required for live mode |
| `OPENAI_API_BASE` | unset | Optional compatible endpoint |
| `DEFAULT_ARCHITECTURE` | `monolith` | Architecture when omitted in a request |
| `MEMORY_DB_PATH` | `data/complianceops.db` | Local SQLite file |
| `MEMORY_MAX_EVENTS` | `20` | Events included in memory/prompt, not a retention limit |
| `MODEL_TIMEOUT_SECONDS` | `60` | Timeout per provider call, not the whole workflow |
| `AGENT_RECURSION_LIMIT` | `30` | Bound per agent tool loop |
| `LOG_LEVEL` | `INFO` | Server logging level |
| `PROMPT_STRATEGY` | `few_shot` | Live prompt: `minimal`, `guardrailed`, `structured` or `few_shot` |
| `LANGSMITH_TRACING` | `false` | `true` sends traces to LangSmith (needs `LANGSMITH_API_KEY`) |
| `LANGSMITH_API_KEY` | unset | LangSmith key; required only when tracing is on |
| `LANGSMITH_PROJECT` | `compliance-evidence-copilot` | LangSmith project that receives traces |
| `LANGSMITH_ENDPOINT` | LangSmith US | Only for EU or self-hosted LangSmith |

## Project layout

```text
app.py                          Local Gradio comparison UI
docs/                           Phase 1-3 deliverables and generated logs
src/complianceops/
  baseline.py                   Phase 2 rule-based agent (no LLM)
  prompts.py                    Phase 3 prompt strategies
  prompt_compare.py             Compare prompt strategies with the evaluation checks
  api.py                        Validated FastAPI endpoints
  config.py                     Environment settings
  domain.py                     Typed request, finding and artifact contracts
  knowledge.py                  Fixture retrieval and evidence assessment rules
  tools.py                      Scoped read/proposal/draft capabilities
  runtime.py                    Monolith, shared live adapter and offline workflow
  multi_agent.py                Specialist routing, handoffs and supervisor
  service.py                    End-to-end orchestration and persistence
  memory.py                     SQLite audit history and complete run storage
  evaluation.py                 Offline/live comparison runner and checks
  fixtures/catalog.json         Synthetic controls, evidence and playbooks
  fixtures/eval_cases.jsonl      Scenario dataset
tests/                          Offline contracts, API and mocked live tests
FINAL_CLASS_GUIDE.md             Teaching plan, evaluation rubric and extension ideas
```

## Production boundary

This is a local capstone, **not production-ready**. It has no authentication,
tenant authorization, immutable audit logging, encryption or retention policy.
Audit IDs provide storage separation, not access control. Prompt/tool history is
bounded but durable runs are retained until explicitly erased. Memory erasure is
a teaching feature, not an immutable compliance archive.

Do not expose the API/UI publicly or attach real evidence. Before production,
add identity and audit-level authorization to every read/write/delete operation,
data classification/redaction, provenance/integrity verification, append-only
external audit logs, retention/legal-hold handling, request and token budgets,
concurrency controls, human review workflows and a shared transactional database.
Evidence metadata is fixture-authored and trusted here; real ingestion must
validate dates, scope, provenance, document authenticity and coverage.
Sequential use is recommended for follow-up turns on the same audit.
