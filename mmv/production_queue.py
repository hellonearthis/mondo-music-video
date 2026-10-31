"""A queue of whole productions, run one at a time through the single-operation guard.

Each ticket is one atomic JSON file. Local work runs on the settings of the moment. Anything that
would cost money runs only on the exact plan and price that was approved, and is otherwise held.
"""
from __future__ import annotations

import threading
import time
import uuid

from .storage import identifier, read_json, write_json

QUEUEABLE_KINDS = ("video", "ident")
TERMINAL_STATES = ("complete", "failed", "cancelled", "interrupted", "held")
STOPPED_PAID_STATES = ("failed", "interrupted")
LOCAL_BACKENDS = ("local_h3", "comfy_sdk_h3")
RESUMABLE_STATES = ("failed", "cancelled", "interrupted", "held")


def _directory(store):
    return store.home / "queue"


def _path(store, ticket_id):
    return _directory(store) / (identifier(ticket_id) + ".json")


def read_tickets(store):
    """Every readable ticket in running order."""
    found = (read_json(path, None) for path in _directory(store).glob("*.json"))
    return sorted((ticket for ticket in found if ticket), key=lambda ticket: ticket["position"])


def save_ticket(store, ticket):
    write_json(_path(store, ticket["id"]), ticket)
    return ticket


def get_ticket(store, ticket_id):
    ticket = read_json(_path(store, ticket_id), None)
    if not ticket:
        raise ValueError("That ticket is not in the queue")
    return ticket


def remove_ticket(store, ticket_id):
    if get_ticket(store, ticket_id)["state"] == "running":
        raise ValueError("That ticket is running. Cancel the operation first")
    _path(store, ticket_id).unlink()


def new_ticket(request, label, position, *, estimate=0, fingerprint=None, now=None):
    """A pending ticket. Only a paid ticket carries approval, because only it needs any."""
    return {"id": uuid.uuid4().hex, "label": label, "kind": request["kind"], "backend": request.get("backend"),
            "request": request, "position": position, "state": "pending", "message": "", "run_id": None,
            "estimate_usd": estimate, "approved_fingerprint": fingerprint if estimate > 0 else None,
            "created": time.time() if now is None else now, "finished": None}


def next_position(tickets):
    return max((ticket["position"] for ticket in tickets), default=0) + 1


def next_pending(tickets):
    return next((ticket for ticket in tickets if ticket["state"] == "pending"), None)


def paid_stop_time(ticket):
    """When this ticket last stopped short. Putting it back in line does not undo that until it actually finishes."""
    if ticket["state"] == "complete":
        return 0
    return (ticket.get("finished") or 0) if ticket["state"] in STOPPED_PAID_STATES else ticket.get("stopped_at") or 0


def hold_reason(ticket, tickets, estimate, fingerprint):
    """Why this ticket may not spend money now, or None when it may run. Free work is never held."""
    if estimate <= 0:
        return None
    if not ticket.get("approved_fingerprint"):
        return f"This production now costs an estimated ${estimate:.2f}, which was never approved. Preview it again."
    if ticket["approved_fingerprint"] != fingerprint:
        return "Its inputs, settings or price changed after approval, so nothing was spent. Preview it again."
    # A failure stops approvals given before it. Approving again after seeing it is a fresh decision.
    if any(other["estimate_usd"] > 0 and paid_stop_time(other) >= ticket["created"] for other in tickets):
        return "An earlier paid ticket did not finish, so nothing was spent. Check it, then preview this one again."
    return None


def moved(tickets, ticket_id, delta):
    """Tickets with new positions after moving one up or down among those still waiting."""
    waiting = [ticket for ticket in tickets if ticket["state"] == "pending"]
    index = next((i for i, ticket in enumerate(waiting) if ticket["id"] == ticket_id), None)
    if index is None:
        raise ValueError("Only a waiting ticket can be moved")
    other = index + delta
    if not 0 <= other < len(waiting):
        return []
    first, second = waiting[index], waiting[other]
    return [{**first, "position": second["position"]}, {**second, "position": first["position"]}]


