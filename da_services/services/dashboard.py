"""DA dashboard read models (docs/api-da-screens.md 2.1, DA-198).

Two calls feed the screen:

- ``summary(from, to)``: the three tiles. Farm visits and Tasks come from our DA Visit and
  DA Task rows; Sync status is what the server knows (queued integration events, visit
  attachments the device still owes or that clashed). The device merges its own queue count.
- ``today(date)``: Today's Plan, visits and tasks for one day merged into one list.

Scope: a DA sees their own DA-ID only; an officer must name the DA, and the DA's registry
posting must be inside their scope (get_da_reference enforces and audits that).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate

from da_services.services import constants as C
from da_services.services import tasks, visits
from da_services.services.da_lookup import get_da_reference
from da_services.utils.permissions import ScopeContext, require_roles

READ_ROLES = (C.ROLE_DA, C.ROLE_SUPERVISOR, C.ROLE_EXECUTIVE, C.ROLE_ADMIN)
DEFAULT_RANGE_DAYS = 30


def resolve_da(da_id: str | None, ctx: ScopeContext) -> str:
	"""The DA-ID the dashboard is about. A DA is always shown their own."""
	if ctx.has_any_role(C.ROLE_DA) and not ctx.unrestricted:
		own = sorted(ctx.da_ids)
		if not own:
			frappe.throw(_("Your account is not bound to a DA-ID."), frappe.PermissionError)
		return own[0]
	if not da_id:
		frappe.throw(_("da_id is required."), frappe.ValidationError)
	get_da_reference(da_id, ctx)  # PermissionError when outside the officer's scope
	return da_id


def sync_status(da_id: str, user: str) -> dict:
	"""Server-side half of the Sync tile.

	- server_pending / failed: integration events this user queued (grievance writes
	  waiting for the Grievance Service) still open or dead.
	- conflicts: visit attachments of this DA the server could not reconcile.
	- last_received_at: the last time the server accepted anything from this DA.
	"""
	pending = frappe.db.count(
		"DA Integration Event", {"owner": user, "status": ("in", ["Pending", "Processing"])}
	)
	failed = frappe.db.count("DA Integration Event", {"owner": user, "status": "Failed"})
	visit_names = frappe.get_all("DA Visit", filters={"da_id": da_id}, pluck="name")
	conflicts = 0
	if visit_names:
		conflicts = frappe.db.count(
			"DA Visit Attachment",
			{"parent": ("in", visit_names), "sync_state": ("in", ["Conflict", "Dead letter"])},
		)
	stamps = []
	for dt in ("DA Visit", "DA Task"):
		latest = frappe.get_all(
			dt, filters={"da_id": da_id}, pluck="modified", order_by="modified desc", limit_page_length=1
		)
		if latest:
			stamps.append(get_datetime(latest[0]))
	return {
		"server_pending": pending,
		"failed": failed,
		"conflicts": conflicts,
		"last_received_at": max(stamps).isoformat() if stamps else None,
	}


def summary(
	ctx: ScopeContext | None = None, *, from_date=None, to_date=None, da_id: str | None = None
) -> dict:
	ctx = ctx or require_roles(*READ_ROLES)
	da_id = resolve_da(da_id, ctx)
	to_d = getdate(to_date) if to_date else getdate()
	from_d = getdate(from_date) if from_date else add_days(to_d, -(DEFAULT_RANGE_DAYS - 1))
	if from_d > to_d:
		frappe.throw(_("from must not be after to."), frappe.ValidationError)
	return {
		"da_id": da_id,
		"range": {"from": str(from_d), "to": str(to_d)},
		"visits": visits.dashboard_counts(da_id, from_d, to_d),
		"tasks": tasks.dashboard_counts(da_id, from_d, to_d),
		"sync": sync_status(da_id, ctx.user),
	}


def _task_items(da_id: str, date) -> list[dict]:
	d = getdate(date)
	rows = frappe.get_all(
		"DA Task",
		filters={
			"da_id": da_id,
			"due_at": ("between", [f"{d} 00:00:00", f"{d} 23:59:59"]),
			"status": ("in", ["Open", "Done"]),
		},
		fields=["name", "title", "task_type", "due_at", "status", "priority", "farmer_id"],
		order_by="due_at asc",
	)
	items = []
	for r in rows:
		if r.status == "Done":
			status = "Done"
		elif d < getdate():
			status = "Overdue"
		else:
			status = "Due today" if d == getdate() else "Upcoming"
		items.append(
			{
				"kind": "task",
				"id": r.name,
				"time": get_datetime(r.due_at).strftime("%H:%M") if r.due_at else None,
				"title": r.title,
				"subtitle": r.task_type + (f" · {r.farmer_id}" if r.farmer_id else ""),
				"status": status,
				"priority": r.priority,
				"href": f"/tasks/{r.name}",
			}
		)
	return items


def today(ctx: ScopeContext | None = None, *, date=None, da_id: str | None = None) -> dict:
	ctx = ctx or require_roles(*READ_ROLES)
	da_id = resolve_da(da_id, ctx)
	d = getdate(date) if date else getdate()
	items = visits.today_items(da_id, d) + _task_items(da_id, d)
	# Timed entries first in clock order, undated tasks at the end.
	items.sort(key=lambda i: (i["time"] is None, i["time"] or "", i["kind"]))
	return {"da_id": da_id, "date": str(d), "items": items}
