"""Build the Hugging Face dataset folder (dist/hf) from the task set and the published runs.

Subsets: tasks (one row per simulated call), results (one row per simulation in the leaderboard
runs), leaderboard (one row per agent and tier). db.json, policy.md and split_tasks.json ship as
plain files. Nested structures are stored as JSON strings so every row has the same schema.

    uv run python scripts/export_hf.py
    hf upload knotkeep/payerbench dist/hf . --repo-type dataset
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# tau2 resolves its data directory on first import
os.environ.setdefault("TAU2_DATA_DIR", str(REPO / "data"))

from payerbench.domain.environment import (  # noqa: E402
    DB_PATH,
    POLICY_PATH,
    SPLITS_PATH,
    TASKS_PATH,
)
from payerbench.report import RESULTS_DIR, load, why_failed  # noqa: E402

OUT = REPO / "dist" / "hf"
CARD = REPO / "hf" / "README.md"
LEADERBOARD = REPO / "data" / "leaderboard.json"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def task_rows(splits: dict[str, list[str]]) -> list[dict]:
    hard = set(splits["hard"])
    smoke = set(splits["smoke"])
    rows = []
    for t in json.loads(TASKS_PATH.read_text()):
        ins = t["user_scenario"]["instructions"]
        ev = t["evaluation_criteria"]
        rows.append(
            {
                "id": t["id"],
                "category": t["id"].rsplit("-", 1)[0],
                "tier": "hard" if t["id"] in hard else "core",
                "in_smoke": t["id"] in smoke,
                "persona": t["user_scenario"].get("persona"),
                "reason_for_call": ins.get("reason_for_call"),
                "known_info": ins.get("known_info"),
                "unknown_info": ins.get("unknown_info"),
                "task_instructions": ins.get("task_instructions"),
                "reward_basis": ev.get("reward_basis") or [],
                "reference_actions": json.dumps(ev.get("actions") or []),
                "communicate_info": ev.get("communicate_info") or [],
                "nl_assertions": ev.get("nl_assertions") or [],
                "initial_state": json.dumps(t.get("initial_state")),
                "task_json": json.dumps(t),
            }
        )
    return rows


def result_rows(splits: dict[str, list[str]], labels: dict[str, str]) -> list[dict]:
    hard = set(splits["hard"])
    rows = []
    for path in sorted(RESULTS_DIR.glob("*.json.gz")):
        run = path.name.removesuffix(".json.gz")
        data = load(str(path))
        info = data.get("info") or {}
        for s in data["simulations"]:
            ri = s.get("reward_info") or {}
            messages = [
                {k: m.get(k) for k in ("role", "content", "tool_calls", "turn_idx")}
                for m in s.get("messages") or []
            ]
            rows.append(
                {
                    "run": run,
                    "agent": labels.get(run, run),
                    "agent_llm": (info.get("agent_info") or {}).get("llm"),
                    "user_llm": (info.get("user_info") or {}).get("llm"),
                    "task_id": s["task_id"],
                    "category": s["task_id"].rsplit("-", 1)[0],
                    "tier": "hard" if s["task_id"] in hard else "core",
                    "trial": s.get("trial"),
                    "reward": ri.get("reward", 0.0),
                    "termination_reason": s.get("termination_reason"),
                    "failure_reasons": why_failed(s) if ri.get("reward", 0.0) < 1 else [],
                    "agent_cost_usd": s.get("agent_cost"),
                    "duration_s": s.get("duration"),
                    "agent_turns": sum(m["role"] == "assistant" for m in messages),
                    "messages": json.dumps(messages, ensure_ascii=False),
                }
            )
    return rows


def leaderboard_rows(board: list[dict]) -> list[dict]:
    return [
        {
            "agent": r["agent"],
            "run": r["run"],
            "tier": r["tier"],
            "tasks": r["tasks"],
            "simulations": r["simulations"],
            **{f"pass_{k}": r["pass^k"].get(str(k)) for k in (1, 2, 3, 4)},
            "agent_cost_usd": r["agent_cost_usd"],
        }
        for r in board
    ]


def main() -> None:
    splits = json.loads(SPLITS_PATH.read_text())
    board = json.loads(LEADERBOARD.read_text())
    labels = {r["run"]: r["agent"] for r in board}
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    _write_jsonl(OUT / "tasks.jsonl", task_rows(splits))
    _write_jsonl(OUT / "results.jsonl", result_rows(splits, labels))
    _write_jsonl(OUT / "leaderboard.jsonl", leaderboard_rows(board))
    for src in (DB_PATH, SPLITS_PATH, POLICY_PATH, CARD):
        shutil.copy(src, OUT / src.name)
    for p in sorted(OUT.iterdir()):
        print(f"{p.stat().st_size / 1e6:8.2f} MB  {p.relative_to(REPO)}")


if __name__ == "__main__":
    main()
