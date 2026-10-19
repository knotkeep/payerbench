"""Register the PayerBench domain and task set with tau2's global registry.

Import this module before using tau2's runner or CLI entry points; registration is idempotent.
"""

from __future__ import annotations

from tau2.registry import registry

from payerbench.domain.environment import (
    DOMAIN,
    get_environment,
    get_tasks,
    get_tasks_split,
)


def register() -> None:
    if DOMAIN not in registry.get_domains():
        registry.register_domain(get_environment, DOMAIN)
    if DOMAIN not in registry.get_task_sets():
        registry.register_tasks(get_tasks, DOMAIN, get_task_splits=get_tasks_split)


register()
