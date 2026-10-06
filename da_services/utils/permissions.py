"""Deny-by-default authorization (FSD 3.1.1, HLD 3 and 10.1).

A Frappe Role answers *what actions exist for you*. It never answers *which DAs you may
touch*. That is answered by the user's live DA RBAC Assignment rows: their Region, Zone
and Woreda scope and, for a Development Agent, the single DA-ID they are bound to. HLD 3
is explicit that "RBAC is necessary but not sufficient", so every service call passes
through here before it reads or writes anything.

UI visibility is not authorization. These checks run in the backend on every request,
and every denial is written to the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe
from frappe import _
from frappe.utils import today

from da_services.services import constants as C
from da_services.utils import audit


@dataclass(frozen=True)
class ScopeContext:
	"""What the signed-in user is allowed to reach, resolved once per request."""

	user: str
	roles: frozenset[str]
	unrestricted: bool
	region_scopes: frozenset[str] = field(default_factory=frozenset)
	zone_scopes: frozenset[str] = field(default_factory=frozenset)
	woreda_scopes: frozenset[str] = field(default_factory=frozenset)
	da_ids: frozenset[str] = field(default_factory=frozenset)

	def has_any_role(self, *roles: str) -> bool:
		return bool(self.roles & set(roles))

	def covers(self, region: str | None = None, woreda: str | None = None, zone: str | None = None) -> bool:
		"""True when the given Region / Zone / Woreda falls inside this user's scope.

		The narrowest grant wins: a Woreda grant covers that Woreda; a Zone grant covers
		every Woreda in the Zone; a Region-only grant covers the whole Region.
		Unrestricted roles cover everything.
		"""
		if self.unrestricted:
			return True
		if woreda and woreda in self.woreda_scopes:
			return True
		if zone and zone in self.zone_scopes:
			return True
		if region and region in self.region_scopes and not (self.woreda_scopes or self.zone_scopes):
			return True
		if region and region in self.region_scopes and woreda is None and zone is None:
			return True
		return False

	def owns_da(self, da_id: str) -> bool:
		return bool(da_id) and da_id in self.da_ids


def active_assignments(user: str | None = None) -> list[dict]:
	"""The user's live DA RBAC Assignment rows, honouring the effective date window."""
	user = user or frappe.session.user
	return frappe.get_all(
		"DA RBAC Assignment",
		filters={
			"user": user,
			"active": 1,
			"effective_from": ("<=", today()),
		},
		or_filters=[["effective_to", "is", "not set"], ["effective_to", ">=", today()]],
		fields=["name", "role", "region_scope", "zone_scope", "woreda_scope", "da_id"],
	)


def get_scope_context(user: str | None = None) -> ScopeContext:
	user = user or frappe.session.user
	roles = frozenset(frappe.get_roles(user))
	unrestricted = bool(roles & C.UNRESTRICTED_ROLES)

	regions: set[str] = set()
	zones: set[str] = set()
	woredas: set[str] = set()
	da_ids: set[str] = set()
	for row in active_assignments(user):
		if row.region_scope:
			regions.add(row.region_scope)
		if row.zone_scope:
			zones.add(row.zone_scope)
		if row.woreda_scope:
			woredas.add(row.woreda_scope)
		if row.role == C.ROLE_DA and row.da_id:
			da_ids.add(row.da_id)

	return ScopeContext(
		user=user,
		roles=roles,
		unrestricted=unrestricted,
		region_scopes=frozenset(regions),
		zone_scopes=frozenset(zones),
		woreda_scopes=frozenset(woredas),
		da_ids=frozenset(da_ids),
	)


def _deny(
	message: str, *, reason: str, entity_type: str | None = None, entity_name: str | None = None, **details
):
	audit.record(
		audit.ACCESS_DENIED,
		decision="denied",
		entity_type=entity_type,
		entity_name=entity_name,
		reason=reason,
		details=details or None,
	)
	frappe.throw(message, frappe.PermissionError)


def require_roles(*roles: str, user: str | None = None) -> ScopeContext:
	"""Raise PermissionError unless the user holds at least one of the roles."""
	ctx = get_scope_context(user)
	if ctx.user == "Guest" or not ctx.has_any_role(*roles):
		_deny(
			_("You do not have permission to perform this action."),
			reason="missing role",
			required_roles=sorted(roles),
		)
	return ctx


def require_da_access(
	da_id: str,
	region: str | None,
	woreda: str | None,
	ctx: ScopeContext | None = None,
	zone: str | None = None,
) -> ScopeContext:
	"""The one rule for touching a DA record.

	- Unrestricted roles: always.
	- Supervisor / Executive: only when the DA's Region / Zone / Woreda is inside their scope.
	- Development Agent: only their own DA-ID.
	- Anyone else (including Communications Officer): never.
	"""
	ctx = ctx or get_scope_context()
	if ctx.unrestricted:
		return ctx
	if ctx.has_any_role(C.ROLE_SUPERVISOR, C.ROLE_EXECUTIVE) and ctx.covers(region, woreda, zone):
		return ctx
	if ctx.has_any_role(C.ROLE_DA) and ctx.owns_da(da_id):
		return ctx
	_deny(
		_("DA {0} is outside your scope.").format(da_id),
		reason="out of scope",
		entity_type="DA",
		entity_name=da_id,
		da_region=region,
		da_zone=zone,
		da_woreda=woreda,
	)
	return ctx  # unreachable; keeps type checkers happy
