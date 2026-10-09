"""DA Visit use-cases behind the dashboard, planner and outcome form (data-model 5.3).

Scope (FSD Appendix D): a DA plans, starts and submits visits for their own DA-ID; a
Supervisor may plan for a DA in their Woreda (recorded in `assigned_by`) and read the
Woreda's visits; an Executive reads their Region; OAN Administrator is unrestricted;
Communications Officer has no access.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime

from da_services.da_services.doctype.da_visit.da_visit import COMPLETE, OPEN_STATES, PLANNED_STATES
from da_services.services import constants as C
from da_services.services.da_lookup import get_da_reference
from da_services.utils.permissions import ScopeContext, require_roles

WRITE_ROLES = (C.ROLE_DA, C.ROLE_SUPERVISOR, C.ROLE_ADMIN)
READ_ROLES = (C.ROLE_DA, C.ROLE_SUPERVISOR, C.ROLE_EXECUTIVE, C.ROLE_ADMIN)

FIELDS = [
	"name",
	"da_id",
	"farmer_id",
	"visit_type",
	"physical_status",
	"purpose",
	"scheduled_at",
	"duration_min",
	"priority",
	"priority_reason",
	"source",
	"assigned_by",
	"farmer_confirmation",
	"confirmation_note",
	"plot_ref",
	"location_lat",
	"location_lng",
	"rescheduled_from",
	"arrived_at",
	"started_at",
	"completed_at",
	"outcome",
	"next_action_type",
	"next_action_date",
	"follow_up_task",
	"follow_up_visit",
	"region",
	"woreda",
	"kebele",
	"client_op_id",
	"modified",
]
_DT = ("scheduled_at", "arrived_at", "started_at", "completed_at", "modified")


def _derived(row: dict) -> dict:
	status = row.get("physical_status")
	sched = row.get("scheduled_at")
	if status == COMPLETE:
		ui, planner = "Completed", "completed"
	elif status == "Missed":
		ui, planner = "Missed", "scheduled"
	elif status in OPEN_STATES:
		ui = "Confirmed" if row.get("farmer_confirmation") == "Confirmed" else "Planned"
		planner = "overdue" if sched and get_datetime(sched) < now_datetime() else "scheduled"
	else:
		ui, planner = status, "scheduled"
	return {"ui_status": ui, "planner_status": planner}


def serialize(doc) -> dict:
	out = {f: doc.get(f) for f in FIELDS}
	for f in _DT:
		if out.get(f) is not None and hasattr(out[f], "isoformat"):
			out[f] = out[f].isoformat()
	out.update(
		_derived(
			{
				"physical_status": doc.get("physical_status"),
				"scheduled_at": doc.get("scheduled_at"),
				"farmer_confirmation": doc.get("farmer_confirmation"),
			}
		)
	)
	if hasattr(doc, "get_doc_before_save"):  # a Document, not a list row
		out["advisory_qa"] = [
			{"question": r.question, "answer": r.answer} for r in (doc.get("advisory_qa") or [])
		]
		out["attachments"] = [
			{
				"file": r.file,
				"kind": r.kind,
				"captured_at": r.captured_at.isoformat() if r.captured_at else None,
			}
			for r in (doc.get("attachments") or [])
		]
	return out


def _resolve_da_for_write(da_id: str | None, ctx: ScopeContext) -> tuple[str, str | None]:
	"""(da_id, assigned_by). A DA acts on their own DA-ID; an officer names a DA in scope."""
	if ctx.has_any_role(C.ROLE_DA) and not ctx.unrestricted:
		own = sorted(ctx.da_ids)
		if not own:
			frappe.throw(_("Your account is not bound to a DA-ID."), frappe.PermissionError)
		return own[0], None
	if not da_id:
		frappe.throw(_("da_id is required."), frappe.ValidationError)
	get_da_reference(da_id, ctx)  # raises PermissionError when out of scope, audited
	return da_id, ctx.user


def plan_visit(
	*,
	farmer_id: str,
	scheduled_at,
	visit_type: str = "Crop Survey",
	purpose: str | None = None,
	duration_min: int = 45,
	priority: str = "Medium",
	priority_reason: str | None = None,
	plot_ref: str | None = None,
	location: dict | None = None,
	notify_farmer_sms: bool = False,
	advisory_qa: list[dict] | None = None,
	da_id: str | None = None,
	client_op_id: str | None = None,
	ctx: ScopeContext | None = None,
) -> dict:
	ctx = ctx or require_roles(*WRITE_ROLES)
	if not farmer_id:
		frappe.throw(_("farmer_id is required."), frappe.ValidationError)
	if not scheduled_at:
		frappe.throw(_("scheduled_at is required."), frappe.ValidationError)
	da_id, assigned_by = _resolve_da_for_write(da_id, ctx)

	if client_op_id:
		existing = frappe.db.get_value("DA Visit", {"client_op_id": client_op_id}, "name")
		if existing:
			return serialize(frappe.get_doc("DA Visit", existing))

	location = location or {}
	doc = frappe.get_doc(
		{
			"doctype": "DA Visit",
			"da_id": da_id,
			"farmer_id": farmer_id,
			"visit_type": visit_type or "Crop Survey",
			"purpose": purpose,
			"scheduled_at": get_datetime(scheduled_at),
			"duration_min": int(duration_min or 45),
			"priority": priority or "Medium",
			"priority_reason": priority_reason,
			"plot_ref": plot_ref,
			"location_lat": location.get("lat"),
			"location_lng": location.get("lng"),
			"notify_farmer_sms": 1 if notify_farmer_sms else 0,
			"source": "Planned",
			"assigned_by": assigned_by,
			"client_op_id": client_op_id,
		}
	)
	if visit_type == "Advisory":
		for row in advisory_qa or []:
			if (row.get("question") or "").strip():
				doc.append(
					"advisory_qa",
					{"question": row["question"].strip(), "answer": (row.get("answer") or "").strip()},
				)
	doc.insert(ignore_permissions=True)
	return serialize(doc)


def _load_in_scope(name: str, ctx: ScopeContext, write: bool = False):
	doc = frappe.get_doc("DA Visit", name)
	if ctx.unrestricted:
		return doc
	if ctx.has_any_role(C.ROLE_DA):
		if ctx.owns_da(doc.da_id):
			return doc
	elif ctx.has_any_role(C.ROLE_SUPERVISOR) and ctx.covers(doc.region, doc.woreda):
		return doc
	elif not write and ctx.has_any_role(C.ROLE_EXECUTIVE) and ctx.covers(doc.region, doc.woreda):
		return doc
	frappe.throw(_("Visit {0} is outside your scope.").format(name), frappe.PermissionError)


def get_visit(name: str, ctx: ScopeContext | None = None) -> dict:
	ctx = ctx or require_roles(*READ_ROLES)
	return serialize(_load_in_scope(name, ctx))


def start_visit(
	name: str, *, arrived_at=None, gps: dict | None = None, farmer_present: bool = True, ctx=None
) -> dict:
	ctx = ctx or require_roles(*WRITE_ROLES)
	doc = _load_in_scope(name, ctx, write=True)
	doc.flags.ignore_permissions = True
	doc.start_visit(arrived_at=arrived_at, gps=gps, farmer_present=farmer_present)
	return serialize(doc)


def submit_outcome(name: str, *, ctx=None, **outcome) -> dict:
	ctx = ctx or require_roles(*WRITE_ROLES)
	doc = _load_in_scope(name, ctx, write=True)
	doc.flags.ignore_permissions = True
	doc.submit_outcome(**outcome)
	doc.reload()
	return serialize(doc)


def reschedule_visit(name: str, *, scheduled_at, reason: str | None = None, ctx=None) -> dict:
	ctx = ctx or require_roles(*WRITE_ROLES)
	doc = _load_in_scope(name, ctx, write=True)
	doc.flags.ignore_permissions = True
	new = doc.reschedule(scheduled_at, reason)
	return serialize(new)


def cancel_visit(name: str, *, reason: str | None = None, ctx=None) -> dict:
	ctx = ctx or require_roles(*WRITE_ROLES)
	doc = _load_in_scope(name, ctx, write=True)
	doc.flags.ignore_permissions = True
	doc.cancel_visit(reason)
	return serialize(doc)


def list_visits(
	ctx: ScopeContext | None = None,
	*,
	from_date=None,
	to_date=None,
	date=None,
	status: str | None = None,
	farmer_id: str | None = None,
	da_id: str | None = None,
	limit: int = 50,
	start: int = 0,
) -> tuple[list[dict], int]:
	"""Visits the caller may see (scope via permission_query_conditions). `status` may be a
	physical_status or a UI chip (Planned / Confirmed / Completed / Missed)."""
	ctx = ctx or require_roles(*READ_ROLES)
	filters: dict = {}
	if date:
		d = getdate(date)
		filters["scheduled_at"] = ("between", [f"{d} 00:00:00", f"{d} 23:59:59"])
	elif from_date and to_date:
		filters["scheduled_at"] = (
			"between",
			[f"{getdate(from_date)} 00:00:00", f"{getdate(to_date)} 23:59:59"],
		)
	if farmer_id:
		filters["farmer_id"] = farmer_id
	if da_id:
		filters["da_id"] = da_id
	if status == "Completed":
		filters["physical_status"] = COMPLETE
	elif status == "Planned":
		filters["physical_status"] = ("in", list(OPEN_STATES))
	elif status:
		filters["physical_status"] = status

	limit = max(1, min(int(limit), 500))
	start = max(0, int(start))
	rows = frappe.get_list(
		"DA Visit",
		filters=filters,
		fields=[*FIELDS, "farmer_confirmation"],
		order_by="scheduled_at asc",
		limit_page_length=limit,
		limit_start=start,
	)
	total = len(frappe.get_list("DA Visit", filters=filters, pluck="name", limit_page_length=0))
	return [serialize(frappe._dict(r)) for r in rows], total


def dashboard_counts(da_id: str, from_date, to_date) -> dict:
	"""Farm visits tile: planned (everything meant to happen in the range) vs completed."""
	rng = ("between", [f"{getdate(from_date)} 00:00:00", f"{getdate(to_date)} 23:59:59"])
	return {
		"planned": frappe.db.count(
			"DA Visit", {"da_id": da_id, "scheduled_at": rng, "physical_status": ("in", list(PLANNED_STATES))}
		),
		"completed": frappe.db.count(
			"DA Visit", {"da_id": da_id, "scheduled_at": rng, "physical_status": COMPLETE}
		),
	}


def today_items(da_id: str, date=None) -> list[dict]:
	"""Visit rows for Today's Plan (merged with tasks in the dashboard service)."""
	d = getdate(date) if date else getdate()
	rows = frappe.get_all(
		"DA Visit",
		filters={
			"da_id": da_id,
			"scheduled_at": ("between", [f"{d} 00:00:00", f"{d} 23:59:59"]),
			"physical_status": ("in", [*OPEN_STATES, COMPLETE, "Missed"]),
		},
		fields=[
			"name",
			"farmer_id",
			"kebele",
			"visit_type",
			"purpose",
			"scheduled_at",
			"physical_status",
			"farmer_confirmation",
		],
		order_by="scheduled_at asc",
	)
	items = []
	for r in rows:
		d_ = _derived(r)
		items.append(
			{
				"kind": "visit",
				"id": r.name,
				"time": get_datetime(r.scheduled_at).strftime("%H:%M") if r.scheduled_at else None,
				"title": f"Farm visit: {r.farmer_id}" + (f", {r.kebele}" if r.kebele else ""),
				"subtitle": r.purpose or r.visit_type,
				"status": "Done"
				if d_["ui_status"] == "Completed"
				else ("Overdue" if d_["planner_status"] == "overdue" else "Upcoming"),
				"href": f"/visits/{r.name}",
			}
		)
	return items
