# PayerBench

A [τ²-bench](https://github.com/sierra-research/tau2-bench) domain for health-plan member
services: a written policy, a synthetic plan database, 15 agent tools, 3 caller tools and 104
simulated calls. An LLM plays the member (or a provider office) with a hidden goal; the agent under
test follows the policy and calls tools; the call is scored on what the database looks like at the
end.

PayerBench plugs into τ²-bench v1.0.1 through its registry, so it inherits τ²'s user simulator,
orchestrator, outcome-based scoring and pass^k. A task passes only if the final database matches
the reference state *and* the agent said the required facts *and*, where needed, an LLM judge
confirms a written assertion.

## Leaderboard

pass^k is the share of tasks solved in all k of k attempts (4 trials per task, October 2026).

| agent | tier | tasks | pass^1 | pass^2 | pass^3 | pass^4 | agent cost |
|---|---|---|---|---|---|---|---|
| Claude Haiku 5.5 | hard | 31 | 0.992 | 0.984 | 0.976 | 0.968 | $0.62 |
| Claude Sonnet 5.5 | hard | 31 | 0.984 | 0.968 | 0.952 | 0.935 | $12.10 |
| Gemma 4 31B 8-bit (local) | core | 73 | 0.979 | 0.959 | 0.938 | 0.918 | $0 |
| Gemma 4 31B 8-bit (local) | hard | 31 | 0.798 | 0.790 | 0.782 | 0.774 | $0 |
| Gemma 4 31B 8-bit (local) | full | 104 | 0.925 | 0.909 | 0.892 | 0.875 | $0 |
| Qwen3.8-Flash-Next 4-bit (local) | core | 73 | 0.846 | 0.765 | 0.705 | 0.658 | $0 |
| Qwen3.8-Flash-Next 4-bit (local) | hard | 31 | 0.887 | 0.806 | 0.750 | 0.710 | $0 |
| Qwen3.8-Flash-Next 4-bit (local) | full | 104 | 0.858 | 0.777 | 0.719 | 0.673 | $0 |

- **Agents:** τ²'s standard `llm_agent` (policy as system prompt, tools, one action per turn).
  Local models were served by oMLX on a Mac Studio (M5 Ultra); Claude models ran over the
  Anthropic API with default settings (thinking on, no sampling parameters).
- **Simulated caller:** Gemma 4 31B 8-bit at temperature 0.7, the same for every agent.
- **Judge for written assertions:** Gemma 4 31B 8-bit at temperature 0. It decides only the 32
  tasks that carry written assertions.
- The Claude models ran only the hard tier: Gemma already scores 0.979 on core.

Full transcripts of all four runs are in `data/results/`.

### What the runs show

- **The Claude models made no genuine errors on the hard tier.** Every one of their three
  failures in 248 calls was the simulated caller's mistake. v1 separates local models from each
  other and from the frontier; it does not separate Haiku 5.5 from Sonnet 5.5.
- **Gemma's failures are one blind spot, three ways.** It failed every attempt (24 of 24) at the
  three tasks where the right move is to check the record before acting: a letter about
  *someone else's* claim (it explained the claim), a parent asking about a 23-year-old "child"
  (it verified the adult and read out their claims), and a terminated member asking for a card
  (it ordered one).
- **Qwen's weakness is reliability, not reasoning.** It beats Gemma on those record checks but
  drops from 0.858 to 0.673 between pass^1 and pass^4, and it transferred all 12 grievance calls
  without verifying the caller first, which the policy requires.

Hard tier by call type (passes out of attempts):

| call type | Gemma 4 31B | Qwen3.8-Flash-Next | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|---|---|
| adult_child | **0/8** | 4/8 | 8/8 | 8/8 |
| misdelivered_letter | **0/8** | 7/8 | 8/8 | 8/8 |
| termed_card | **0/8** | 7/8 | 8/8 | 8/8 |
| expedite_denied | 4/4 | 1/4 | 4/4 | 4/4 |
| dob_shorthand | 7/8 | 5/8 | 7/8 | 7/8 |
| card_after_move | 12/12 | 11/12 | 12/12 | 12/12 |
| spouse_address | 8/8 | 7/8 | 8/8 | 8/8 |
| provider_deductible | 8/8 | 8/8 | 8/8 | 7/8 |
| appeal_by_description, oop_remaining, pcp_unavailable, spanish_multi, total_owed | all | all | all | all |

## What is in the domain

| piece | PayerBench |
|---|---|
| Policy | `policy.md`: identity verification, one member per call, provider-office rules, confirmation before changes, appeal window and reason codes, PCP rules, expedited review, exactly when to transfer |
| Database | 40 members, 102 claims, 25 prior authorizations, 42 providers, the plan document, and per-call outcomes (verifications, appeals, card orders, transfers). All synthetic. |
| Agent tools | 8 reads (find member ID, member details, claims, one claim, prior auths, benefits search, provider search, verify provider) and 7 writes (verify identity, contact info, ID card, PCP change, appeal, expedited review, transfer) |
| Caller tools | read insurance card, read letters, read practice details: some facts are only on paper, so the caller has to look (τ²'s "dual control") |
| Tasks | 104 tasks across 33 call types and six personas (plain, confused, elderly, adversarial, Spanish-speaking, provider office); 73 core, 31 hard |

Splits: `smoke` (33 tasks), `core` (73), `hard` (31), `full` (104).

**Scoring.** τ² replays each task's reference actions on a fresh copy of the database and compares
hashes with the agent's final database, so any correct path passes. Three design choices make
that hash meaningful here:

- **Identity verification is a recorded write.** Verifying the wrong person (a spouse, an adult
  child) changes the database and fails the task, so privacy is scored by outcome.
- **Free text is stored as codes.** Appeals store a reason code, addresses are normalized, phones
  are digits only, so the hash measures what was done rather than how it was worded.
- **Facts the agent must say are language-neutral** (amounts as digits, plan names, appeal IDs).
  Statuses and refusals go to the LLM judge instead.

**The hard tier** adds ordering (update the address *before* ordering a card, since it ships to
the address on file), arithmetic (remaining out-of-pocket, total owed across claims), choosing
among constrained options (the requested PCP is full or out of network; find the one eligible
alternative), partial refusals (change my address and my spouse's; a provider office asking for
the deductible) and three record checks (whose claim is this, is this "child" an adult, is this
member still covered).

## Run it

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                       # installs tau2-bench v1.0.1 from Sierra's GitHub tag
uv run pytest                 # every reference action replays; the database rebuilds byte-for-byte

# a local model on any OpenAI-compatible endpoint
export PAYERBENCH_LOCAL_BASE_URL=http://127.0.0.1:8080/v1
uv run payerbench run --agent-llm local/<model> --user-llm local/<model> --judge-llm local/<model> \
  --split smoke --trials 1 --save-to my-run

# a hosted model (any LiteLLM model string; keys from the environment)
uv run payerbench run --agent-llm anthropic/claude-sonnet-5-5 --split hard --trials 4 --save-to hard-sonnet

uv run payerbench report my-run --show failed       # why each failure failed, with transcripts
uv run payerbench leaderboard "Mine=my-run" "Gemma 4 31B=final-gemma"
```

Model names follow LiteLLM. A `local/` prefix sends the request to
`PAYERBENCH_LOCAL_BASE_URL` (default `http://127.0.0.1:9999/v1`) as an OpenAI-compatible model.
Runs are saved under `data/simulations/<name>/`; `report` and `leaderboard` also read the published
runs in `data/results/` by name (`final-gemma`, `final-qwen3.8`, `hard-claude-haiku-5-5`,
`hard-claude-sonnet-5-5`).

For results comparable with the table above, use a strong, fixed caller and judge for every agent
you compare. A rerun with different caller or judge models is a new baseline.

The database and tasks are generated deterministically and checked in:

```bash
uv run python -m payerbench.build_db    # src/payerbench/domain/data/db.json
uv run python -m payerbench.tasks       # tasks.json, split_tasks.json
```

## How the benchmark was checked

Nine problems were found by reading the transcripts behind failures, before any number was
reported. Each would otherwise have been counted against an agent:

| found in | problem | fix |
|---|---|---|
| first smoke run | τ² points the agent's and the caller's toolkits at one database once a task sets caller data, so agent tools ran against the caller's documents | caller documents live inside the shared database |
| first smoke run | the local judge wraps JSON in a code fence; τ² parses it raw and errored | strip the fence before τ² parses it |
| first smoke run | postponed annotations hid the tool parameter types from τ²'s schema builder | no `from __future__ import annotations` in tool modules |
| second run | callers asked for a human or accepted an offered transfer in tasks where the reference had none | the policy lists exactly when to transfer; callers decline unless the task is a transfer |
| second run | a caller asked "why did my coverage end", which the records cannot answer | the policy says records show dates, not reasons |
| full run | a Spanish-speaking caller failed for "pendiente" | statuses checked by the judge; required facts are language-neutral |
| hard run | an elderly caller read "M... SYNTH... 000007" and the tool required the hyphens | tools accept IDs without punctuation, as a real system would |
| hard run | an "adult child" task picked an 8-year-old | adult-child tasks use members 18 and over |
| Qwen run | Qwen sends ZIP codes as JSON numbers and the tool crashed on them | tools convert identifiers to text and pad ZIPs |

## Caveats

- **Saturated for frontier models.** v1 cannot rank Haiku 5.5 against Sonnet 5.5. A v2 needs
  longer calls with several dependent requests, rules that interact, arithmetic over many records,
  and callers who change their story mid-call.
- **One simulated caller, one judge, both Gemma.** A cross-check with a Qwen caller showed Gemma's
  misses were simulator errors rather than leniency, but a stronger, independent caller would be a
  better reference.
- **The task author wrote the policy and the tasks.** Generated tasks share phrasings, and the
  hard tier was designed after seeing where Gemma succeeded. A held-out, hand-written task set is
  the honest next check.
- **Local results depend on the serving stack.** Engine, engine version and quantization change
  outputs; report them with any local result.
- **Four trials.** Per-category counts are small; a single flip moves a hard-tier row by 3 to 12
  points.

## Layout

```
src/payerbench/
  domain/            policy.md, data model, agent tools, caller tools, tau2 environment
  domain/data/       db.json, tasks.json, split_tasks.json
  world.py           seeded synthetic health plan the database is built from
  build_db.py        world -> db.json
  tasks.py           db.json -> tasks.json, split_tasks.json
  run.py, report.py  run through tau2's runner; read saved results
  cli.py             payerbench run | report | leaderboard
data/
  results/           transcripts of the leaderboard runs (tau2 results, gzipped)
  tau2/              tau2-bench user-simulator prompts (see THIRD_PARTY_NOTICES.md)
```

## License

MIT. The user-simulator prompts under `data/tau2/` are from tau2-bench (MIT, Sierra Research);
see `THIRD_PARTY_NOTICES.md`. All member, claim and provider records are synthetic.
