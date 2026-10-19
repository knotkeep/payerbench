"""Build the PayerBench tau2 database (db.json) from the seeded synthetic world.

The world in payerbench.world is a seeded synthetic health plan. This module reshapes it for
tau2: structured addresses, ten-digit phones, denial dates on denied claims, and a set of primary
care providers (the world has none, and PCP changes need them). Everything is derived with fixed
seeds, so the file is reproducible: `uv run python -m payerbench.build_db`.
"""

from __future__ import annotations

import random
import re
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

from payerbench.domain.data_model import (
    Address,
    Claim,
    Member,
    PayerDB,
    PriorAuth,
    Provider,
)
from payerbench.domain.tools import TODAY, normalize_street
from payerbench.world import DENIAL_REASONS, PLAN_DOCUMENT, world

SEED = 20261013
DATA_DIR = Path(__file__).parent / "domain" / "data"
DB_PATH = DATA_DIR / "db.json"
PCP_ZIPS = ["84101", "84102", "84105", "84111", "84115", "84121"]


def _address(raw: str, fake: Faker) -> Address:
    """Parse 'street, city, ST 12345'; replace military or unparseable addresses."""
    m = re.fullmatch(r"(.+), (.+), ([A-Z]{2}) (\d{5})", raw)
    if m and m.group(3) not in {"AA", "AE", "AP"}:
        street, city, state, zip_code = m.groups()
    else:
        street, city = fake.street_address(), fake.city()
        state, zip_code = fake.state_abbr(include_territories=False), fake.zipcode()
    return Address(
        street=normalize_street(street), city=city.upper(), state=state, zip_code=zip_code
    )


def _dob(dob: date, plan: str, rng: random.Random) -> date:
    """Medicare Advantage members are 65 or older (the world draws ages and plans independently)."""
    age = (TODAY - dob).days // 365
    if plan.startswith("Medicare") and age < 65:
        return dob.replace(year=TODAY.year - rng.randint(66, 88))
    return dob


def build() -> PayerDB:
    w = world()
    rng = random.Random(SEED)
    fake = Faker("en_US")
    fake.seed_instance(SEED)

    members = {}
    for mid, m in w.members.items():
        members[mid] = Member(
            member_id=mid,
            first_name=m.first_name,
            last_name=m.last_name,
            dob=_dob(m.dob, m.plan, rng).isoformat(),
            plan=m.plan,
            active=m.active,
            effective_date=m.effective_date.isoformat(),
            term_date=m.term_date.isoformat() if m.term_date else None,
            pcp_name=m.pcp,
            pcp_npi=None,
            deductible_total=m.deductible_total,
            deductible_met=m.deductible_met,
            oop_max=m.oop_max,
            oop_met=m.oop_met,
            address=_address(m.address, fake),
            phone="801" + "".join(str(rng.randint(0, 9)) for _ in range(7)),
        )

    claims = {}
    for cid, c in sorted(w.claims.items()):
        denial_date = None
        if c.status == "denied":
            denial_date = (c.service_date + timedelta(days=rng.randint(14, 30))).isoformat()
        claims[cid] = Claim(
            claim_id=cid,
            member_id=c.member_id,
            service_date=c.service_date.isoformat(),
            provider=c.provider,
            cpt=c.cpt,
            description=c.description,
            billed=c.billed,
            allowed=c.allowed,
            plan_paid=c.plan_paid,
            member_owes=c.member_owes,
            status=c.status,
            denial_code=c.denial_code,
            denial_reason=DENIAL_REASONS.get(c.denial_code) if c.denial_code else None,
            denial_date=denial_date,
        )

    prior_auths = {
        aid: PriorAuth(
            auth_id=aid,
            member_id=p.member_id,
            service=p.service,
            status=p.status,
            requested=p.requested.isoformat(),
            decision=p.decision.isoformat() if p.decision else None,
            notes=p.notes,
        )
        for aid, p in sorted(w.prior_auths.items())
    }

    providers = {
        p.npi: Provider(
            npi=p.npi,
            name=p.name,
            specialty=p.specialty,
            zip_code=p.zip_code,
            in_network=p.in_network,
            accepting_new=p.accepting_new,
        )
        for p in w.providers
    }
    # Primary care: at least one accepting in-network PCP per ZIP, plus some that are not.
    for i, zip_code in enumerate(PCP_ZIPS * 2):
        npi = str(1_900_000_000 + rng.randint(0, 99_999_999))
        providers[npi] = Provider(
            npi=npi,
            name=f"Dr. {fake.first_name()} {fake.last_name()}",
            specialty="primary care",
            zip_code=zip_code,
            in_network=i < len(PCP_ZIPS) or rng.random() > 0.5,
            accepting_new=i < len(PCP_ZIPS) or rng.random() > 0.5,
        )

    return PayerDB(
        members=members,
        claims=claims,
        prior_auths=prior_auths,
        providers=dict(sorted(providers.items())),
        plan_document=dict(PLAN_DOCUMENT),
    )


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = build()
    db.dump(str(DB_PATH))
    print(
        f"{DB_PATH}: {len(db.members)} members, {len(db.claims)} claims, "
        f"{len(db.prior_auths)} prior auths, {len(db.providers)} providers"
    )


if __name__ == "__main__":
    main()
