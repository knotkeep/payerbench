---
license: mit
language:
- en
pretty_name: PayerBench
tags:
- agents
- tool-use
- benchmark
- tau2-bench
- customer-service
- healthcare
- synthetic
size_categories:
- n<1K
configs:
- config_name: tasks
  data_files:
  - split: test
    path: tasks.jsonl
  default: true
- config_name: results
  data_files:
  - split: test
    path: results.jsonl
- config_name: leaderboard
  data_files:
  - split: test
    path: leaderboard.jsonl
---

# PayerBench

A [τ²-bench](https://github.com/sierra-research/tau2-bench) domain for health-plan member
services: a written policy, a synthetic plan database, 15 agent tools, 3 caller tools and 104
simulated calls. An LLM plays the member (or a provider office) with a hidden goal; the agent under
test follows the policy and calls tools; the call is scored on the final state of the database,
on facts the agent must state, and, for 32 tasks, on written assertions checked by an LLM judge.

Code to run it: [github.com/knotkeep/payerbench](https://github.com/knotkeep/payerbench).

## Subsets

| subset | rows | one row is |
|---|---|---|
| `tasks` | 104 | a simulated call: persona, what the caller knows, instructions, reference actions, required facts, judge assertions |
| `results` | 1,080 | one simulation from the leaderboard runs, with its reward, failure reasons and full transcript |
| `leaderboard` | 8 | pass^1 to pass^4 for one agent on one tier |

Plain files: `db.json` (the starting database), `policy.md` (the agent's policy),
`split_tasks.json` (`smoke` 33, `core` 73, `hard` 31, `full` 104).

Nested fields (`reference_actions`, `initial_state`, `task_json`, `messages`) are JSON strings.
`task_json` is the task exactly as τ²-bench loads it.

## Leaderboard (October 2026, 4 trials per task)

pass^k is the share of tasks solved in all k of k attempts.

| agent | tier | tasks | pass^1 | pass^4 | agent cost |
|---|---|---|---|---|---|
| Claude Haiku 5.5 | hard | 31 | 0.992 | 0.968 | $0.62 |
| Claude Sonnet 5.5 | hard | 31 | 0.984 | 0.935 | $12.10 |
| Gemma 4 31B 8-bit (local) | full | 104 | 0.925 | 0.875 | $0 |
| Gemma 4 31B 8-bit (local) | hard | 31 | 0.798 | 0.774 | $0 |
| Qwen3.8-Flash-Next 4-bit (local) | full | 104 | 0.858 | 0.673 | $0 |
| Qwen3.8-Flash-Next 4-bit (local) | hard | 31 | 0.887 | 0.710 | $0 |

Agents ran as τ²'s standard `llm_agent`. Every agent faced the same simulated caller (Gemma 4 31B
8-bit, temperature 0.7) and the same judge (Gemma 4 31B 8-bit, temperature 0). Local models were
served by oMLX on a Mac Studio; Claude models ran over the Anthropic API with default settings.

## Scoring

- **Database:** τ² replays the task's reference actions on a fresh copy of the database and
  compares hashes with the agent's final database. Identity verification is a recorded write, so
  verifying the wrong person fails the task. Free text is stored as codes and addresses and phones
  are normalized, so the hash measures what was done, not how it was worded.
- **Required facts:** each string in `communicate_info` must appear in an agent message (case and
  commas ignored). Only language-neutral tokens are used: amounts as digits, plan names, IDs.
- **Written assertions:** an LLM judge checks `nl_assertions` where neither of the above can see
  the failure (a refusal, a disclosure, a false approval).

## Caveats

- Saturated for frontier models: v1 does not separate Claude Haiku 5.5 from Sonnet 5.5.
- One simulated caller and one judge, both Gemma 4 31B. Results with a different caller or judge
  are a new baseline.
- The policy and tasks were written by the benchmark's author; the hard tier was designed after
  seeing where Gemma succeeded.
- Four trials per task; a single flip moves a hard-tier row by 3 to 12 points.

## Data and license

All member, claim, prior-authorization and provider records are synthetic, generated with fixed
seeds; no real person's data is included. MIT license. τ²-bench is MIT-licensed by Sierra
Research.
