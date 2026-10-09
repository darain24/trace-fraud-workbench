"""Deterministic implementation of the bank's fraud policy; no financial actions."""

from dataclasses import dataclass

from .models import Action


@dataclass
class Situation:
    probability: float
    exposure: float
    verdict: str = "uncertain"
    response: str | None = None
    disputed: bool = False
    recurring: bool = False
    card_testing: bool = False
    cleared_over_100: bool = False
    shared_fraud: bool = False
    undocumented: bool = False
    conflict: bool = False
    independent_evidence: int = 0
    pending_authorization: bool = False
    confirmed_cards: int = 0
    credentials_compromised: bool = False


def route(action: str, exposure: float) -> str:
    if action in ("FILE_REPORT", "BLOCK_ALL_CARDS"):
        return "L2"
    if action == "BLOCK_CARD":
        return "L2" if exposure > 2500 else "L1"
    if action == "DECLINE_TRANSACTION":
        return "L1"
    return "auto"


def decide(s: Situation) -> list[Action]:
    result = []

    def add(name, reason):
        if not any(a.action == name for a in result):
            result.append(
                Action(action=name, route=route(name, s.exposure), reason=reason)
            )

    request = s.verdict == "uncertain" and not s.response
    if s.probability >= 0.30 or s.disputed or request or s.response:
        add(
            "CREATE_CASE",
            "§3a: maintain an internal investigation record; persist supporting evidence.",
        )
    if s.conflict or s.response == "conflicting":
        add("ESCALATE_TO_ANALYST", "R8: evidence conflicts; human review is required.")
        add(
            "MONITOR_CARD",
            "R8: preserve visibility while an analyst resolves conflicting evidence.",
        )
        return result
    if s.response == "confirmed":
        add(
            "CLOSE_NO_FRAUD",
            "R3: simulated customer confirmation settles the transaction question.",
        )
        return result
    if s.response == "no_reply":
        add(
            "MONITOR_CARD", "R4: no customer reply within the simulated 24-hour period."
        )
        if s.pending_authorization:
            add(
                "DECLINE_TRANSACTION",
                "R4: decline a pending authorization only; L1 approval required.",
            )
        if s.exposure > 500:
            add(
                "ESCALATE_TO_ANALYST",
                "R4: unanswered verification and exposure exceeds $500.",
            )
        return result
    if s.recurring and s.disputed and s.response != "denied":
        add(
            "VERIFY_WITH_CUSTOMER",
            "R7: recurring-amount hypothesis needs customer verification; merchant identity is not established.",
        )
        add(
            "WARN_CUSTOMER",
            "R7: explain the recurring-charge hypothesis without asserting merchant identity.",
        )
        return result
    if s.card_testing:
        add(
            "DECLINE_TRANSACTION",
            "R5: at least three small online transactions within one hour followed by a larger purchase.",
        )
        add(
            "STEP_UP_AUTH",
            "R5: require additional authentication for the card-testing sequence.",
        )
        if s.cleared_over_100:
            add(
                "BLOCK_CARD",
                "R5: a purchase over $100 is confirmed cleared; approval required.",
            )
    if s.response == "denied":
        add(
            "BLOCK_CARD",
            "R2: recorded customer denial; recommend blocking this card with the appropriate approval.",
        )
        add("CREATE_CASE", "R2: record the disputed activity and investigation.")
    elif s.verdict == "legitimate":
        add("ALLOW_TRANSACTION", "§1 and §6: evidence supports legitimate activity.")
        add(
            "CLOSE_NO_FRAUD",
            "§6: two independent corroborating findings support closure.",
        )
    elif s.verdict == "uncertain":
        if not s.card_testing:
            add(
                "VERIFY_WITH_CUSTOMER",
                "R1: available signals do not establish fraud; seek verification before blocking.",
            )
        if s.exposure > 500:
            add(
                "ESCALATE_TO_ANALYST",
                "R8: uncertain verdict with potential exposure above $500.",
            )
    elif not s.card_testing:
        add(
            "ESCALATE_TO_ANALYST",
            "§2 and R8: an evidence-supported fraud finding without a cardholder "
            "denial needs a human before any action with customer impact.",
        )
        add(
            "MONITOR_CARD",
            "§1: raise monitoring sensitivity while the analyst reviews. This "
            "contains further exposure at no customer impact, which blocking a card "
            "on behavioural evidence alone would not.",
        )
    strongly_suspected = s.verdict == "fraud" or s.response == "denied"
    # R9 requires coordinated or repeated abuse *across customers* before a report,
    # not merely activity that matches none of the five documented typologies. An
    # unmatched single-account episode gets a case and an analyst, not a filing.
    reportable = (
        s.exposure > 1000 or s.shared_fraud or (s.undocumented and s.shared_fraud)
    )
    if strongly_suspected and reportable:
        add("CREATE_CASE", "§3a: every report must have an internal case.")
        add(
            "FILE_REPORT",
            "§3a / R2 / R6 / R9: strong suspicion with threshold exposure or corroborated connected activity; L2 approval required.",
        )
    if s.shared_fraud:
        add(
            "MONITOR_CONNECTED_CARDS",
            "R6: monitor the corroborated set of connected cards.",
        )
    if s.undocumented and strongly_suspected:
        add(
            "ESCALATE_TO_ANALYST",
            "R9: activity matches no documented pattern and needs a human read.",
        )
    return result


def validate_actions(actions, exposure):
    return [
        f"{a.action}: expected {route(a.action, exposure)}, got {a.route}"
        for a in actions
        if a.route != route(a.action, exposure)
    ]
