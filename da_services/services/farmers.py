"""Farmer profile and listing services (DA-40).

Business logic for farmer profile display, combining Farmer Registry data
with DA Visit history and permission checks.
"""

import frappe
from frappe import _

from da_services.integrations.farmer_registry import get_farmer_registry_client
from da_services.integrations.farmer_registry.mapper import (
	farmer_to_reference_dict,
	reference_dict_to_profile,
)
from da_services.services import constants as C
from da_services.utils.permissions import ScopeContext


def get_farmer_profile(farmer_id: str, ctx: ScopeContext) -> dict:
	"""Get complete farmer profile for DA-40 profile screen.

	Combines:
	- Farmer Registry data (cached in DA Farmer Reference)
	- DA Visit history (last visit, pending actions)
	- Edit permissions (for DA-41)

	Args:
	    farmer_id: Farmer Registry internal_record_id
	    ctx: Scope context with user permissions

	Returns:
	    Complete profile dict for frontend

	Raises:
	    DoesNotExistError: Farmer not found
	    PermissionError: Farmer not in scope
	"""
	# Get or sync farmer reference from cache
	ref = _get_or_sync_farmer_reference(farmer_id)
	if not ref:
		frappe.throw(_("Farmer {0} not found.").format(farmer_id), frappe.DoesNotExistError)

	# Check scope: Farmer must be in user's region/woreda
	if not ctx.unrestricted:
		# Get single woreda/region from the scopes set
		woreda_scope = next(iter(ctx.woreda_scopes), None) if ctx.woreda_scopes else None
		region_scope = next(iter(ctx.region_scopes), None) if ctx.region_scopes else None

		if woreda_scope and ref.get("woreda") != woreda_scope:
			frappe.throw(_("Farmer is not in your Woreda scope."), frappe.PermissionError)
		elif region_scope and ref.get("region") != region_scope:
			frappe.throw(_("Farmer is not in your Region scope."), frappe.PermissionError)

	# Get visit data (last visit, pending tasks)
	visit_data = _get_farmer_visit_data(farmer_id)

	# Check if farmer is editable by current DA
	can_edit = _can_edit_farmer(farmer_id, ctx)

	# Merge all data into profile
	profile = reference_dict_to_profile(ref, visit_data)
	profile["can_edit"] = can_edit
	da_ids_list = list(ctx.da_ids) if ctx.da_ids else []
	profile["is_linked"] = _is_farmer_linked_to_da(farmer_id, da_ids_list)

	return profile


def list_farmers(
	ctx: ScopeContext,
	*,
	woreda: str | None = None,
	kebele: str | None = None,
	state: str | None = None,
	da_id: str | None = None,
	limit: int = 50,
	start: int = 0,
) -> tuple[list, int]:
	"""List farmers visible to the user (DA-40 farmers list).

	Scope enforcement:
	- DA: Only linked farmers
	- Supervisor: All farmers in their Woreda
	- Executive: All farmers in their Region (read-only)
	- Admin: All farmers

	Args:
	    ctx: Scope context
	    woreda: Filter by woreda
	    kebele: Filter by kebele
	    state: Filter by registration state
	    da_id: Filter by linked DA
	    limit: Page size
	    start: Offset

	Returns:
	    (farmers list, total count)
	"""
	filters = {}

	# Scope filters
	if not ctx.unrestricted:
		if ctx.has_any_role(C.ROLE_DA):
			# DA sees only linked farmers
			da_ids_list = list(ctx.da_ids) if ctx.da_ids else []
			linked_farmer_ids = _get_linked_farmer_ids(da_ids_list)
			if not linked_farmer_ids:
				return [], 0
			filters["farmer_id"] = ("in", linked_farmer_ids)
		else:
			# For Supervisor/Executive, filter by their scope
			woreda_scope = next(iter(ctx.woreda_scopes), None) if ctx.woreda_scopes else None
			region_scope = next(iter(ctx.region_scopes), None) if ctx.region_scopes else None

			if woreda_scope:
				filters["woreda"] = woreda_scope
			elif region_scope:
				filters["region"] = region_scope

	# User filters
	if woreda:
		filters["woreda"] = woreda
	if kebele:
		filters["kebele"] = kebele
	if state:
		filters["registration_state"] = state

	# If filtering by DA, apply linked farmers
	if da_id:
		linked_to_da = frappe.get_all(
			"DA Farmer Link",
			filters={"da_id": da_id, "is_active": 1},
			pluck="farmer_id",
		)
		if linked_to_da:
			# Intersect with existing farmer_id filter if present
			if "farmer_id" in filters:
				existing = (
					filters["farmer_id"][1]
					if isinstance(filters["farmer_id"], tuple)
					else [filters["farmer_id"]]
				)
				filters["farmer_id"] = ("in", list(set(existing) & set(linked_to_da)))
			else:
				filters["farmer_id"] = ("in", linked_to_da)
		else:
			return [], 0

	# Query DA Farmer Reference
	farmers = frappe.get_all(
		"DA Farmer Reference",
		filters=filters,
		fields=[
			"farmer_id",
			"reg_id",
			"farmer_name",
			"phone",
			"kebele",
			"woreda",
			"region",
			"total_land_hectares",
			"registration_state",
			"registered_at",
		],
		order_by="farmer_name asc",
		limit=limit,
		start=start,
	)

	total = frappe.db.count("DA Farmer Reference", filters)

	# Enrich with visit counts
	for farmer in farmers:
		farmer["visit_count"] = _get_farmer_visit_count(farmer["farmer_id"])
		farmer["last_visit"] = _get_last_visit_date(farmer["farmer_id"])

	return farmers, total


