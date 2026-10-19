"""Run PayerBench through tau2's runner and summarize pass^k.

Model names follow LiteLLM, plus a `local/` prefix for models on the Mac's OpenAI-compatible
endpoint (PAYERBENCH_LOCAL_BASE_URL, default http://127.0.0.1:9999/v1):

    local/gemma-4-31b-it-4bit        -> openai/gemma-4-31b-it-4bit at PAYERBENCH_LOCAL_BASE_URL
    anthropic/claude-sonnet-5        -> Anthropic API (ANTHROPIC_API_KEY)

tau2 resolves its data directory when first imported, so TAU2_DATA_DIR is set before any tau2
import; simulation files land in data/simulations/.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BENCH_DATA = REPO / "data"
LOCAL_BASE_URL = os.getenv("PAYERBENCH_LOCAL_BASE_URL", "http://127.0.0.1:9999/v1")


def llm(
    name: str, temperature: float, max_tokens: int = 2048, thinking: dict | None = None
) -> tuple[str, dict[str, Any]]:
    """LiteLLM model string and arguments for a model name.

    Current Claude models reject sampling parameters, so no temperature is sent for them;
    `thinking` passes through to the Anthropic API (for example {"type": "disabled"}).
    """
    if name.startswith("anthropic/"):
        args: dict[str, Any] = {"max_tokens": max(max_tokens, 8192)}
        if thinking is not None:
            args["thinking"] = thinking
        return name, args
    args = {"temperature": temperature, "max_tokens": max_tokens}
    if name.startswith("local/"):
        args |= {"api_base": LOCAL_BASE_URL, "api_key": "local"}
        return "openai/" + name.removeprefix("local/"), args
    return name, args


def _setup(judge: str) -> None:
    BENCH_DATA.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TAU2_DATA_DIR", str(BENCH_DATA))
    from tau2.evaluator import evaluator_nl_assertions

    from payerbench import register  # noqa: F401  (registers the domain)

    model, args = llm(judge, temperature=0.0)
    evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS = model
    evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS_ARGS = args
    if not getattr(evaluator_nl_assertions.generate, "_unfenced", False):
        evaluator_nl_assertions.generate = _unfenced(evaluator_nl_assertions.generate)


def _unfenced(generate: Any) -> Any:
    """Wrap tau2's generate so a judge reply in a ```json fence parses as plain JSON.

    tau2 passes the judge's raw reply to json.loads; local models often fence their JSON.
    """
    import re

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        msg = generate(*args, **kwargs)
        text = msg.content or ""
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
        if fenced:
            msg.content = fenced.group(1)
        return msg

    wrapped._unfenced = True  # type: ignore[attr-defined]
    return wrapped


def run(
    agent_llm: str,
    user_llm: str = "local/gemma-4-31b-it-4bit",
    judge_llm: str = "local/gemma-4-31b-it-4bit",
    split: str | None = "smoke",
    task_ids: list[str] | None = None,
    trials: int = 1,
    concurrency: int = 2,
    agent_temperature: float = 0.0,
    user_temperature: float = 0.7,
    save_to: str | None = None,
    agent: str = "llm_agent",
    agent_thinking: dict | None = None,
) -> Any:
    """Run one agent configuration. Returns tau2's Results (also saved under data/simulations)."""
    _setup(judge_llm)
    from tau2 import TextRunConfig
    from tau2.runner import run_domain

    a_model, a_args = llm(agent_llm, agent_temperature, thinking=agent_thinking)
    u_model, u_args = llm(user_llm, user_temperature)
    config = TextRunConfig(
        domain="payerbench",
        task_split_name=None if task_ids else split,
        task_ids=task_ids,
        agent=agent,
        llm_agent=a_model,
        llm_args_agent=a_args,
        llm_user=u_model,
        llm_args_user=u_args,
        num_trials=trials,
        max_concurrency=concurrency,
        save_to=save_to,
        log_level="ERROR",
        auto_resume=True,
    )
    return run_domain(config)


def summarize(results: Any) -> dict[str, Any]:
    """pass^k, average reward, and per-category pass^1 from tau2 Results."""
    from tau2.metrics.agent_metrics import compute_metrics

    m = compute_metrics(results)
    by_cat: dict[str, list[float]] = {}
    for sim in results.simulations:
        cat = sim.task_id.rsplit("-", 1)[0]
        reward = sim.reward_info.reward if sim.reward_info else 0.0
        by_cat.setdefault(cat, []).append(reward)
    return {
        "avg_reward": m.avg_reward,
        "pass_hat_k": m.pass_hat_ks,
        "by_category": {c: sum(v) / len(v) for c, v in sorted(by_cat.items())},
        "n_simulations": len(results.simulations),
    }
