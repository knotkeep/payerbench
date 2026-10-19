"""PayerBench tau2 domain: database, tools, and task-set integrity (no model calls)."""

from __future__ import annotations

import json

import pytest

from payerbench import register  # noqa: F401
from payerbench.build_db import build
from payerbench.domain.data_model import PayerDB
from payerbench.domain.environment import (
    DB_PATH,
    SPLITS_PATH,
    TASKS_PATH,
    get_environment,
    get_tasks,
)
from payerbench.domain.tools import PayerTools
from payerbench.tasks import build as build_tasks

TASKS = json.loads(TASKS_PATH.read_text())


def _fresh() -> PayerTools:
    return PayerTools(PayerDB.load(str(DB_PATH)))


def test_db_and_tasks_are_reproducible():
    assert build().get_hash() == PayerDB.load(str(DB_PATH)).get_hash()
    assert build_tasks(PayerDB.load(str(DB_PATH))) == TASKS


def test_tasks_load_through_tau2_and_ids_are_unique():
    tasks = get_tasks()
    assert len(tasks) == len(TASKS) >= 60
    assert len({t.id for t in tasks}) == len(tasks)
    splits = json.loads(SPLITS_PATH.read_text())
    assert set(splits["smoke"]) <= {t.id for t in tasks}


@pytest.mark.parametrize("task", TASKS, ids=[t["id"] for t in TASKS])
def test_reference_actions_replay_without_error(task):
    tools = _fresh()
    before = tools.db.get_hash()
    for a in task["evaluation_criteria"]["actions"]:
        result = getattr(tools, a["name"])(**a["arguments"])
        if a["name"] == "verify_identity":
            assert result["verified"], task["id"]
    writes = [a for a in task["evaluation_criteria"]["actions"] if a["name"] != "find_member_id"]
    assert (tools.db.get_hash() != before) == bool(writes), task["id"]


def test_communicate_tokens_survive_tau2_matching():
    for t in TASKS:
        for s in t["evaluation_criteria"]["communicate_info"]:
            assert "," not in s and s.strip() == s and s, (t["id"], s)


def test_privacy_tasks_name_two_different_members():
    for t in TASKS:
        if t["id"].startswith("other_member"):
            known = t["user_scenario"]["instructions"]["known_info"]
            ids = {w.strip(".,") for w in known.split() if w.startswith("M-SYNTH-")}
            assert len(ids) == 2, t["id"]


def test_tools_enforce_data_rules():
    tools = _fresh()
    db = tools.db
    paid = next(c for c in db.claims.values() if c.status == "paid")
    with pytest.raises(ValueError, match="only denied"):
        tools.file_appeal(paid.claim_id, "other")
    specialist = next(p for p in db.providers.values() if p.specialty != "primary care")
    with pytest.raises(ValueError, match="primary care"):
        tools.change_pcp(next(iter(db.members)), specialist.npi)
    m = next(iter(db.members.values()))
    assert tools.verify_identity(m.member_id, "1900-01-01") == {"verified": False}
    assert db.verified_members == []
    tools.update_contact_info(m.member_id, phone="(801) 555-0100")
    assert db.members[m.member_id].phone == "8015550100"


def test_environment_builds_with_policy_and_caller_tools():
    env = get_environment()
    assert "verify_identity" in {t.name for t in env.get_tools()}
    assert "read_insurance_card" in {t.name for t in env.get_user_tools()}
    assert "180 days" in env.get_policy()


def test_caller_data_and_agent_tools_share_state_after_tau2_set_state():
    """tau2 re-points both toolkits at one database when a task sets caller data."""
    task = next(t for t in get_tasks() if t.initial_state and t.initial_state.initialization_data)
    env = get_environment()
    env.set_state(task.initial_state.initialization_data, None, [])
    assert env.tools.db is env.user_tools.db
    caller = env.user_tools.db.caller
    assert caller.insurance_card or caller.letters or caller.provider_office
    m = next(iter(env.tools.db.members.values()))
    assert env.tools.verify_identity(m.member_id, m.dob)["verified"]


def test_hard_tasks_have_the_intended_trap():
    db = PayerDB.load(str(DB_PATH))
    by_id = {t["id"]: t for t in TASKS}
    for tid, t in by_id.items():
        cat = tid.rsplit("-", 1)[0]
        acts = t["evaluation_criteria"]["actions"]
        if cat == "misdelivered_letter":
            caller = acts[0]["arguments"]["member_id"]
            letters = t["initial_state"]["initialization_data"]["user_data"]["caller"]["letters"]
            cid = letters[0]["body"].split()[1]
            assert db.claims[cid].member_id != caller, tid
        if cat == "card_after_move":
            assert [a["name"] for a in acts] == [
                "verify_identity",
                "update_contact_info",
                "order_id_card",
            ]
        if cat == "pcp_unavailable":
            wanted = t["user_scenario"]["instructions"]["known_info"]
            alt = db.providers[acts[1]["arguments"]["npi"]]
            assert alt.name not in wanted and alt.in_network and alt.accepting_new, tid
        if cat in {"adult_child"}:
            assert acts == [], tid


def test_tools_accept_numbers_for_text_identifiers():
    tools = _fresh()
    m = next(m for m in tools.db.members.values() if m.active)
    tools.update_contact_info(m.member_id, "77 Birch Ln", "Sandy", "UT", 84070)
    assert tools.db.members[m.member_id].address.zip_code == "84070"
    tools.update_contact_info(m.member_id, "1 Main St", "Boston", "MA", 2108)
    assert tools.db.members[m.member_id].address.zip_code == "02108"
    tools.update_contact_info(m.member_id, phone=8015550100)
    assert tools.db.members[m.member_id].phone == "8015550100"
    npi = next(p.npi for p in tools.db.providers.values())
    assert tools.verify_provider(int(npi)).npi == npi
