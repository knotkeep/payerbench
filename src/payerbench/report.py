"""Read tau2 results files for PayerBench: per-task outcomes, failure reasons, transcripts.

Works on the saved results.json, so it needs no model access and no tau2 runtime state.
"""

from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parents[2] / "data"
SIM_DIR = BENCH_DIR / "simulations"
RESULTS_DIR = BENCH_DIR / "results"


def load(run: str) -> dict[str, Any]:
    """A run by name (raw under simulations/, or gzipped under results/) or by path."""
    path = Path(run)
    if not path.exists():
        raw, packed = SIM_DIR / run / "results.json", RESULTS_DIR / f"{run}.json.gz"
        path = raw if raw.exists() else packed
    elif path.is_dir():
        path = path / "results.json"
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads(path.read_text())


def why_failed(sim: dict[str, Any]) -> list[str]:
    """Human-readable reasons a simulation did not earn reward 1."""
    ri = sim.get("reward_info") or {}
    if not ri:
        err = (sim.get("info") or {}).get("error", "")
        return [f"{sim.get('termination_reason')}: {str(err)[:160]}"]
    out = []
    db = ri.get("db_check") or {}
    if db and not db.get("db_match"):
        out.append("db: final state differs from reference")
    for c in ri.get("communicate_checks") or []:
        if not c.get("met"):
            out.append(f"communicate: never said {c.get('info')!r}")
    for n in ri.get("nl_assertions") or []:
        if not n.get("met"):
            out.append(f"nl: {n.get('nl_assertion')} ({str(n.get('justification'))[:120]})")
    if not out and ri.get("reward", 0) < 1:
        out.append(f"terminated: {sim.get('termination_reason')}")
    return out


def pass_hat_k(n: int, c: int, k: int) -> float:
    """tau-bench pass^k: probability that k trials drawn without replacement all succeed."""
    return math.comb(c, k) / math.comb(n, k) if n >= k else float("nan")


def summary(data: dict[str, Any]) -> dict[str, Any]:
    by_task: dict[str, list[float]] = defaultdict(list)
    for s in data["simulations"]:
        by_task[s["task_id"]].append((s.get("reward_info") or {}).get("reward", 0.0))
    k_max = min(len(v) for v in by_task.values()) if by_task else 0
    passk = {
        k: sum(pass_hat_k(len(v), sum(r >= 1 for r in v), k) for v in by_task.values())
        / len(by_task)
        for k in range(1, k_max + 1)
    }
    by_cat: dict[str, list[float]] = defaultdict(list)
    for tid, rewards in by_task.items():
        by_cat[tid.rsplit("-", 1)[0]].extend(rewards)
    return {
        "tasks": len(by_task),
        "simulations": len(data["simulations"]),
        "pass^k": {k: round(v, 3) for k, v in passk.items()},
        "by_category": {c: round(sum(v) / len(v), 2) for c, v in sorted(by_cat.items())},
        "infra_errors": sum(
            1 for s in data["simulations"] if s.get("termination_reason") == "infrastructure_error"
        ),
    }


def transcript(sim: dict[str, Any], width: int = 220) -> str:
    lines = []
    for m in sim.get("messages") or []:
        text = str(m.get("content") or "").replace("\n", " ")[:width]
        calls = [
            f"{t['name']}({json.dumps(t.get('arguments'))})" for t in m.get("tool_calls") or []
        ]
        lines.append(f"{m['role']:>9}: {text} {' '.join(calls)}".rstrip())
    return "\n".join(lines)


def tier_metrics(data: dict[str, Any], task_ids: set[str]) -> dict[str, Any] | None:
    """pass^k and cost over the simulations whose task is in `task_ids`."""
    sims = [s for s in data["simulations"] if s["task_id"] in task_ids]
    if not sims:
        return None
    sub = summary({"simulations": sims})
    return {
        "tasks": sub["tasks"],
        "simulations": sub["simulations"],
        "pass^k": sub["pass^k"],
        "agent_cost_usd": round(sum(s.get("agent_cost") or 0 for s in sims), 2),
    }


def leaderboard(runs: dict[str, str], splits: dict[str, list[str]]) -> tuple[str, list[dict]]:
    """Markdown table and rows: one row per (agent, tier) with every task of the tier run."""
    rows = []
    for label, run in runs.items():
        data = load(run)
        for tier in ("core", "hard", "full"):
            ids = set(splits[tier])
            ran = {s["task_id"] for s in data["simulations"]} & ids
            if ran != ids:
                continue
            m = tier_metrics(data, ids)
            rows.append({"agent": label, "run": run, "tier": tier, **m})
    lines = [
        "| agent | tier | tasks | pass^1 | pass^2 | pass^3 | pass^4 | agent cost |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        pk = r["pass^k"]
        cells = [f"{pk[k]:.3f}" if k in pk else "-" for k in (1, 2, 3, 4)]
        lines.append(
            f"| {r['agent']} | {r['tier']} | {r['tasks']} | "
            + " | ".join(cells)
            + f" | ${r['agent_cost_usd']:.2f} |"
        )
    return "\n".join(lines) + "\n", rows
