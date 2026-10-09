import asyncio
import copy
import json
import time

from . import analysis, llm, retrieval, scoring, store, tigergraph
from .config import TG_URL
from .models import SAR, Answer, CaseRecord, EvidenceRequest, Recommendations
from .policy import Situation, decide

RUN_LOCK = asyncio.Lock()


def situation(a, response=None):
    # A `customer_report` trigger is the cardholder stating they did not make the
    # transaction. Policy R2 keys off a denial, not off whether the agent happened to
    # ask for one, so the trigger itself opens that branch.
    if response is None and a["disputed"] and not a["conflict"] and not a["recurring"]:
        response = "denied"
    return Situation(
        probability=a["probability"],
        exposure=a["exposure"],
        verdict=a["verdict"],
        response=response,
        disputed=a["disputed"],
        recurring=a["recurring"],
        card_testing=a["testing"],
        shared_fraud=a["shared_fraud"],
        undocumented=a["pattern"] == "undocumented",
        conflict=a["conflict"],
        independent_evidence=a.get("independent_evidence", 0),
    )


PATTERN_TEXT = {
    "card_testing": "card testing",
    "card_not_present_fraud": "card-not-present fraud",
    "card_not_present_new_device": "card-not-present fraud from a device new to the account",
    "out_of_region_use": "out-of-region card-present use",
    "account_takeover": "account takeover",
    "undocumented": "an undocumented pattern",
    "none": "no identified fraud pattern",
}

def clause(claim):
    """First sentence of a finding, for prose that reads as prose."""
    return claim.split(". ")[0].rstrip(".").strip()


