"""PayerBench database for the tau2 (τ²-bench) domain.

Every write tool records an outcome here, and a task passes its DB check only if the final state
hashes equal to the state produced by replaying the task's reference actions. Values that a
correct agent could legitimately phrase differently (free-text reasons, address formatting) are
stored as codes or normalized forms, so the hash measures what was done, not how it was worded.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from tau2.environment.db import DB

ClaimStatus = Literal["paid", "denied", "pending", "adjusted"]
AuthStatus = Literal["approved", "denied", "pending", "not_required"]
AppealReason = Literal[
    "disagree_medical_necessity",
    "prior_auth_was_obtained",
    "billing_or_coding_error",
    "provider_should_be_in_network",
    "other",
]
CardReason = Literal["lost", "damaged", "never_received"]


class Address(BaseModel):
    street: str = Field(description="Street line, normalized to upper case with single spaces")
    city: str = Field(description="City, upper case")
    state: str = Field(description="Two-letter state code")
    zip_code: str = Field(description="Five-digit ZIP code")


class Member(BaseModel):
    member_id: str
    first_name: str
    last_name: str
    dob: str = Field(description="Date of birth, YYYY-MM-DD")
    plan: str
    active: bool
    effective_date: str
    term_date: str | None
    pcp_name: str
    pcp_npi: str | None
    pcp_effective_date: str | None = None
    deductible_total: int
    deductible_met: int
    oop_max: int
    oop_met: int
    address: Address
    phone: str = Field(description="Ten digits, no punctuation")
    id_card_orders: list[IdCardOrder] = Field(default_factory=list)


class IdCardOrder(BaseModel):
    reason: CardReason
    ship_to: Address


class Claim(BaseModel):
    claim_id: str
    member_id: str
    service_date: str
    provider: str
    cpt: str
    description: str
    billed: float
    allowed: float
    plan_paid: float
    member_owes: float
    status: ClaimStatus
    denial_code: str | None = None
    denial_reason: str | None = None
    denial_date: str | None = None


class PriorAuth(BaseModel):
    auth_id: str
    member_id: str
    service: str
    status: AuthStatus
    requested: str
    decision: str | None
    notes: str = ""
    expedited: bool = False


class Provider(BaseModel):
    npi: str
    name: str
    specialty: str
    zip_code: str
    in_network: bool
    accepting_new: bool


class Appeal(BaseModel):
    appeal_id: str
    claim_id: str
    member_id: str
    reason: AppealReason
    status: Literal["submitted"] = "submitted"


class Transfer(BaseModel):
    member_id: str | None = Field(description="Verified member on the call, or null")


class CallerLetter(BaseModel):
    title: str
    body: str


class CallerData(BaseModel):
    """What the caller has at hand: an insurance card, letters from the plan, provider details.

    Lives inside PayerDB because tau2 points the agent's and the caller's toolkits at one shared
    database once a task sets caller data (Environment.set_state).
    """

    insurance_card: dict[str, str] | None = None
    letters: list[CallerLetter] = Field(default_factory=list)
    provider_office: dict[str, str] | None = Field(
        default=None, description="For callers from a provider office: practice name and NPI"
    )


class PayerDB(DB):
    """Members, claims, prior authorizations, providers, the caller's documents, and the outcomes
    of this call."""

    members: dict[str, Member]
    claims: dict[str, Claim]
    prior_auths: dict[str, PriorAuth]
    providers: dict[str, Provider]
    plan_document: dict[str, str] = Field(description="Benefits document sections by title")
    appeals: dict[str, Appeal] = Field(default_factory=dict)
    verified_members: list[str] = Field(
        default_factory=list, description="Members whose identity was verified on this call"
    )
    transfers: list[Transfer] = Field(default_factory=list)
    caller: CallerData = Field(default_factory=CallerData)


Member.model_rebuild()
