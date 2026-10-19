"""Caller-side tools: what the simulated caller can look at during the call.

This is tau2's dual-control setup. The caller does not start out knowing everything in their
instructions; some details (member ID, claim number, NPI) are only on a card or letter they have
to look at, as a real caller would. A document the caller does not have is reported as a plain
answer, not an error, because tau2 ends a call after ten tool errors.
"""

from tau2.environment.toolkit import ToolKitBase, ToolType, is_tool

from payerbench.domain.data_model import CallerLetter, PayerDB


class CallerTools(ToolKitBase):
    """Documents the caller has in hand."""

    db: PayerDB

    def __init__(self, db: PayerDB) -> None:
        super().__init__(db)

    @is_tool(ToolType.READ)
    def read_insurance_card(self) -> dict[str, str] | str:
        """Read your health plan ID card.

        Returns:
            The fields printed on the card.
        """
        if not self.db.caller.insurance_card:
            return "You do not have your insurance card with you."
        return self.db.caller.insurance_card

    @is_tool(ToolType.READ)
    def read_letters(self) -> list[CallerLetter] | str:
        """Read the letters you have received from the health plan.

        Returns:
            Each letter's title and text.
        """
        if not self.db.caller.letters:
            return "You have no letters from the health plan."
        return self.db.caller.letters

    @is_tool(ToolType.READ)
    def read_practice_details(self) -> dict[str, str] | str:
        """Read your practice's details (for callers from a provider office).

        Returns:
            Practice name and the provider's NPI.
        """
        if not self.db.caller.provider_office:
            return "You are not calling from a provider office."
        return self.db.caller.provider_office