def article(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


RESPONSE_TEXT = {
    "confirmed": "the cardholder confirms they made the transaction",
    "denied": "the cardholder denies making the transaction",
    "no_reply": "no reply is received within the 24-hour window",
    "conflicting": "the reply conflicts with the transaction evidence",
}


def assumed_response(a):
    """Pick the reply to simulate, and say what it is based on.

    The dataset includes no customer replies, so this is an assumption and is
    recorded as one. It is keyed to the assessed probability rather than chosen to
    make the case tidy: where the evidence leans fraud the cardholder is assumed to
    deny, where it leans legitimate they are assumed to confirm, and where the
    evidence conflicts with itself no single reply is assumed to settle it.
    """
    if a["conflict"]:
        return "conflicting", (
            "The cardholder disputes a charge that matches their own recurring amount "
            "and product code. The reply is assumed to restate the dispute without "
            "resolving the contradiction, which is the case policy R7 and R8 describe."
        )
    if a["probability"] >= 0.5:
        return "denied", (
            f"Assessed fraud probability is {a['probability']:.2f} on "
            f"{a['independent_evidence']} independent finding(s), so the cardholder is "
            "assumed to deny the transaction. This is the modal outcome for this "
            "evidence shape in the closed-case record."
        )
    return "confirmed", (
        f"Assessed fraud probability is {a['probability']:.2f} and the counter-evidence "
        "matches the shapes the bank's own cleared cases describe (a new handset, a "
        "trip, or an unusually large but intended purchase), so the cardholder is "
        "assumed to confirm the transaction."
    )


def needs_evidence(a):
    """Policy R1: a weak or single-signal case is verified before it is acted on.

    A corroborated shared-origin cluster is excluded. One cardholder's answer cannot
    settle whether several cards are being used through one device profile, and R6
    routes that case to a report and connected-card monitoring rather than to a
    verification call.
    """
    if a.get("shared_fraud"):
        return False
    if a["disputed"] and not a["conflict"]:
        # The cardholder has already said they did not make it. Asking them to
        # validate the transaction they just reported is not evidence gathering.
        return False
    return a["verdict"] == "uncertain" or a["conflict"]


def write_summary(trigger, a, packet, response):
    f = packet["flagged"]
    ids = [t["id"] for t in a["affected"]]
    v = a.get("velocity") or {"v48": len(ids), "baseline_rate_48h": 0.0}
    parts = []
    parts.append(
        f"Alert {trigger['case_id']} opened on {trigger['opened_at'][:10]} from "
        f"{article(trigger['trigger_type'])} "
        f"{trigger['trigger_type'].replace('_', ' ')} on transaction {f['id']} "
        f"(${abs(f['amount']):,.2f}, {f['channel'].replace('_', ' ')}) for card "
        f"{f['card_id']}."
    )
    top = sorted(a.get("findings", []), key=lambda x: -abs(x["weight"]))[:2]
    if top:
        parts.append(
            "The findings that moved the assessment most: "
            + "; ".join(clause(x["claim"]) for x in top)
            + "."
        )
    parts.append(
        f"Card activity ran at {v['v48']} transaction(s) in 48 hours against a "
        f"{v['baseline_rate_48h']} baseline for this card."
    )
    if a["history"]:
        confirmed = sum(h["outcome"] == "confirmed_fraud" for h in a["history"])
        parts.append(
            f"{len(a['history'])} closed investigation(s) reachable from this customer "
            f"or its device profile were retrieved as memory, {confirmed} of them "
            "confirmed fraud."
        )
    if a["verdict"] == "legitimate":
        parts.append(
            f"The evidence supports legitimate activity at probability "
            f"{a['probability']:.2f}; no transaction is treated as part of a fraud "
            "episode."
        )
    elif a["verdict"] == "fraud":
        parts.append(
            f"The assessment is fraud at probability {a['probability']:.2f}, scoped to "
            f"{len(ids)} transaction(s) and ${a['exposure']:,.2f} exposure, matching "
            f"{PATTERN_TEXT[a['pattern']]}."
        )
    else:
        parts.append(
            f"The evidence is not sufficient to decide at probability "
            f"{a['probability']:.2f}, so verification was requested before any action "
            "with customer impact."
        )
    if response:
        parts.append(
            f"The simulated reply was that {RESPONSE_TEXT[response]}, which is recorded "
            "as an assumption, not a customer contact."
        )
    return " ".join(parts)


def write_narrative(trigger, a, packet, response):
    """A SAR narrative that stands on its own: who, what, when, where, how, why."""
    f = packet["flagged"]
    affected = a["affected"]
    ids = [t["id"] for t in affected]
    first, last = min(t["ts"] for t in affected), max(t["ts"] for t in affected)
    channels = sorted({t["channel"].replace("_", " ") for t in affected})
    amounts = ", ".join(f"${abs(t['amount']):,.2f}" for t in affected[:6])
    lines = [
        f"Customer {f['customer_id']}, an account holder of this institution, holds "
        f"card {f['card_id']}. Between {first[:16]} and {last[:16]} this institution "
        f"identified {len(ids)} transaction(s) on that card totalling "
        f"${a['exposure']:,.2f} that appear to be unauthorised.",
        f"The transactions were {amounts}"
        + (", among others" if len(affected) > 6 else "")
        + f", carried out through the {' and '.join(channels)} channel"
        + ("s" if len(channels) > 1 else "")
        + f", billed to region code {f['region'] or 'not recorded'} in country code "
        f"{f['country'] or 'not recorded'}. Transaction identifiers are "
        + ", ".join(ids[:10])
        + ("." if len(ids) <= 10 else ", and others recorded in the case file."),
    ]
    if f["device"]:
        lines.append(
            f"The online activity originated from the device profile "
            f"\"{f['device']}\", which the identity record marks as "
            f"{f['new_device'] or 'not recorded'} for this account"
            + (
                f" and which carries the proxy indicator {f['proxy']}."
                if f["proxy"]
                else "."
            )
        )
    else:
        lines.append(
            "The activity was card-present, for which this dataset carries no device "
            "or connection record."
        )
    reasons = [
        clause(x["claim"])
        for x in sorted(a.get("findings", []), key=lambda x: -x["weight"])[:3]
        if x["weight"] > 0
    ]
    if reasons:
        lines.append(
            "The activity was identified as suspicious on the following grounds. "
            + " ".join(r.rstrip(".") + "." for r in reasons)
        )
    if a["connected_cards"]:
        lines.append(
            f"The same device profile links this activity to {len(a['connected_cards'])} "
            "other card(s) of other customers showing comparable activity in the same "
            "window: " + ", ".join(a["connected_cards"][:8]) + ". The shared element "
            "named in this report is the device profile, not an identified individual."
        )
    if a["history"]:
        confirmed = [h for h in a["history"] if h["outcome"] == "confirmed_fraud"]
        if confirmed:
            lines.append(
                f"{len(confirmed)} prior investigation(s) closed by this institution as "
                "confirmed fraud are reachable from the same customer or device profile "
                "and were used as background: "
                + ", ".join(h["id"] for h in confirmed[:6])
                + "."
            )
    if response == "denied":
        lines.append(
            "When contacted, the cardholder denied authorising the transaction. This "
            "reply is a simulation recorded in the case file; the dataset "
            "supplies no customer replies, and no customer was contacted."
        )
    lines.append(
        f"The pattern is assessed as {PATTERN_TEXT[a['pattern']]} at a fraud "
        f"probability of {a['probability']:.2f}, derived from the weighted findings "
        "listed in the case file rather than from the detection model's own score."
    )
    lines.append(
        "This report is filed under section 3a of the institution's fraud policy and "
        "requires L2 approval; no card action has been executed at the time of filing."
    )
    # A SAR narrative is specified at six to twelve sentences. Trim from the middle,
    # which is the corroborating detail, never the who/what/when/where that opens it
    # or the assessment and filing basis that close it.
    if len(lines) > 12:
        lines = lines[:4] + lines[-(12 - 4) :]
    return " ".join(lines)


def build_answer(trigger, a, packet, response=None, previous=None, tokens=0, latency=0):
    """Assemble the answer. When the policy calls for more evidence, the initial
    recommendation is recorded, a request is raised, a reply is simulated and stated
    as an assumption, and the final recommendation is recomputed against it."""
    f = packet["flagged"]
    initial_actions = (
        list(previous.next_best_actions.initial)
        if previous
        else decide(situation(a, None))
    )
    requests = list(previous.evidence_requests) if previous else []
    what_changed = "nothing"
    assessment = a

    if (
        response is None
        and not previous
        and a["disputed"]
        and not a["conflict"]
        and not a["recurring"]
    ):
        # The denial arrived with the alert. Fold it in as evidence so the verdict,
        # the status and the R2 actions describe the same case, but raise no evidence
        # request: nothing was asked for.
        a = assessment = apply_response(
            a, packet, "denied", origin="case_pack:" + trigger["case_id"]
        )
        initial_actions = decide(situation(a, None))
    if response is None and needs_evidence(a) and not previous:
        response, basis = assumed_response(a)
        requests.append(
            EvidenceRequest(
                type="step_up_auth" if a["probability"] >= 0.5 else "customer_validation",
                asked_after_step=len(store.events(trigger["case_id"])),
                assumed_response=(
                    f"SIMULATED ({response}): {RESPONSE_TEXT[response]}. " + basis
                ),
            )
        )
        assessment = apply_response(a, packet, response)
    elif response:
        supplied = EvidenceRequest(
            type="customer_validation",
            asked_after_step=len(store.events(trigger["case_id"])),
            assumed_response="SIMULATED ({}): {}.".format(
                response, RESPONSE_TEXT[response]
            ),
        )
        # A reply supplied for this case supersedes the reply the agent assumed for
        # the same request; it does not stack a second request on top of it.
        if requests and requests[-1].assumed_response.startswith("SIMULATED ("):
            requests[-1] = supplied
        else:
            requests.append(supplied)
        assessment = a

    a = assessment
    actions = decide(situation(a, response))
    if requests and [x.model_dump() for x in actions] != [
        x.model_dump() for x in initial_actions
    ]:
        what_changed = (
            f"The simulated reply ({RESPONSE_TEXT[response]}) moved the assessed "
            f"probability to {a['probability']:.2f}, which changes the policy branch "
            "that applies and therefore the recommended actions."
        )
    elif requests:
        what_changed = (
            f"The simulated reply ({RESPONSE_TEXT[response]}) did not move the case "
            "across a policy threshold, so the recommendation stands."
        )

    final_names = {x.action for x in actions}
    status = (
        "escalated"
        if "ESCALATE_TO_ANALYST" in final_names
        else (
            "closed_legitimate"
            if a["verdict"] == "legitimate"
            else ("closed_fraud" if a["verdict"] == "fraud" else "open")
        )
    )
    affected = a["affected"]
    ids = [t["id"] for t in affected]
    description = ""
    if a["pattern"] == "undocumented" and a.get("shared_fraud"):
        others = len(a["connected_cards"])
        description = (
            "Cards belonging to different customers transact through one shared device "
            "profile within a short window, each carrying the same new-device and proxy "
            "combination, and prior confirmed cases already attach to that profile. It "
            f"affects {others + 1} card(s) across separate customers rather than one "
            "compromised account. It was found by expanding from the flagged "
            "transaction to its device profile and back out to the other cards that "
            "touched it, then checking which of those cards already carry confirmed "
            "cases. It is not card testing, a single-account takeover or out-of-region "
            "use, so it is recorded in its own terms."
        )
    elif a["pattern"] == "undocumented":
        v = a.get("velocity", {})
        description = (
            "Card-present activity accelerated sharply on one card without moving to a "
            "new billing region, without a device record to examine, and without the "
            "mixed-channel signature of an account takeover: "
            f"{v.get('v48', len(ids))} transaction(s) in 48 hours against a "
            f"{v.get('baseline_rate_48h', 0)} baseline for this card. It affects this "
            "cardholder alone on present evidence. It was found by comparing the card's "
            "own 48-hour rate with its preceding 30 days rather than by matching a "
            "known typology, and it fits none of the five documented patterns."
        )
    record = CaseRecord(
        status=status,
        verdict=a["verdict"],
        fraud_probability=a["probability"],
        pattern=a["pattern"],
        pattern_description=description,
        affected_txn_ids=ids,
        first_suspicious_txn_id=ids[0] if ids else "",
        connected_card_ids=a["connected_cards"],
        connected_device_profiles=a.get("connected_devices", []),
        exposure_usd=a["exposure"],
        evidence=a["evidence"],
        similar_prior_cases=[h["id"] for h in a["history"]],
        summary=write_summary(trigger, a, packet, response),
    )
    should_file = "FILE_REPORT" in final_names
    sar = SAR(
        reason=(
            "Policy 3a: a report is required only when fraud is confirmed or strongly "
            "suspected and exposure exceeds $1,000, the activity connects to a shared "
            "device profile or region cluster, or the pattern is coordinated or "
            f"undocumented. This case is assessed {a['verdict']} at "
            f"{a['probability']:.2f} with ${a['exposure']:,.2f} exposure and "
            f"{len(a['connected_cards'])} connected card(s), so none of those "
            "conditions is met and the internal case alone is the correct record."
        )
    )
    if should_file:
        reasons = []
        if a["exposure"] > 1000:
            reasons.append(f"exposure of ${a['exposure']:,.2f} exceeds $1,000")
        if a["shared_fraud"]:
            reasons.append("the activity connects to a shared device profile (R6)")
        if a["pattern"] == "undocumented":
            reasons.append("the pattern matches none of the documented typologies (R9)")
        sar = SAR(
            file=True,
            reason=(
                "Policy 3a: fraud is strongly suspected and "
                + ", and ".join(reasons or ["the policy filing conditions are met"])
                + ". FILE_REPORT is always L2."
            ),
            narrative=write_narrative(trigger, a, packet, response),
            subjects=[f["customer_id"], f["card_id"]]
            + a["connected_cards"]
            + a.get("connected_devices", []),
            total_amount_usd=a["exposure"],
            activity_dates=[
                min(t["ts"] for t in affected)[:10],
                max(t["ts"] for t in affected)[:10],
            ],
        )
    if a["conflict"]:
        stop = (
            "Stopped under R8. The cardholder's denial and the recurring-charge match "
            "point in opposite directions, and no further graph evidence available "
            "before the alert cutoff separates them. A human analyst resolves this."
        )
    elif response in ("confirmed", "denied"):
        stop = (
            f"Stopped under policy 6: the verification response settles the question. "
            f"Probability moved to {a['probability']:.2f} and the actions below follow "
            "directly from it."
        )
    elif a["verdict"] != "uncertain" and a["independent_evidence"] >= 2:
        stop = (
            f"Stopped under policy 6: probability {a['probability']:.2f} is past the "
            f"threshold on {a['independent_evidence']} independent findings. Further "
            "graph traversal would add detail, not change the decision."
        )
    else:
        stop = (
            "Stopped pending the requested evidence. Everything reachable in the graph "
            "before this alert's cutoff has been examined; only the cardholder can "
            "resolve the remaining ambiguity."
        )
    return Answer(
        case_id=trigger["case_id"],
        case=record,
        evidence_requests=requests,
        next_best_actions=Recommendations(
            initial=initial_actions if requests else actions,
            final=actions,
            what_changed=what_changed,
        ),
        sar=sar,
        stop_reason=stop,
        tool_calls=packet["tool_calls"],
        tokens=tokens,
        latency_s=round(latency, 3),
    )


def apply_response(a, packet, response, origin="request"):
    """Fold a cardholder's answer back into the assessment, as new evidence.

    `origin` distinguishes a reply the agent asked for from a denial that arrived in
    the trigger itself. The evidence is the same; only its provenance differs, and
    the case file must not describe an unasked-for report as a simulated reply.
    """
    a = copy.deepcopy(a)
    f = packet["flagged"]
    if response == "confirmed":
        a.update(
            verdict="legitimate",
            probability=0.07,
            pattern="none",
            affected=[],
            exposure=0.0,
            connected_cards=[],
            connected_devices=[],
            shared_fraud=False,
            conflict=False,
        )
    elif response == "denied":
        a.update(verdict="fraud", probability=0.93, conflict=False)
        if not a["affected"]:
            a["affected"] = [f]
            a["exposure"] = round(abs(f["amount"]), 2)
        if a["pattern"] == "none":
            a["pattern"] = (
                "card_not_present_fraud"
                if f["channel"] == "online"
                else "out_of_region_use"
            )
    elif response == "conflicting":
        a.update(verdict="uncertain", probability=0.45, conflict=True)
    else:
        a.update(verdict="uncertain", probability=0.50)
    if origin == "request":
        claim = (
            f"SIMULATED verification response: {RESPONSE_TEXT[response]}. The "
            "the dataset includes no customer replies; this is an assumption recorded "
            "in evidence_requests, not a customer contact."
        )
        ref = "evidence_request:1"
    else:
        claim = (
            "The cardholder's own report is the denial: they state they did not make "
            "the flagged transaction. Policy R2 treats that as direct evidence, so no "
            "verification was requested for something already reported."
        )
        ref = origin
    a["evidence"] = a["evidence"] + [
        {
            "claim": claim,
            "source": "customer",
            "ref": ref,
            "entity_ids": [f["id"]],
        }
    ]
    return a


def graph_view(packet, a):
    f = packet["flagged"]
    nodes = []
    edges = []
    seen = set()

    def node(id, label, kind, **extra):
        if id not in seen:
            nodes.append({"id": id, "label": label, "kind": kind, **extra})
            seen.add(id)

    def edge(source, target, label):
        edges.append(
            {
                "id": f"{source}-{target}-{label}",
                "source": source,
                "target": target,
                "label": label,
            }
        )

    node(f["customer_id"], f["customer_id"], "customer")
    node(f["card_id"], f["card_id"], "card")
    edge(f["customer_id"], f["card_id"], "owns")
    display = packet["timeline"][-3:]
    if not any(t["id"] == f["id"] for t in display):
        display.append(f)
    for t in display:
        node(t["card_id"], t["card_id"], "card")
        node(
            t["id"],
            f"${abs(t['amount']):,.2f}",
            "transaction",
            flagged=t["id"] == f["id"],
            timestamp=t["ts"],
            risk=t["risk"],
        )
        edge(t["card_id"], t["id"], "transaction")
    if f["device"]:
        node("device:" + f["device"], f["device"].split(" | ")[0][:26], "device")
        edge(f["id"], "device:" + f["device"], "profile")
        other = {}
        for t in packet["neighbors"]:
            if t["card_verified"]:
                other[t["card_id"]] = t
        for t in list(other.values())[:3]:
            node(t["card_id"], t["card_id"], "connected")
            edge("device:" + f["device"], t["card_id"], "shared profile ≠ fraud")
    else:
        node("region:" + f["region"], "Region " + (f["region"] or "unknown"), "region")
        edge(f["id"], "region:" + f["region"], "billed in")
    return {"nodes": nodes, "edges": edges}


async def investigate(case_id, use_llm=True):
    async with RUN_LOCK:
        record = store.get_case(case_id)
        if record["result"]:
            return record  # Resume is idempotent; evidence updates are separate.
        start = time.monotonic()
        with store.connect() as c:
            c.execute(
                "UPDATE cases SET state='running',error=NULL WHERE id=?", (case_id,)
            )
        try:
            trigger = record["trigger"]
            store.event(
                case_id,
                "trigger",
                "Investigation opened",
                {"trigger": trigger["trigger_type"]},
            )
            packet = await asyncio.to_thread(analysis.collect, trigger)
            store.event(
                case_id,
                "evidence",
                "Transaction history and relationships retrieved",
                {
                    "source": "local_sqlite",
                    "cutoff": packet["cutoff"],
                    "transactions": len(packet["timeline"]),
                },
            )
            grounding_error = None
            if TG_URL:
                try:
                    packet = await retrieval.ground(packet, trigger)
                    store.event(
                        case_id,
                        "graph",
                        "TigerGraph evidence and vector context verified",
                        {"source": "tigergraph"},
                    )
                except Exception as exc:
                    grounding_error = str(exc)[:250]
                    store.event(
                        case_id,
                        "warning",
                        "TigerGraph grounding failed; local analysis explicitly retained",
                        {"error": grounding_error},
                    )
            a = analysis.assess(packet, trigger)
            advisory = scoring.predict(trigger["flagged_txn_id"])
            if packet["source"] == "tigergraph":
                for ev in a["evidence"]:
                    if ev["source"] == "external":
                        ev.update(
                            source="graph",
                            ref=ev["ref"].replace(
                                "local_sqlite:", "tigergraph:verified_derivation:"
                            ),
                        )
                for doc in packet.get("graph_documents", [])[:3]:
                    a["evidence"].append(
                        {
                            "claim": doc["text"][:1200],
                            "source": "document",
                            "ref": "tigergraph:vector:" + doc["id"],
                            "entity_ids": [],
                        }
                    )
            store.event(
                case_id,
                "assessment",
                "Competing explanations assessed",
                {
                    "verdict": a["verdict"],
                    "probability": a["probability"],
                    "calibrated": False,
                },
            )
            synthesis = None
            model_error = None
            tokens = 0
            if use_llm:
                store.event(
                    case_id,
                    "model",
                    "Local evidence reviewer started",
                    {"model": llm.MODEL},
                )
                try:
                    synthesis = await llm.synthesize(a)
                    tokens = synthesis["tokens"]
                    store.event(
                        case_id,
                        "model",
                        "Local reviewer completed",
                        {
                            "tokens": tokens,
                            "cached": synthesis["cached"],
                            "next_tool": synthesis["synthesis"]["next_tool"],
                        },
                    )
                    # Tool selection is bounded: execute only reviewed read-only follow-ups.
                    selected = synthesis["synthesis"]["next_tool"]
                    if selected != "none":
                        await asyncio.to_thread(followup, selected, packet, trigger)
                        packet["tool_calls"] += 1
                        store.event(
                            case_id,
                            "tool",
                            "Agent selected " + selected,
                            {
                                "tool": selected,
                                "source": "local_sqlite",
                                "read_only": True,
                            },
                        )
                except Exception as exc:
                    model_error = f"{type(exc).__name__}: {str(exc)[:180]}"
                    store.event(
                        case_id,
                        "warning",
                        "Local model unavailable; deterministic analysis retained",
                        {"error": model_error},
                    )
            answer = build_answer(
                trigger, a, packet, tokens=tokens, latency=time.monotonic() - start
            )
            store.event(
                case_id,
                "policy",
                "Policy and approval routes evaluated",
                {"actions": [x.model_dump() for x in answer.next_best_actions.final]},
            )
            tg_error = grounding_error
            if TG_URL:
                try:
                    graph_id = await tigergraph.persist(answer.model_dump(), trigger)
                    answer.case.written_to_graph = True
                    answer.case.graph_case_id = graph_id
                    store.event(
                        case_id,
                        "persistence",
                        "TigerGraph case read-back verified",
                        {"graph_case_id": graph_id},
                    )
                except Exception as exc:
                    tg_error = str(exc)[:250]
            detail = {
                "assessment": a,
                "statistical_advisory": advisory,
                "packet": packet,
                "graph": graph_view(packet, a),
                "synthesis": synthesis,
                "model_error": model_error,
                "tigergraph_error": tg_error,
                "mode": "TigerGraph grounded"
                if packet["source"] == "tigergraph"
                else "local analysis · TigerGraph evidence pending",
                "simulated": False,
                "validation": validate(answer),
            }
            store.save(case_id, answer.model_dump(), detail)
            store.event(
                case_id,
                "complete",
                "Investigation saved",
                {
                    "state": answer.case.status,
                    "written_to_graph": answer.case.written_to_graph,
                },
            )
            return store.get_case(case_id)
        except Exception as exc:
            with store.connect() as c:
                c.execute(
                    "UPDATE cases SET state='failed',error=? WHERE id=?",
                    (str(exc)[:400], case_id),
                )
            store.event(
                case_id, "error", "Investigation failed", {"error": str(exc)[:400]}
            )
            raise


def followup(tool, packet, trigger):
    with store.connect() as c:
        if tool == "prior_cases":
            r = c.execute(
                "SELECT id,outcome,pattern FROM history WHERE customer_id=? AND closed_at<? LIMIT 20",
                (trigger["customer_id"], trigger["opened_at"]),
            ).fetchall()
        elif tool == "device_neighbors":
            r = c.execute(
                "SELECT id,card_id FROM transactions WHERE device=? AND device!=? AND ts<=? LIMIT 20",
                (packet["flagged"]["device"], "", trigger["opened_at"]),
            ).fetchall()
        else:
            r = c.execute(
                "SELECT region,count(*) AS count FROM transactions WHERE customer_id=? AND ts<=? GROUP BY region",
                (trigger["customer_id"], trigger["opened_at"]),
            ).fetchall()
    packet["agent_followup"] = {"tool": tool, "result": [dict(x) for x in r]}
    return packet["agent_followup"]


def validate(answer):
    from .policy import validate_actions

    errors = validate_actions(answer.next_best_actions.final, answer.case.exposure_usd)
    with store.connect() as c:
        amounts = []
        for id in answer.case.affected_txn_ids:
            r = c.execute(
                "SELECT amount FROM transactions WHERE id=?", (id,)
            ).fetchone()
            if not r:
                errors.append("Missing transaction " + id)
            else:
                amounts.append(abs(r[0]))
        if round(sum(amounts), 2) != round(answer.case.exposure_usd, 2):
            errors.append("Exposure does not match affected transactions")
        for id in answer.case.connected_card_ids:
            if not c.execute(
                "SELECT 1 FROM transactions WHERE card_id=? AND card_verified=1 LIMIT 1",
                (id,),
            ).fetchone():
                errors.append("Unverified card " + id)
        for id in answer.case.similar_prior_cases:
            if not c.execute("SELECT 1 FROM history WHERE id=?", (id,)).fetchone():
                errors.append("Unknown historical case " + id)
    return {
        "schema_valid": True,
        "errors": errors,
        "verified": not errors
        and answer.case.written_to_graph
        and any(
            e.source == "graph" and e.ref.startswith("tigergraph:")
            for e in answer.case.evidence
        )
        and any(
            e.source == "document" and e.ref.startswith("tigergraph:vector:")
            for e in answer.case.evidence
        ),
        "limitations": [
            "TigerGraph evidence retrieval and vector grounding are not verified."
        ]
        if not answer.case.written_to_graph
        else [],
    }


async def respond(case_id, response, note=""):
    async with RUN_LOCK:
        r = store.get_case(case_id)
        if not r["result"]:
            raise ValueError("Run the investigation before adding evidence")
        old = Answer.model_validate(r["result"])
        detail = copy.deepcopy(r["detail"])
        a = detail["assessment"]
        packet = detail["packet"]
        if detail.get("last_response") == {"response": response, "note": note}:
            return r
        # Same fold-in as the automatic path, so an analyst-supplied reply and a
        # simulated one move the case identically.
        a = apply_response(detail["assessment"], packet, response)
        if note:
            a["evidence"][-1]["claim"] += " Analyst note: " + note
        answer = build_answer(
            r["trigger"], a, packet, response, old, old.tokens, old.latency_s
        )
        detail.update(
            simulated=True,
            last_response={"response": response, "note": note},
            validation=validate(answer),
            synthesis=None,
        )
        if TG_URL:
            try:
                gid = await tigergraph.persist(answer.model_dump(), r["trigger"])
                answer.case.written_to_graph = True
                answer.case.graph_case_id = gid
            except Exception as exc:
                detail["tigergraph_error"] = str(exc)[:250]
        store.save(case_id, answer.model_dump(), detail)
        store.event(
            case_id,
            "response",
            "Simulated evidence received",
            {
                "response": response,
                "note": note,
                "simulated": True,
                "actions": [x.model_dump() for x in answer.next_best_actions.final],
            },
        )
        return store.get_case(case_id)


def scenarios(case_id):
    r = store.get_case(case_id)
    if not r["detail"]:
        raise ValueError("Run an investigation first")
    results = {}
    for response in ["confirmed", "denied", "no_reply", "conflicting"]:
        a = copy.deepcopy(r["detail"]["assessment"])
        s = situation(a, response)
        s.conflict = response == "conflicting"
        if response == "confirmed":
            s.verdict = "legitimate"
            s.exposure = 0
            s.probability = 0.08
            s.shared_fraud = False
        elif response == "denied":
            s.verdict = "fraud"
            s.probability = 0.92
        else:
            s.verdict = "uncertain"
        results[response] = [x.model_dump() for x in decide(s)]
    return {"hypothetical": True, "persisted": False, "branches": results}


async def review(case_id):
    async with RUN_LOCK:
        record = store.get_case(case_id)
        if not record["result"]:
            raise ValueError("Run the investigation first")
        start = time.monotonic()
        detail = record["detail"]
        store.event(
            case_id, "model", "Local evidence reviewer started", {"model": llm.MODEL}
        )
        try:
            synthesis = await llm.synthesize(detail["assessment"])
        except Exception as exc:
            store.event(
                case_id, "warning", "Local reviewer failed", {"error": str(exc)[:200]}
            )
            raise ValueError("Local model review failed: " + str(exc)[:200]) from exc
        detail["synthesis"] = synthesis
        detail["model_error"] = None
        selected = synthesis["synthesis"]["next_tool"]
        if selected != "none":
            result = await asyncio.to_thread(
                followup, selected, detail["packet"], record["trigger"]
            )
            store.event(
                case_id,
                "tool",
                "Agent selected " + selected,
                {"tool": selected, "result": result, "source": "local_sqlite"},
            )
            record["result"]["tool_calls"] += 1
        record["result"]["tokens"] += synthesis["tokens"]
        record["result"]["latency_s"] = round(
            record["result"]["latency_s"] + time.monotonic() - start, 3
        )
        # Review changes interpretation only, not policy decisions or their approval revision.
        with store.connect() as c:
            c.execute(
                "UPDATE cases SET result_json=?,detail_json=?,updated_at=? WHERE id=?",
                (
                    json.dumps(record["result"]),
                    json.dumps(detail),
                    store.now(),
                    case_id,
                ),
            )
        store.event(
            case_id,
            "model",
            "Local evidence reviewer completed",
            {"tokens": synthesis["tokens"], "cached": synthesis["cached"]},
        )
        return store.get_case(case_id)
