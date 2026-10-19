"""Agent tools for the PayerBench tau2 domain.

Docstrings are the tool definitions the agent sees (tau2 parses the first paragraph and the Args
section). Tools enforce data integrity (a claim must be denied to appeal it, a PCP must be an
accepting in-network primary-care provider) but not conversational policy: whether the caller was
verified, or whether they asked for a change, is left to the agent and scored by the evaluation.
"""

import re
from datetime import date, timedelta

from tau2.environment.toolkit import ToolKitBase, ToolType, is_tool

from payerbench.domain.data_model import (
    Address,
    Appeal,
    AppealReason,
    CardReason,
    Claim,
    IdCardOrder,
    Member,
    PayerDB,
    PriorAuth,
    Provider,
    Transfer,
)

TODAY = date(2026, 9, 24)
APPEAL_WINDOW_DAYS = 180
PCP_EFFECTIVE = "2026-10-01"


def _text(value: object) -> str:
    """Tool arguments as text; some models send IDs, ZIPs and NPIs as JSON numbers."""
    return str(value).strip()


def _zip(value: object) -> str:
    """Five-digit ZIP from text or a number (a numeric 02557 arrives as 2557)."""
    text = _text(value)
    return text.zfill(5) if text.isdigit() and len(text) < 5 else text


def normalize_street(street: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.,]", "", _text(street))).strip().upper()


def normalize_id(raw: str, prefix: str) -> str:
    """Canonical record ID from what a caller read aloud: 'msynth 000007' -> 'M-SYNTH-000007'.

    Letters before the digits form the prefix; separators and case are ignored.
    """
    raw = _text(raw)
    compact = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    digits = re.sub(r"^[A-Z]+", "", compact)
    return (
        f"{prefix}{digits}" if compact.startswith(prefix.replace("-", "")) else raw.strip().upper()
    )


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", _text(phone))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Phone number must have 10 digits")
    return digits