def resumable(ticket):
    """A local production that got as far as a run folder can continue from what it already made."""
    return ticket["state"] in RESUMABLE_STATES and bool(ticket.get("run_id")) and ticket.get("backend") in LOCAL_BACKENDS


def waiting_count(tickets):
    return sum(ticket["state"] == "pending" or (ticket["state"] == "interrupted" and resumable(ticket)) for ticket in tickets)


def resume_ticket(store, ticket):
    if not resumable(ticket):
        raise ValueError("Only a stopped local production that has a run folder can resume. Use Queue again")
    return save_ticket(store, {**ticket, "state": "pending", "resume_run": ticket["run_id"], "finished": None, "stopped_at": paid_stop_time(ticket),
                               "message": "Will continue from its saved work"})


def resume_interrupted(store):
    """Starting the queue is the operator's go-ahead to carry on with local work a stop cut short."""
    for ticket in read_tickets(store):
        if ticket["state"] == "interrupted" and resumable(ticket):
            resume_ticket(store, ticket)


def prompts_complete(directory):
    """Every passage has its saved prompt, so rendering can continue. Earlier than that, prompt work starts over from cache."""
    segments = read_json(directory / "prepared.json", {}).get("segments") or []
    prompts = read_json(directory / "prompts.json", {})
    return bool(segments) and all(prompts.get(f"seg{segment['index']:03d}") for segment in segments)


def resume_blocker(directory, fingerprint, consent):
    """Why a saved production must not continue as it stands, or None."""
    if fingerprint != consent.get("fingerprint"):
        return "Original inputs or settings changed; restore them before resuming"
    for path in (directory / "renders").glob("*/comfy-request.json"):
        receipt = read_json(path, {})
        if not receipt.get("job_id"):
            return "Submission outcome unknown. Reconcile the saved receipt with the proxy before resuming"
        if receipt.get("state") in ("failed", "canceled", "expired"):
            return "A Comfy job ended without a usable result; resume will not regenerate it"
    return None


def public_ticket(ticket):
    return {**{key: value for key, value in ticket.items() if key not in ("request", "approved_fingerprint")},
            "resumable": resumable(ticket)}


def recover_tickets(store, message_for):
    """A ticket still marked running at startup died with the application. Nothing is restarted."""
    for ticket in read_tickets(store):
        if ticket["state"] == "running":
            save_ticket(store, {**ticket, "state": "interrupted", "message": message_for(ticket["kind"]),
                                "finished": time.time()})


def _reason(store, error):
    """Same care as an operation failure: no response bodies or credentials reach the ticket."""
    message = str(error) if isinstance(error, ValueError) else type(error).__name__
    for secret in store.secret_values():
        message = message.replace(secret, "[redacted]")
    return message


def new_control():
    """The queue's in-memory state. Never saved: after a restart the queue waits to be started."""
    return {"running": False, "dispatching": False, "prepare_lock": threading.Lock()}


def cost(prepared):
    """What a plan may charge. The displayed estimate is rounded, so a tiny real cost must not read as free."""
    return max(prepared.get(key) or 0 for key in ("estimate", "render_estimate", "writer_estimate"))


def _claim_next(store, jobs, control):
    """The next ticket to prepare, or None after releasing the dispatcher when there is nothing to do now."""
    with jobs.lock:
        ticket = next_pending(read_tickets(store)) if control["running"] and jobs.active is None else None
        if ticket is None:
            if control["running"] and jobs.active is None:
                control["running"] = False
            control["dispatching"] = False
        return ticket


def _plan_resume(store, ticket, control):
    """The plan for continuing a saved run, or None when it never got far enough to continue."""
    from . import production
    from .services import check_required_services
    directory = store.home / "runs" / identifier(ticket["resume_run"])
    if (directory / "output.json").exists():
        return {"finished": True}
    consent = read_json(directory / "consent.json", {})
    if not consent.get("accepted") or not prompts_complete(directory):
        return None
    request = read_json(directory / "request.json", ticket["request"])
    with control["prepare_lock"]:
        prepared = production.prepare_resume(store, request, directory)
    fingerprint = production.fingerprint(store, request, prepared)
    return {"resume": True, "consent": consent, "request": request, "prepared": prepared, "fingerprint": fingerprint,
            "blocker": resume_blocker(directory, fingerprint, consent),
            "offline": check_required_services(store, request, resume=True)}


