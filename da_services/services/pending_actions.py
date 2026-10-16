"""Pending action state derivation for DA-39.

Determines what action is pending for each farmer based on:
1. Fayda verification status (from Farmer Registry via DA Farmer Reference)
2. Credit application status (from A2C)
3. Visit history - crop survey due (from DA Visit table)
4. Visit history - livestock survey due (from DA Visit table)

NO integration with Crop/Livestock Registries needed - uses visit frequency only.

Priority order (highest first):
1. Fayda check - verification pending/mismatch
2. Credit in review - active application exists
3. Crop survey due - no crop survey in threshold days
4. Livestock due - no livestock survey in threshold days
5. No action due - default state
"""

from datetime import datetime
from typing import Literal

import frappe
from frappe.utils import get_datetime, now_datetime

from da_services.integrations.a2c import get_a2c_client

# Type definitions
PendingActionState = Literal[
	"Crop survey due", "Livestock due", "Credit in review", "Fayda check", "No action due"
]

PendingActionPriority = Literal["high", "medium", "low"]

# Business rules - thresholds for survey due dates
# TODO: Move to DA Settings doctype for configurability
CROP_SURVEY_DUE_DAYS = 30
LIVESTOCK_SURVEY_DUE_DAYS = 60


class PendingActionResult:
	"""Result of pending action derivation."""

	def __init__(
		self,
		state: PendingActionState,
		priority: PendingActionPriority,
		reason: str | None = None,
		days_overdue: int | None = None,
	):
		self.state = state
		self.priority = priority
		self.reason = reason
		self.days_overdue = days_overdue

	def to_dict(self) -> dict:
		"""Convert to dict for API response."""
		result = {"state": self.state, "priority": self.priority}
		if self.reason:
			result["reason"] = self.reason
		if self.days_overdue is not None:
			result["days_overdue"] = self.days_overdue
		return result


def derive_pending_action(farmer_id: str, farmer_data: dict | None = None) -> PendingActionResult:
	"""Derive pending action state for a farmer (DA-39).

	Args:
	    farmer_id: Farmer Registry internal_record_id
	    farmer_data: Optional farmer reference dict (to avoid re-query)

	Returns:
	    PendingActionResult with state, priority, reason
	"""
	# Priority 1: Check Fayda verification status
	fayda_result = _check_fayda_status(farmer_id, farmer_data)
	if fayda_result:
		return fayda_result

	# Priority 2: Check credit application status
	credit_result = _check_credit_status(farmer_id)
	if credit_result:
		return credit_result

	# Priority 3: Check crop survey status (visit-based)
	crop_result = _check_crop_survey_due(farmer_id)
	if crop_result:
		return crop_result

	# Priority 4: Check livestock survey status (visit-based)
	livestock_result = _check_livestock_survey_due(farmer_id)
	if livestock_result:
		return livestock_result

	# Priority 5: Default - no action due
	return PendingActionResult(state="No action due", priority="low", reason=None)


def derive_pending_actions_batch(farmer_ids: list[str]) -> dict[str, PendingActionResult]:
	"""Derive pending actions for multiple farmers (optimized batch).

	Args:
	    farmer_ids: List of farmer IDs

	Returns:
	    Dict mapping farmer_id -> PendingActionResult
	"""
	if not farmer_ids:
		return {}

	# Batch 1: Load farmer references (for registration status)
	farmer_refs = frappe.get_all(
		"DA Farmer Reference",
		filters={"farmer_id": ["in", farmer_ids]},
		fields=["farmer_id", "registration_state"],
	)
	farmer_map = {f["farmer_id"]: f for f in farmer_refs}

	# Batch 2: Load last crop surveys
	crop_visits = _get_last_visits_batch(farmer_ids, "Crop Survey")

	# Batch 3: Load last livestock surveys
	livestock_visits = _get_last_visits_batch(farmer_ids, "Livestock Survey")

	# Batch 4: Check credit applications
	credit_map = {}
	a2c_client = get_a2c_client()
	for farmer_id in farmer_ids:
		try:
			credit_map[farmer_id] = a2c_client.has_active_application(farmer_id)
		except Exception:
			credit_map[farmer_id] = False

	# Derive pending action for each farmer
	results = {}
	for farmer_id in farmer_ids:
		farmer_data = farmer_map.get(farmer_id)
		result = None

		# Priority 1: Fayda check
		if farmer_data:
			result = _check_fayda_status(farmer_id, farmer_data)

		# Priority 2: Credit in review
		if not result and credit_map.get(farmer_id):
			result = PendingActionResult(
				state="Credit in review", priority="medium", reason="Active loan application"
			)

		# Priority 3: Crop survey due
		if not result:
			last_crop = crop_visits.get(farmer_id)
			result = _check_crop_survey_due_with_date(last_crop)

		# Priority 4: Livestock survey due
		if not result:
			last_livestock = livestock_visits.get(farmer_id)
			result = _check_livestock_survey_due_with_date(last_livestock)

		# Priority 5: Default
		if not result:
			result = PendingActionResult(state="No action due", priority="low")

		results[farmer_id] = result

	return results


