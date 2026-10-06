"""Profile resolution hook for oan_auth_service's GET /api/v1/auth/me."""

import frappe

from da_services.services import constants as C
from da_services.utils.permissions import active_assignments


def resolve_user_profile_hook(user_doc, roles=None) -> tuple[str, dict | None]:
	"""Hook subscriber for oan_auth_service's on_user_profile.

	Returns ("da_services", profile_data) namespaced under data["profiles"]["da_services"]
	containing DA-specific scope that auth_service does not already provide.
	"""
	user = user_doc.name
	user_roles = set(roles or frappe.get_roles(user))
	da_roles = user_roles & set(C.DA_SERVICES_ROLES)

	if not da_roles:
		return "da_services", None

	assignments = active_assignments(user)
	regions: set[str] = set()
	woredas: set[str] = set()
	da_ids: set[str] = set()

	for row in assignments:
		if row.region_scope:
			regions.add(row.region_scope)
		if row.woreda_scope:
			woredas.add(row.woreda_scope)
		if row.role == C.ROLE_DA and row.da_id:
			da_ids.add(row.da_id)

	return "da_services", {
		"roles": sorted(da_roles),
		"scope": {
			"regions": sorted(regions),
			"woredas": sorted(woredas),
			"da_ids": sorted(da_ids),
		},
	}