def check_farmer_edit_permissions(farmer_id: str, ctx: ScopeContext) -> dict:
	"""Check if user can edit this farmer (DA-41 permission check).

	Args:
	    farmer_id: Farmer Registry internal_record_id
	    ctx: Scope context

	Returns:
	    {
	        "can_edit": bool,
	        "reason": str (if can_edit is False),
	        "is_linked": bool,
	        "link_type": str (Automatic/Manual)
	    }
	"""
	can_edit = _can_edit_farmer(farmer_id, ctx)
	da_ids_list = list(ctx.da_ids) if ctx.da_ids else []
	is_linked = _is_farmer_linked_to_da(farmer_id, da_ids_list)

	link = None
	if da_ids_list:
		link = frappe.db.get_value(
			"DA Farmer Link",
			{"farmer_id": farmer_id, "da_id": ("in", da_ids_list), "is_active": 1},
			["link_type"],
			as_dict=False,
		)

	reason = None
	if not can_edit:
		if not is_linked:
			reason = "Farmer is not linked or assigned to you"
		else:
			reason = "You do not have permission to edit this farmer"

	return {
		"can_edit": can_edit,
		"reason": reason,
		"is_linked": is_linked,
		"link_type": link if is_linked else None,
	}


def _get_or_sync_farmer_reference(farmer_id: str) -> dict | None:
	"""Get farmer from cache, or fetch and cache from registry.

	Args:
	    farmer_id: Farmer Registry internal_record_id

	Returns:
	    Farmer reference dict or None if not found
	"""
	# Check cache first
	cached = frappe.db.get_value(
		"DA Farmer Reference",
		farmer_id,
		"*",
		as_dict=True,
	)

	if cached:
		return cached

	# Not in cache, fetch from registry
	client = get_farmer_registry_client()
	farmer = client.get_farmer(farmer_id)

	if not farmer:
		return None

	# Cache it
	ref_dict = farmer_to_reference_dict(farmer)
	ref_dict["last_synced_at"] = frappe.utils.now_datetime()
	ref_dict["sync_version"] = 1

	doc = frappe.get_doc(
		{
			"doctype": "DA Farmer Reference",
			**ref_dict,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return doc.as_dict()


def _get_farmer_visit_data(farmer_id: str) -> dict:
	"""Get visit-related data for a farmer.

	Returns:
	    {
	        "last_visit_date": datetime,
	        "last_visit_outcome": str,
	        "pending_task_count": int,
	        "total_visits": int,
	    }
	"""
	# Get last completed visit
	last_visit = frappe.db.get_value(
		"DA Visit",
		{
			"farmer_id": farmer_id,
			"physical_status": "Physical Visit Complete",
		},
		["completed_at", "outcome"],
		as_dict=True,
		order_by="completed_at desc",
	)

	# Get pending tasks
	pending_tasks = frappe.db.count(
		"DA Task",
		{
			"farmer_id": farmer_id,
			"status": "Open",
		},
	)

	# Get total visits
	total_visits = frappe.db.count(
		"DA Visit",
		{"farmer_id": farmer_id},
	)

	return {
		"last_visit_date": last_visit.completed_at if last_visit else None,
		"last_visit_outcome": last_visit.outcome if last_visit else None,
		"pending_task_count": pending_tasks,
		"total_visits": total_visits,
	}


def _get_farmer_visit_count(farmer_id: str) -> int:
	"""Get total visit count for a farmer."""
	return frappe.db.count("DA Visit", {"farmer_id": farmer_id})


def _get_last_visit_date(farmer_id: str) -> str | None:
	"""Get last visit date for a farmer."""
	return frappe.db.get_value(
		"DA Visit",
		{"farmer_id": farmer_id},
		"scheduled_at",
		order_by="scheduled_at desc",
	)


def _can_edit_farmer(farmer_id: str, ctx: ScopeContext) -> bool:
	"""Check if user can edit this farmer (DA-41 rule).

	DA-41 rule: Only farmers linked or assigned to the DA are editable.

	Args:
	    farmer_id: Farmer ID
	    ctx: Scope context

	Returns:
	    True if editable
	"""
	if ctx.unrestricted:
		return True

	# Only DAs and Supervisors can edit
	if not ctx.has_any_role(C.ROLE_DA, C.ROLE_SUPERVISOR):
		return False

	# For DA role: Must be linked
	if ctx.has_any_role(C.ROLE_DA):
		return _is_farmer_linked_to_da(farmer_id, ctx.da_ids)

	# For Supervisor: Can edit any farmer in their woreda
	if ctx.has_any_role(C.ROLE_SUPERVISOR):
		woreda_scope = next(iter(ctx.woreda_scopes), None) if ctx.woreda_scopes else None
		if woreda_scope:
			farmer_woreda = frappe.db.get_value("DA Farmer Reference", farmer_id, "woreda")
			return farmer_woreda == woreda_scope

	return False


def _is_farmer_linked_to_da(farmer_id: str, da_ids: list) -> bool:
	"""Check if farmer is linked to any of the given DA IDs."""
	if not da_ids:
		return False

	return frappe.db.exists(
		"DA Farmer Link",
		{
			"farmer_id": farmer_id,
			"da_id": ("in", da_ids),
			"is_active": 1,
		},
	)


def _get_linked_farmer_ids(da_ids: list) -> list:
	"""Get all farmer IDs linked to the given DA IDs."""
	if not da_ids:
		return []

	return frappe.get_all(
		"DA Farmer Link",
		filters={"da_id": ("in", da_ids), "is_active": 1},
		pluck="farmer_id",
	)