def _plan(store, ticket, control):
    """Long work, done outside the operation lock so status, Cancel and Pause keep answering."""
    from . import production
    from .services import check_required_services
    if ticket.get("resume_run"):
        plan = _plan_resume(store, ticket, control)
        if plan:
            return plan
    request = ticket["request"]
    with control["prepare_lock"]:
        prepared = production.prepare(store, request)
    return {"resume": False, "request": request, "prepared": prepared, "fingerprint": production.fingerprint(store, request, prepared),
            "offline": check_required_services(store, request)}


def _launch(store, jobs, control, ticket, plan, error):
    """Decide under the lock: stop the ticket, or start it. Returns True when the dispatcher is finished."""
    from . import production
    from .jobs import output_run_id
    with jobs.lock:
        if not control["running"] or jobs.active is not None:
            control["dispatching"] = False
            return True
        tickets = read_tickets(store)
        current = next((item for item in tickets if item["id"] == ticket["id"] and item["state"] == "pending"), None)
        if current is None:
            return False
        stopped = {**current, "finished": time.time()}
        if error is not None:
            save_ticket(store, {**stopped, "state": "failed", "message": _reason(store, error)})
            return False
        if plan.get("finished"):
            save_ticket(store, {**stopped, "state": "complete", "message": "Already finished before it stopped"})
            return False
        resume, prepared, fingerprint = plan["resume"], plan["prepared"], plan["fingerprint"]
        if resume:   # saved prompts, no writer calls, and only local renderers ever resume: nothing here can charge
            reason = plan["blocker"]
        elif current.get("resume_run") and cost(prepared) > 0:   # starting over would call a paid writer again
            reason = "It stopped before its prompts were finished and starting over may charge again. Preview it again."
        else:
            reason = hold_reason(current, tickets, cost(prepared), fingerprint)
        if reason:
            save_ticket(store, {**stopped, "state": "held", "message": reason})
            return False
        if plan["offline"]:
            save_ticket(store, {**stopped, "state": "failed", "message": f"Cannot start: {plan['offline'][0]}"})
            return False
        request = plan["request"]
        consent = plan["consent"] if resume else {   # a resume keeps the original approval on record
            "accepted": True, "accepted_at": time.time(), "estimate_usd": prepared["estimate"],
            "quote_id": "queue-" + current["id"], "fingerprint": fingerprint}
        run_id = current["resume_run"] if resume else output_run_id(store, request)
        ready = {**prepared, "consent": consent}
        jobs.start(request["kind"], lambda context: production.produce(store, request, ready, context, resume=resume), run_id=run_id)
        save_ticket(store, {**current, "state": "running", "run_id": run_id, "resume_run": None, "started": time.time()})
        control["dispatching"] = False
        return True


def dispatch(store, jobs, control):
    """Start the next runnable ticket if the queue is on and nothing else is running."""
    with jobs.lock:
        if control["dispatching"]:
            return
        control["dispatching"] = True
    try:
        while (ticket := _claim_next(store, jobs, control)) is not None:
            plan, error = None, None
            try:
                plan = _plan(store, ticket, control)
            except Exception as failure:
                error = failure
            if _launch(store, jobs, control, ticket, plan, error):
                return
    except Exception:
        with jobs.lock:   # an unusable queue folder must not leave the queue claiming to run
            control.update(running=False, dispatching=False)
        raise


def settle_operation(store, jobs, control, status):
    """Record the ticket an ended operation belonged to. Cancel means stop, not "skip to the next one"."""
    with jobs.lock:
        ticket = next((item for item in read_tickets(store)
                       if item["state"] == "running" and item["run_id"] == status.get("id")), None)
        if ticket:
            save_ticket(store, {**ticket, "state": status["state"], "message": status.get("message", ""), "finished": time.time()})
            if status["state"] == "cancelled":
                control["running"] = False


def start_dispatch(store, jobs, control):
    threading.Thread(target=dispatch, args=(store, jobs, control), daemon=True).start()
