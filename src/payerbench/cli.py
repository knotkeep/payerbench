"""Command line: run agents against simulated callers, read results, build the leaderboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    help="PayerBench: a tau2-bench domain for health-plan member services.",
    no_args_is_help=True,
)
console = Console()


@app.command("run")
def run_cmd(
    agent_llm: str = typer.Option("local/gemma-4-31b-it-4bit", help="Agent under test"),
    user_llm: str = typer.Option("local/gemma-4-31b-it-4bit", help="Simulated caller"),
    judge_llm: str = typer.Option("local/gemma-4-31b-it-4bit", help="NL-assertion judge"),
    split: str = typer.Option("smoke", help="Task split: smoke, core, hard or full"),
    tasks: str | None = typer.Option(None, help="Comma-separated task IDs (overrides split)"),
    trials: int = typer.Option(1, help="Trials per task (pass^k needs k trials)"),
    concurrency: int = typer.Option(2, help="Simulations in parallel"),
    user_temperature: float = typer.Option(0.7, help="Caller variety across trials"),
    save_to: str | None = typer.Option(None, help="Run name under data/simulations"),
    agent_thinking: str | None = typer.Option(
        None, help='Claude agents: thinking config as JSON, e.g. \'{"type": "disabled"}\''
    ),
) -> None:
    """Run the agent against simulated callers and report pass^k."""
    from payerbench.run import run, summarize

    results = run(
        agent_llm,
        user_llm=user_llm,
        judge_llm=judge_llm,
        split=split,
        task_ids=tasks.split(",") if tasks else None,
        trials=trials,
        concurrency=concurrency,
        user_temperature=user_temperature,
        save_to=save_to,
        agent_thinking=json.loads(agent_thinking) if agent_thinking else None,
    )
    console.print_json(json.dumps(summarize(results)))


@app.command("report")
def report_cmd(
    run: str = typer.Argument(..., help="Run name (data/simulations or data/results), or a path"),
    show: str | None = typer.Option(None, help="Print transcripts: 'failed' or a task ID"),
) -> None:
    """pass^k, per-category reward, and why each failed simulation failed."""
    from payerbench.report import load, summary, transcript, why_failed

    data = load(run)
    console.print_json(json.dumps(summary(data)))
    for s in sorted(data["simulations"], key=lambda s: (s["task_id"], s.get("trial", 0))):
        reward = (s.get("reward_info") or {}).get("reward", 0.0)
        if reward >= 1 and show != s["task_id"]:
            continue
        console.print(f"[bold]{s['task_id']}[/bold] trial {s.get('trial', 0)} reward {reward}")
        for r in why_failed(s):
            console.print(f"  - {r}", markup=False)
        if show in ("failed", s["task_id"]):
            console.print(transcript(s), markup=False)


@app.command("leaderboard")
def leaderboard_cmd(
    runs: Annotated[
        list[str], typer.Argument(help="label=run pairs, e.g. 'Gemma 4 31B=final-gemma'")
    ],
    out: str = typer.Option("data/leaderboard", help="Writes <out>.md and <out>.json"),
) -> None:
    """pass^k by tier for several runs, from saved results (no model calls)."""
    from payerbench.domain.environment import SPLITS_PATH
    from payerbench.report import leaderboard

    pairs = dict(r.split("=", 1) for r in runs)
    table, rows = leaderboard(pairs, json.loads(SPLITS_PATH.read_text()))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(f"{out}.md").write_text(table)
    Path(f"{out}.json").write_text(json.dumps(rows, indent=1) + "\n")
    console.print(table, markup=False)


if __name__ == "__main__":
    app()
