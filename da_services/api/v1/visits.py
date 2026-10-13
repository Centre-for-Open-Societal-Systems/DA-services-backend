"""v1 visits: plan, list, detail, reschedule, cancel (docs/api-da-screens.md 2.7, 2.8; DA-43).

POST /api/v1/da-services/visits                      plan a visit (201)
GET  /api/v1/da-services/visits?date|from&to&status&farmer_id&da_id&limit&start
GET  /api/v1/da-services/visits/<visit_id>           one visit + status timeline
POST /api/v1/da-services/visits/<visit_id>/reschedule {scheduled_at | date+time, reason}
POST /api/v1/da-services/visits/<visit_id>/cancel     {reason}

Check-in and outcome (`/start`, `/outcome`) are DA-44. The plan body accepts either
`scheduled_at` or the form's separate `date` + `time`. `notify_farmer_sms` is recorded
on the visit; the SMS itself needs the gateway (not yet available) and is sent by a
later job, never from this request. `location` comes from the client (the farmer's
parcel, once the Farmer Registry API exists) and is stored as given.

Scope is enforced in services/visits.py: a DA acts on their own DA-ID, a Supervisor on
DAs in their Woreda (recorded as `assigned_by`), an Executive reads their Region.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import get_datetime
from oan_auth_service.api.utils import handle_api_errors, success_response

from da_services.api.router import route
from da_services.services import visits as svc
from da_services.utils.permissions import require_roles

PLAN_FIELDS = (
	"farmer_id",
	"scheduled_at",
	"date",
	"time",
	"visit_type",
	"purpose",
	"duration_min",
	"priority",
	"priority_reason",
	"plot_ref",
	"location",
	"notify_farmer_sms",
	"advisory_qa",
	"da_id",
	"client_op_id",
)


def _body(kwargs: dict, *names: str) -> dict:
	"""Request fields by name: the JSON body when there is one, else the call's kwargs."""
	request = getattr(frappe.local, "request", None)
	data = (request.get_json(silent=True) if request is not None else None) or {}
	out = {n: data.get(n, kwargs.get(n)) for n in names}
	for key in ("location", "advisory_qa"):
		if isinstance(out.get(key), str):
			try:
				out[key] = json.loads(out[key])
			except ValueError:
				frappe.throw(_("{0} must be JSON.").format(key), frappe.ValidationError)
	return out


def _scheduled_at(b: dict):
	"""`scheduled_at`, or the plan form's `date` + `time`."""
	if b.get("scheduled_at"):
		return get_datetime(b["scheduled_at"])
	if b.get("date"):
		return get_datetime(f"{b['date']} {b.get('time') or '09:00'}")
	return None


def _truthy(v) -> bool:
	return str(v).lower() in ("1", "true", "yes", "on")


_TERMINAL = ("Rescheduled", "Cancelled", "Missed", "Superseded")


def _timeline(visit: dict, meta: dict) -> list[dict]:
	"""Status history for the details modal, from the visit's own timestamps.

	Built from the record rather than Frappe's Version log so it is the same on every
	site (Version rows are skipped in tests and can be pruned).
	"""
	by = meta.get("created_by_user")
	entries = [{"label": "Planned", "by": by, "when": meta.get("creation"), "done": True}]
	if visit.get("assigned_by"):
		entries[0]["by"] = visit["assigned_by"]
	if visit.get("farmer_confirmation") == "Confirmed":
		entries.append({"label": "Confirmed", "by": None, "when": None, "done": True})
	if visit.get("started_at"):
		entries.append({"label": "In progress", "by": None, "when": visit["started_at"], "done": True})
	if visit.get("completed_at"):
		entries.append(
			{"label": "Physical Visit Complete", "by": None, "when": visit["completed_at"], "done": True}
		)
	status = visit.get("physical_status")
	if status in _TERMINAL:
		entries.append(
			{"label": status, "by": meta.get("modified_by"), "when": meta.get("modified"), "done": True}
		)
	for e in entries:
		if e["when"] is not None and hasattr(e["when"], "isoformat"):
			e["when"] = e["when"].isoformat()
	return entries