class PayerTools(ToolKitBase):
    """Member-services tools over the PayerBench database."""

    db: PayerDB

    def __init__(self, db: PayerDB) -> None:
        super().__init__(db)

    def _member(self, member_id: str) -> Member:
        m = self.db.members.get(normalize_id(member_id, "M-SYNTH-"))
        if m is None:
            raise ValueError(f"Member {member_id} not found")
        return m

    def _claim(self, claim_id: str) -> Claim:
        c = self.db.claims.get(normalize_id(claim_id, "C-"))
        if c is None:
            raise ValueError(f"Claim {claim_id} not found")
        return c

    # --- identity -------------------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def find_member_id(
        self, first_name: str, last_name: str, date_of_birth: str, zip_code: str
    ) -> str:
        """Look up a member ID from full name, date of birth and home ZIP code, for callers who
        do not have their ID card. Does not verify the caller; call verify_identity afterwards.

        Args:
            first_name: Member's first name.
            last_name: Member's last name.
            date_of_birth: Date of birth as YYYY-MM-DD.
            zip_code: Five-digit ZIP code of the member's address on file.

        Returns:
            The member ID.
        """
        hits = [
            m.member_id
            for m in self.db.members.values()
            if m.first_name.lower() == _text(first_name).lower()
            and m.last_name.lower() == _text(last_name).lower()
            and m.dob == _text(date_of_birth)
            and m.address.zip_code == _zip(zip_code)
        ]
        if len(hits) != 1:
            raise ValueError("No unique member matches those details")
        return hits[0]

    @is_tool(ToolType.WRITE)
    def verify_identity(self, member_id: str, date_of_birth: str) -> dict:
        """Verify a caller's identity against the member record. Required before discussing or
        changing anything about a member. A successful verification is recorded for the call.

        Args:
            member_id: Member ID the caller provided.
            date_of_birth: Date of birth the caller provided, as YYYY-MM-DD.

        Returns:
            Whether the details match, and the member's name when they do.
        """
        m = self.db.members.get(normalize_id(member_id, "M-SYNTH-"))
        if m is None or m.dob != _text(date_of_birth):
            return {"verified": False}
        if m.member_id not in self.db.verified_members:
            self.db.verified_members.append(m.member_id)
        return {"verified": True, "member_id": m.member_id, "name": f"{m.first_name} {m.last_name}"}

    @is_tool(ToolType.READ)
    def verify_provider(self, npi: str) -> Provider:
        """Look up a provider by NPI, to confirm that a caller from a provider office represents a
        provider known to the plan.

        Args:
            npi: The provider's 10-digit National Provider Identifier.

        Returns:
            The provider record.
        """
        for p in self.db.providers.values():
            if p.npi == _text(npi):
                return p
        raise ValueError(f"No provider with NPI {npi}")

    # --- reads ----------------------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_member_details(self, member_id: str) -> Member:
        """Get a member's plan, coverage status and dates, PCP, deductible and out-of-pocket
        progress, address and phone on file.

        Args:
            member_id: The member ID.

        Returns:
            The member record.
        """
        return self._member(member_id)

    @is_tool(ToolType.READ)
    def list_claims(self, member_id: str) -> list[Claim]:
        """List a member's claims, newest first, with status, amounts and any denial reason.

        Args:
            member_id: The member ID.

        Returns:
            The member's claims.
        """
        mid = self._member(member_id).member_id
        rows = [c for c in self.db.claims.values() if c.member_id == mid]
        return sorted(rows, key=lambda c: c.service_date, reverse=True)

    @is_tool(ToolType.READ)
    def get_claim(self, claim_id: str) -> Claim:
        """Get one claim by claim ID.

        Args:
            claim_id: The claim ID, for example C-12345678.

        Returns:
            The claim.
        """
        return self._claim(claim_id)

    @is_tool(ToolType.READ)
    def get_prior_auths(self, member_id: str) -> list[PriorAuth]:
        """List a member's prior authorization requests with status, dates and reviewer notes.

        Args:
            member_id: The member ID.

        Returns:
            The member's prior authorizations.
        """
        mid = self._member(member_id).member_id
        return [p for p in self.db.prior_auths.values() if p.member_id == mid]

    @is_tool(ToolType.READ)
    def search_benefits(self, query: str) -> list[dict]:
        """Search the plan's benefits document (coverage rules, limits, appeals, network,
        privacy). Returns the most relevant sections.

        Args:
            query: Keywords to search for.

        Returns:
            Matching sections with their text.
        """
        words = [w for w in query.lower().split() if len(w) > 2]
        scored = []
        for title, text in self.db.plan_document.items():
            hay = f"{title} {text}".lower()
            score = sum(hay.count(w) for w in words)
            if score:
                scored.append((score, title, text))
        scored.sort(reverse=True)
        return [{"section": t, "text": x} for _, t, x in scored[:3]]

    @is_tool(ToolType.READ)
    def find_providers(
        self,
        specialty: str,
        zip_code: str | None = None,
        in_network_only: bool = True,
        accepting_new_only: bool = False,
    ) -> list[Provider]:
        """Find providers by specialty (primary care, cardiology, dermatology, orthopedics,
        physical therapy, endocrinology), optionally by ZIP code, network status and whether they
        accept new patients.

        Args:
            specialty: Provider specialty.
            zip_code: Five-digit ZIP code to filter by.
            in_network_only: Only return in-network providers.
            accepting_new_only: Only return providers accepting new patients.

        Returns:
            Up to 10 matching providers.
        """
        rows = [
            p
            for p in self.db.providers.values()
            if p.specialty == _text(specialty).lower()
            and (zip_code is None or p.zip_code == _zip(zip_code))
            and (not in_network_only or p.in_network)
            and (not accepting_new_only or p.accepting_new)
        ]
        return sorted(rows, key=lambda p: p.npi)[:10]

    # --- writes ---------------------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def update_contact_info(
        self,
        member_id: str,
        street: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        phone: str | None = None,
    ) -> Member:
        """Update a member's mailing address and/or phone number. To change the address, give
        all four address fields.

        Args:
            member_id: The member ID.
            street: Street line, for example "77 Birch Ln Apt 4".
            city: City.
            state: Two-letter state code.
            zip_code: Five-digit ZIP code.
            phone: Ten-digit phone number.

        Returns:
            The updated member record.
        """
        m = self._member(member_id)
        parts = [street, city, state, zip_code]
        if any(parts) and not all(parts):
            raise ValueError("Address changes need street, city, state and zip_code")
        if not any(parts) and not phone:
            raise ValueError("Nothing to update")
        if all(parts):
            if not re.fullmatch(r"\d{5}", _zip(zip_code)):
                raise ValueError("ZIP code must be five digits")
            m.address = Address(
                street=normalize_street(street),
                city=_text(city).upper(),
                state=_text(state).upper(),
                zip_code=_zip(zip_code),
            )
        if phone:
            m.phone = normalize_phone(phone)
        return m

    @is_tool(ToolType.WRITE)
    def order_id_card(self, member_id: str, reason: CardReason) -> IdCardOrder:
        """Order a replacement ID card, mailed to the address on file at the time of the order.

        Args:
            member_id: The member ID.
            reason: One of lost, damaged, never_received.

        Returns:
            The order, including the address it ships to.
        """
        m = self._member(member_id)
        order = IdCardOrder(reason=reason, ship_to=m.address.model_copy())
        m.id_card_orders.append(order)
        return order

    @is_tool(ToolType.WRITE)
    def change_pcp(self, member_id: str, npi: str) -> Member:
        """Change a member's primary care provider (PCP). The new PCP must be an in-network
        primary care provider who is accepting new patients. Takes effect on the first day of
        next month.

        Args:
            member_id: The member ID.
            npi: NPI of the new primary care provider.

        Returns:
            The updated member record.
        """
        m = self._member(member_id)
        p = next((p for p in self.db.providers.values() if p.npi == _text(npi)), None)
        if p is None:
            raise ValueError(f"No provider with NPI {npi}")
        if p.specialty != "primary care":
            raise ValueError("A PCP must be a primary care provider")
        if not (p.in_network and p.accepting_new):
            raise ValueError("A PCP must be in network and accepting new patients")
        m.pcp_name, m.pcp_npi, m.pcp_effective_date = p.name, p.npi, PCP_EFFECTIVE
        return m

    @is_tool(ToolType.WRITE)
    def file_appeal(self, claim_id: str, reason: AppealReason) -> Appeal:
        """File a first-level appeal on a denied claim. Allowed within 180 days of the denial
        date, once per claim. Decisions take up to 30 days.

        Args:
            claim_id: The denied claim's ID.
            reason: One of disagree_medical_necessity, prior_auth_was_obtained,
                billing_or_coding_error, provider_should_be_in_network, other.

        Returns:
            The appeal, with its appeal ID (the confirmation number to give the caller).
        """
        c = self._claim(claim_id)
        if c.status != "denied" or c.denial_date is None:
            raise ValueError(
                f"Claim {c.claim_id} is {c.status}; only denied claims can be appealed"
            )
        deadline = date.fromisoformat(c.denial_date) + timedelta(days=APPEAL_WINDOW_DAYS)
        if TODAY > deadline:
            raise ValueError(f"The appeal window closed on {deadline.isoformat()}")
        appeal_id = f"APL-{c.claim_id.removeprefix('C-')}"
        if appeal_id in self.db.appeals:
            raise ValueError(f"Claim {c.claim_id} already has appeal {appeal_id}")
        appeal = Appeal(
            appeal_id=appeal_id, claim_id=c.claim_id, member_id=c.member_id, reason=reason
        )
        self.db.appeals[appeal_id] = appeal
        return appeal

    @is_tool(ToolType.WRITE)
    def request_expedited_review(self, auth_id: str) -> PriorAuth:
        """Request expedited (72-hour) review of a pending prior authorization. Only for pending
        requests, and only when the caller reports that their provider says waiting could
        seriously harm their health.

        Args:
            auth_id: The prior authorization ID, for example PA-123456.

        Returns:
            The updated prior authorization.
        """
        p = self.db.prior_auths.get(normalize_id(auth_id, "PA-"))
        if p is None:
            raise ValueError(f"Prior authorization {auth_id} not found")
        if p.status != "pending":
            raise ValueError(f"Prior authorization {p.auth_id} is {p.status}, not pending")
        p.expedited = True
        return p

    @is_tool(ToolType.WRITE)
    def transfer_to_human_agent(self, summary: str) -> str:
        """Transfer the caller to a human representative, with a short summary of the issue.
        Use only when the caller asks for a human or the request is outside what the policy
        and tools allow you to resolve.

        Args:
            summary: A short summary of the caller's issue.

        Returns:
            A confirmation that the transfer was placed.
        """
        verified = self.db.verified_members[-1] if self.db.verified_members else None
        self.db.transfers.append(Transfer(member_id=verified))
        return "Transfer successful"
