"""tau2 environment and task loading for the PayerBench domain."""

from __future__ import annotations

import json
from pathlib import Path

from tau2.data_model.tasks import Task
from tau2.environment.environment import Environment

from payerbench.domain.data_model import PayerDB
from payerbench.domain.tools import PayerTools
from payerbench.domain.user_tools import CallerTools

DOMAIN = "payerbench"
HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "db.json"
TASKS_PATH = HERE / "data" / "tasks.json"
SPLITS_PATH = HERE / "data" / "split_tasks.json"
POLICY_PATH = HERE / "policy.md"


def get_environment(
    db: PayerDB | None = None, user_db: PayerDB | None = None, solo_mode: bool = False
) -> Environment:
    """Agent and caller toolkits share one database, as tau2's set_state expects."""
    if solo_mode:
        raise ValueError(
            "PayerBench has no solo mode: the caller holds information the agent needs"
        )
    shared = db or user_db or PayerDB.load(str(DB_PATH))
    return Environment(
        domain_name=DOMAIN,
        policy=POLICY_PATH.read_text(),
        tools=PayerTools(shared),
        user_tools=CallerTools(shared),
    )


def get_tasks(task_split_name: str | None = None) -> list[Task]:
    tasks = [Task.model_validate(t) for t in json.loads(TASKS_PATH.read_text())]
    if task_split_name is None:
        return tasks
    splits = get_tasks_split()
    if task_split_name not in splits:
        raise ValueError(f"Unknown split {task_split_name}; choose from {list(splits)}")
    keep = set(splits[task_split_name])
    return [t for t in tasks if t.id in keep]


def get_tasks_split() -> dict[str, list[str]]:
    return json.loads(SPLITS_PATH.read_text())
