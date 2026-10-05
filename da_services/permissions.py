"""Frappe permission hooks for the app's own doctypes (deny-by-default).

The query condition filters list views, reports and the REST API uniformly;
has_permission mirrors it for a single document. Both are registered in hooks.py.
"""

import frappe

from da_services.services import constants as C


def _is_unrestricted(user: str) -> bool:
	return bool(set(frappe.get_roles(user)) & C.UNRESTRICTED_ROLES)


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