# ============================================================================
# Private helper functions
# ============================================================================


def _check_fayda_status(farmer_id: str, farmer_data: dict | None = None) -> PendingActionResult | None:
	"""Check if Fayda verification is pending (registration not approved)."""
	if not farmer_data:
		farmer_data = frappe.db.get_value(
			"DA Farmer Reference", farmer_id, ["registration_state"], as_dict=True
		)

	if not farmer_data:
		return None

	registration_state = farmer_data.get("registration_state")

	# If registration is pending approval, Fayda verification is needed
	if registration_state == "PENDING_APPROVAL":
		return PendingActionResult(
			state="Fayda check", priority="high", reason="Farmer registration pending approval"
		)

	return None


def _check_credit_status(farmer_id: str) -> PendingActionResult | None:
	"""Check if farmer has active credit application."""
	try:
		a2c_client = get_a2c_client()
		if a2c_client.has_active_application(farmer_id):
			return PendingActionResult(
				state="Credit in review", priority="medium", reason="Active loan application under review"
			)
	except Exception as e:
		frappe.log_error(
			title="Pending Actions - Credit Check Failed", message=f"Error for {farmer_id}: {e!s}"
		)

	return None


def _check_crop_survey_due(farmer_id: str) -> PendingActionResult | None:
	"""Check if crop survey is due based on DA Visit history."""
	last_survey_date = frappe.db.get_value(
		"DA Visit",
		filters={
			"farmer_id": farmer_id,
			"visit_type": "Crop Survey",
			"physical_status": "Physical Visit Complete",
		},
		fieldname="completed_at",
		order_by="completed_at desc",
	)

	return _check_crop_survey_due_with_date(last_survey_date)


def _check_crop_survey_due_with_date(last_survey_date: datetime | None) -> PendingActionResult | None:
	"""Check if crop survey is due given the last survey date."""
	if not last_survey_date:
		return PendingActionResult(
			state="Crop survey due", priority="high", reason="No crop survey on record"
		)

	now = now_datetime()
	last_date = get_datetime(last_survey_date)
	days_since = (now - last_date).days

	if days_since > CROP_SURVEY_DUE_DAYS:
		days_overdue = days_since - CROP_SURVEY_DUE_DAYS
		priority = "high" if days_overdue >= 15 else "medium"

		return PendingActionResult(
			state="Crop survey due",
			priority=priority,
			reason=f"Last crop survey {days_since} days ago",
			days_overdue=days_overdue,
		)

	return None


def _check_livestock_survey_due(farmer_id: str) -> PendingActionResult | None:
	"""Check if livestock survey is due based on DA Visit history."""
	last_survey_date = frappe.db.get_value(
		"DA Visit",
		filters={
			"farmer_id": farmer_id,
			"visit_type": "Livestock Survey",
			"physical_status": "Physical Visit Complete",
		},
		fieldname="completed_at",
		order_by="completed_at desc",
	)

	return _check_livestock_survey_due_with_date(last_survey_date)


def _check_livestock_survey_due_with_date(last_survey_date: datetime | None) -> PendingActionResult | None:
	"""Check if livestock survey is due given the last survey date."""
	if not last_survey_date:
		# Don't flag if never surveyed (farmer may not have livestock)
		return None

	now = now_datetime()
	last_date = get_datetime(last_survey_date)
	days_since = (now - last_date).days

	if days_since > LIVESTOCK_SURVEY_DUE_DAYS:
		days_overdue = days_since - LIVESTOCK_SURVEY_DUE_DAYS
		return PendingActionResult(
			state="Livestock due",
			priority="medium",
			reason=f"Last livestock survey {days_since} days ago",
			days_overdue=days_overdue,
		)

	return None


def _get_last_visits_batch(farmer_ids: list[str], visit_type: str) -> dict[str, datetime | None]:
	"""Get last completed visits for multiple farmers (batch query).

	Args:
	    farmer_ids: List of farmer IDs
	    visit_type: Visit type filter

	Returns:
	    Dict mapping farmer_id -> last visit datetime
	"""
	if not farmer_ids:
		return {}

	visits = frappe.get_all(
		"DA Visit",
		filters={
			"farmer_id": ["in", farmer_ids],
			"visit_type": visit_type,
			"physical_status": "Physical Visit Complete",
		},
		fields=["farmer_id", "completed_at"],
		order_by="completed_at desc",
	)

	# Keep only the most recent visit per farmer
	result = {}
	for visit in visits:
		farmer_id = visit["farmer_id"]
		if farmer_id not in result:
			result[farmer_id] = visit["completed_at"]

	return result
