"""In-app notifications (data-model 5.10): the bell on the portal and mobile app.

Other services call ``notify(...)`` (or ``notify_da(...)`` when they only know the DA-ID);
the API reads a user's own rows. SMS / Telegram delivery is a later concern recorded on
the same row (channel, delivery_status) so one event can go out on several channels.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from da_services.services import constants as C
from da_services.utils.permissions import ScopeContext, require_roles

KINDS = (
	"Visit",
	"Task",
	"Sync",
	"Grievance",
	"Broadcast",
	"Issue",
	"Assignment",
	"Onboarding",
	"Approval",
	"System",
)

FIELDS = [
	"name",
	"kind",
	"title",
	"body",
	"href",
	"read",
	"read_at",
	"event",
	"reference_doctype",
	"reference_name",
	"creation",
]


def serialize(row) -> dict:
	out = {f: row.get(f) for f in FIELDS}
	out["id"] = out.pop("name")
	out["read"] = bool(out["read"])
	out["at"] = out.pop("creation")
	for f in ("at", "read_at"):
		if out.get(f) is not None and hasattr(out[f], "isoformat"):
			out[f] = out[f].isoformat()
	return out


def user_for_da(da_id: str) -> str | None:
	"""The user bound to a DA-ID through an active Development Agent assignment."""
	rows = frappe.get_all(
		"DA RBAC Assignment",
		filters={"da_id": da_id, "role": C.ROLE_DA, "active": 1},
		fields=["user"],
		order_by="modified desc",
		limit_page_length=1,
	)
	return rows[0].user if rows else None


def notify(
	user: str,
	*,
	kind: str,
	title: str,
	body: str | None = None,
	href: str | None = None,
	event: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	da_id: str | None = None,
	channel: str = "App",
) -> str:
	"""Create one notification row for `user`. Returns its name."""
	if kind not in KINDS:
		frappe.throw(_("Unknown notification kind {0}.").format(kind))
	doc = frappe.get_doc(
		{
			"doctype": "DA Notification",
			"user": user,
			"kind": kind,
			"title": title[:140],
			"body": body,
			"href": href,
			"event": event,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"da_id": da_id,
			"channel": channel,
			"delivery_status": "Not sent",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def notify_da(da_id: str, **kwargs) -> str | None:
	"""notify() addressed by DA-ID; skips silently when no user is bound yet (pre-provisioning)."""
	user = user_for_da(da_id)
	if not user:
		return None
	return notify(user, da_id=da_id, **kwargs)


def list_notifications(
	ctx: ScopeContext | None = None, *, unread: bool = False, limit: int = 20, start: int = 0
) -> tuple[list[dict], dict]:
	"""A user's own notifications, newest first, plus meta {unread_count, limit, start}."""
	ctx = ctx or require_roles(*C.DA_SERVICES_ROLES)
	filters: dict = {"user": ctx.user}
	if unread:
		filters["read"] = 0
	limit = max(1, min(int(limit), 100))
	start = max(0, int(start))
	rows = frappe.get_all(
		"DA Notification",
		filters=filters,
		fields=FIELDS,
		order_by="creation desc",
		limit_page_length=limit,
		limit_start=start,
	)
	unread_count = frappe.db.count("DA Notification", {"user": ctx.user, "read": 0})
	return [serialize(r) for r in rows], {"unread_count": unread_count, "limit": limit, "start": start}


def mark_read(name: str, ctx: ScopeContext | None = None) -> dict:
	ctx = ctx or require_roles(*C.DA_SERVICES_ROLES)
	doc = frappe.get_doc("DA Notification", name)
	if doc.user != ctx.user and not ctx.unrestricted:
		frappe.throw(_("Notification {0} is not yours.").format(name), frappe.PermissionError)
	if not doc.read:
		doc.read = 1
		doc.read_at = now_datetime()
		doc.flags.ignore_permissions = True
		doc.save()
	return serialize(doc)


def mark_all_read(ctx: ScopeContext | None = None) -> dict:
	ctx = ctx or require_roles(*C.DA_SERVICES_ROLES)
	names = frappe.get_all("DA Notification", filters={"user": ctx.user, "read": 0}, pluck="name")
	now = now_datetime()
	for name in names:
		frappe.db.set_value("DA Notification", name, {"read": 1, "read_at": now}, update_modified=True)
	return {"updated": len(names)}
