"""v1: who am I, in DA Services terms.

Two surfaces share one implementation:

- ``GET /api/v1/da-services/me`` returns the caller's DA Services profile: roles, Region/Woreda
  scope, bound DA-ID, the DA record from the registry (for a Development Agent) and
  the sidebar sections the role may see.
- The ``on_user_profile`` hook in ``api/v1/profile.py`` (PR #4) gives oan_auth_service's
  ``GET /api/v1/auth/me`` the roles and scope under ``data.profiles.da_services``; this
  endpoint adds the registry record and the menu on top.

The menu is a convenience for the UI, not an authorisation control: every endpoint
still enforces the scope rule itself.
"""

from __future__ import annotations

import frappe
from oan_auth_service.api.utils import handle_api_errors, success_response

from da_services.api.router import route
from da_services.integrations.da_registry.client import DARegistryError, get_client
from da_services.services import constants as C
from da_services.utils.permissions import ScopeContext, require_roles

# Sidebar sections per role, using the portal's route slugs (FSD 2.4 navigation).
# Initial mapping; adjust as screens are confirmed per role.
MENU_BY_ROLE: dict[str, list[str]] = {
	C.ROLE_DA: [
		"dashboard",
		"farmers",
		"beneficiaries",
		"grievances",
		"visits",
		"my-teams",
		"feedback",
		"knowledge",
		"performance",
		"surveys",
		"profile",
		"sync",
	],
	C.ROLE_SUPERVISOR: [
		"dashboard",
		"agents",
		"approvals",
		"assignments",
		"farmers",
		"visits",
		"grievances",
		"feedback",
		"knowledge",
		"lifecycle",
		"kpis",
		"reviews",
		"surveys",
		"training",
		"profile",
	],
	C.ROLE_EXECUTIVE: ["dashboard", "agents", "kpis", "reviews", "admin/reports", "profile"],
	C.ROLE_ADMIN: [
		"dashboard",
		"agents",
		"approvals",
		"assignments",
		"registry-sync",
		"farmers",
		"visits",
		"grievances",
		"feedback",
		"knowledge",
		"broadcast",
		"alerts",
		"advisors",
		"lifecycle",
		"kpis",
		"reviews",
		"surveys",
		"training",
		"admin/users",
		"admin/reports",
		"admin/settings",
	],
	C.ROLE_COMMS: ["dashboard", "knowledge", "broadcast", "alerts", "profile"],
}


def menu_for(ctx: ScopeContext) -> list[str]:
	if ctx.unrestricted:
		return MENU_BY_ROLE[C.ROLE_ADMIN]
	seen: dict[str, None] = {}
	for role in C.DA_SERVICES_ROLES:
		if role in ctx.roles:
			for item in MENU_BY_ROLE[role]:
				seen.setdefault(item, None)
	return list(seen)


def profile_for(ctx: ScopeContext, include_agent: bool = True) -> dict:
	da_id = next(iter(sorted(ctx.da_ids)), None)
	data: dict = {
		"user": ctx.user,
		"roles": [r for r in C.DA_SERVICES_ROLES if r in ctx.roles],
		"unrestricted": ctx.unrestricted,
		"scope": {"regions": sorted(ctx.region_scopes), "woredas": sorted(ctx.woreda_scopes)},
		"da_id": da_id,
		"menu": menu_for(ctx),
	}
	if include_agent and da_id:
		try:
			data["agent"] = get_client().get_da(da_id).to_dict()
		except DARegistryError as exc:
			data["agent"] = None
			data["agent_error"] = f"registry unavailable: {exc.__class__.__name__}"
	return data


@route("/me", methods=("GET",), summary="Current user's DA Services profile: roles, scope, DA-ID, menu")
@frappe.whitelist()
@handle_api_errors
def get_me():
	ctx = require_roles(*C.DA_SERVICES_ROLES, *C.UNRESTRICTED_ROLES)
	return success_response(data=profile_for(ctx))