@route("/visits", methods=("POST",), status=201, summary="Plan a visit")
@frappe.whitelist(methods=["POST"])
@handle_api_errors
def plan(**kwargs):
	ctx = require_roles(*svc.WRITE_ROLES)
	b = _body(kwargs, *PLAN_FIELDS)
	out = svc.plan_visit(
		farmer_id=(b.get("farmer_id") or "").strip(),
		scheduled_at=_scheduled_at(b),
		visit_type=b.get("visit_type") or "Crop Survey",
		purpose=b.get("purpose"),
		duration_min=int(b.get("duration_min") or 45),
		priority=b.get("priority") or "Medium",
		priority_reason=b.get("priority_reason"),
		plot_ref=b.get("plot_ref"),
		location=b.get("location") or None,
		notify_farmer_sms=_truthy(b.get("notify_farmer_sms")),
		advisory_qa=b.get("advisory_qa") or None,
		da_id=b.get("da_id"),
		client_op_id=b.get("client_op_id") or None,
		ctx=ctx,
	)
	return success_response(data=out, message="Visit planned")


@route("/visits", methods=("GET",), summary="Visits the caller may see")
@frappe.whitelist()
@handle_api_errors
def list_visits(**kwargs):
	ctx = require_roles(*svc.READ_ROLES)
	q = _body(kwargs, "date", "from", "to", "status", "farmer_id", "da_id", "limit", "start")
	limit = int(q.get("limit") or 50)
	start = int(q.get("start") or 0)
	rows, total = svc.list_visits(
		ctx,
		date=q.get("date"),
		from_date=q.get("from"),
		to_date=q.get("to"),
		status=q.get("status"),
		farmer_id=q.get("farmer_id"),
		da_id=q.get("da_id"),
		limit=limit,
		start=start,
	)
	return success_response(data=rows, meta={"total": total, "limit": limit, "start": start})


@route("/visits/<visit_id>", methods=("GET",), summary="One visit with its status timeline")
@frappe.whitelist()
@handle_api_errors
def get_visit(visit_id: str):
	ctx = require_roles(*svc.READ_ROLES)
	out = svc.get_visit(visit_id, ctx)
	meta = (
		frappe.db.get_value(
			"DA Visit",
			visit_id,
			["creation", "created_by_user", "modified", "modified_by", "farmer_confirmation"],
			as_dict=True,
		)
		or {}
	)
	out["timeline"] = _timeline({**out, "farmer_confirmation": meta.get("farmer_confirmation")}, meta)
	return success_response(data=out)


@route("/visits/<visit_id>/reschedule", methods=("POST",), summary="Move a visit to a new time")
@frappe.whitelist(methods=["POST"])
@handle_api_errors
def reschedule(visit_id: str, **kwargs):
	ctx = require_roles(*svc.WRITE_ROLES)
	b = _body(kwargs, "scheduled_at", "date", "time", "reason")
	when = _scheduled_at(b)
	if not when:
		frappe.throw(_("scheduled_at (or date + time) is required."), frappe.ValidationError)
	out = svc.reschedule_visit(visit_id, scheduled_at=when, reason=b.get("reason"), ctx=ctx)
	return success_response(data=out, message="Visit rescheduled")


@route("/visits/<visit_id>/cancel", methods=("POST",), summary="Cancel a planned visit")
@frappe.whitelist(methods=["POST"])
@handle_api_errors
def cancel(visit_id: str, **kwargs):
	ctx = require_roles(*svc.WRITE_ROLES)
	b = _body(kwargs, "reason")
	out = svc.cancel_visit(visit_id, reason=b.get("reason"), ctx=ctx)
	return success_response(data=out, message="Visit cancelled")
