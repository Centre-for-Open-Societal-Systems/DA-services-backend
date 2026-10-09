"""Frappe permission hooks for the app's own doctypes (deny-by-default).

The query condition filters list views, reports and the REST API uniformly;
has_permission mirrors it for a single document. Both are registered in hooks.py.
"""

import frappe

from da_services.services import constants as C
from da_services.utils.permissions import get_scope_context

DENY = "1=0"


def _is_unrestricted(user: str) -> bool:
	return bool(set(frappe.get_roles(user)) & C.UNRESTRICTED_ROLES)


def _sql_in(values) -> str:
	return ", ".join(frappe.db.escape(v) for v in sorted(values))


def da_scoped_query_conditions(doctype: str, user: str | None = None) -> str:
	"""List filter for operational doctypes that carry `da_id`, `region`, `woreda`.

	Same rule as utils.permissions.ScopeContext: a DA sees rows for their own DA-ID; a
	Supervisor / Executive sees rows whose posting codes fall inside their grants, the
	narrowest grant winning; a Zone-only grant cannot be resolved against rows that carry
	no zone, so it yields nothing (no silent widening to the Region); Communications
	Officer and anyone without a grant see nothing. Unrestricted roles see everything.
	"""
	user = user or frappe.session.user
	ctx = get_scope_context(user)
	if ctx.unrestricted:
		return ""
	t = f"`tab{doctype}`"
	if ctx.has_any_role(C.ROLE_DA):
		if not ctx.da_ids:
			return DENY
		return f"{t}.`da_id` in ({_sql_in(ctx.da_ids)})"
	if ctx.has_any_role(C.ROLE_SUPERVISOR, C.ROLE_EXECUTIVE):
		if ctx.woreda_scopes:
			return f"{t}.`woreda` in ({_sql_in(ctx.woreda_scopes)})"
		if ctx.zone_scopes:
			return DENY  # scope unresolved: rows carry no zone
		if ctx.region_scopes:
			return f"{t}.`region` in ({_sql_in(ctx.region_scopes)})"
	return DENY


def has_da_scoped_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	"""Single-document mirror of da_scoped_query_conditions. Executive is read-only."""
	user = user or frappe.session.user
	ctx = get_scope_context(user)
	if ctx.unrestricted:
		return True
	if ctx.has_any_role(C.ROLE_DA):
		return ctx.owns_da(doc.da_id)
	if ctx.has_any_role(C.ROLE_SUPERVISOR):
		return ctx.covers(doc.region, doc.woreda)
	if ctx.has_any_role(C.ROLE_EXECUTIVE):
		return ptype == "read" and ctx.covers(doc.region, doc.woreda)
	return False


def da_task_query_conditions(user: str | None = None) -> str:
	return da_scoped_query_conditions("DA Task", user)


def has_da_task_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	return has_da_scoped_permission(doc, ptype, user)


def rbac_assignment_query_conditions(user: str | None = None) -> str:
	"""Administrators see every grant; everyone else sees only their own rows."""
	user = user or frappe.session.user
	if _is_unrestricted(user):
		return ""
	return "`tabDA RBAC Assignment`.`user` = {user}".format(user=frappe.db.escape(user))


def has_rbac_assignment_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
	user = user or frappe.session.user
	if _is_unrestricted(user):
		return True
	# Non-administrators may only read, and only their own grants.
	return ptype == "read" and doc.user == user
