# Phase 3: Make the agent smarter

Phase 2's rule-based baseline could not handle paraphrase, negation or prioritization (see
[phase 2](./phase2-baseline-agent.md)). Phase 3 adds an LLM to the workflow and tests how the
**system prompt** changes behavior.

## How the LLM is integrated

The design is deliberately hybrid. Deterministic code still computes every finding, proposal and
draft from the catalog; the LLM receives those authoritative records and **explains and synthesizes**
them. It never decides finding status, approval or whether an action occurred. Live mode is
`RUNTIME_MODE=live` with `OPENAI_API_KEY` set; both architectures (monolith and multi-agent) use it.
See [runtime.py](../src/complianceops/runtime.py) and [multi_agent.py](../src/complianceops/multi_agent.py).

## Prompt strategies tested

All four share the same cases, tools, model and automated checks. They live in
[prompts.py](../src/complianceops/prompts.py) and are selected with `PROMPT_STRATEGY`.

| Strategy | What it adds |
|---|---|
| `minimal` | One generic sentence: "summarize the assessment records". No rules. |
| `guardrailed` | Full safety policy: authoritative findings, untrusted evidence and user text, no certification or execution, cite exact IDs. |
| `structured` | Guardrailed, plus a required five-section answer format (Observations, Gaps and unknowns, Recommendations, Approvals, Limitations) and an instruction to copy IDs exactly. |
| `few_shot` | Structured, plus one short synthetic worked example of the format. |

Only final user-facing answers (the monolith and the supervisor) get the format contract; intermediate
specialist reports keep the safety policy only.

## Results

Live run, `gpt-4o-mini`, temperature 0, 12 cases x 2 architectures = 24 runs per strategy.
Raw data: [prompt-compare-live.json](../data/prompt-compare-live.json); table:
[phase3-prompt-comparison-results.md](./phase3-prompt-comparison-results.md).

| Strategy | All 9 checks pass | Citation presence | Required sections | Avg latency (s) | Total tokens | Avg answer length (chars) |
|---|---|---|---|---|---|---|
| minimal | 17% | 17% | 0% | 8.1 | 109,238 | 1,604 |
| guardrailed | 79% | 79% | 0% | 12.3 | 200,409 | 2,113 |
| structured | 96% | 96% | 100% | 9.9 | 191,119 | 945 |
| few_shot | **100%** | **100%** | 100% | 10.1 | 191,149 | 663 |

Every difference came from one check, `citation_presence`. All strategies passed the other eight
checks (finding statuses, proposal scope, rejected evidence, tool coverage, capability scope,
proposal safety, draft contract, and false-execution-claim red flags) on every run.

## How behavior changes with better prompts

- **minimal -> guardrailed:** citation presence jumps from 17% to 79%. The minimal answers were
  accurate and readable but described controls in prose ("Access Control (AC-01)... evidence was
  rejected") without quoting the policy ID or the rejected evidence IDs. Naming the requirement to
  cite exact IDs is the biggest single improvement.
- **guardrailed -> structured:** fixed section headings (0% -> 100% followed) and a "copy IDs
  exactly" rule raise citations to 96% and shrink answers by more than half (2,113 -> 945 characters).
  Without a format, the model chose its own layout per run.
- **structured -> few_shot:** the worked example fixed the remaining failure and made answers
  tighter again (945 -> 663 characters). Because the longer prompt is offset by shorter outputs,
  total token use is essentially unchanged.

## New failure modes introduced or exposed

| Failure mode | Seen in | Detail |
|---|---|---|
| **Missing identifiers** | minimal (20 of 24 runs), guardrailed (5), structured (1) | Correct meaning, but policy or evidence IDs omitted, so the answer is not traceable. In guardrailed this clustered in the larger cases (`full-readiness`, `request-injection`) and in multi-agent runs, where the supervisor summarizes specialist reports and drops IDs. |
| **Format drift** | minimal, guardrailed | No consistent structure, so answers are hard to compare or scan. |
| **Verbosity and cost** | guardrailed | Longest answers and highest latency (12.3 s) and tokens; guidance without format makes the model over-explain. |
| **Residual identifier loss in multi-agent** | structured | The single remaining failure was a supervisor answer in `request-injection/multi_agent` that omitted two policy IDs. |
| **Example anchoring** (a risk specific to few-shot) | checked, **not observed** | No answer contained the example's placeholder IDs. |
| **Prompt injection** | all strategies | Not observed: no answer claimed anything was certified, executed or published. This is a weak signal only; see limitations. |

## Selected default: `few_shot`

`few_shot` is now the default (`DEFAULT_PROMPT_STRATEGY` and `PROMPT_STRATEGY` in `.env`).

**Justification**

1. It was the only strategy with 100% on every check, including citation presence, which is the
   property the compliance lead most needs (every claim traceable to a control, policy and
   evidence ID).
2. It costs no more than `structured`: tokens are within 0.02% and latency within the noise, because
   shorter answers offset the longer prompt.
3. Its answers are the most compact and always follow the same five sections, which makes review and
   automated checking easier.
4. The strategies that do not enforce structure (`minimal`, `guardrailed`) either dropped
   identifiers often or produced verbose, inconsistent answers.

**Fallback:** `structured` is nearly as good (96%) and has no example to maintain. Switch to it with
`PROMPT_STRATEGY=structured` if the worked example ever needs to change per control family.

## Limitations of this comparison

- **One run per strategy at temperature 0 on 24 cases.** The `structured` vs `few_shot` gap is one
  run (1/24). That is suggestive, not statistically established. Re-run before relying on it,
  especially after changing the model.
- **One model** (`gpt-4o-mini`). Rankings may differ on other models.
- **The scorer is narrow.** `citation_presence` checks that IDs appear in the text, not that they
  support the claims. The false-execution-claim detector is a small regex. The checks do **not**
  measure semantic groundedness, calibration or true injection resistance, so human review of live
  answers is still required (rubric in [FINAL_CLASS_GUIDE.md](../FINAL_CLASS_GUIDE.md)).
- The `minimal` prompt was intentionally weak to show a floor; its poor score reflects the missing
  requirements, not model quality.

## Reproduce

```bash
python -m complianceops.prompt_compare --mode live \
  --output data/prompt-compare-live.json --report docs/phase3-prompt-comparison-results.md
python -m complianceops.prompt_compare --strategies guardrailed few_shot --architecture monolith
```

This makes paid model calls (about 96 runs, 15-20 minutes for all four strategies).
