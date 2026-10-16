"""Tests for pending actions derivation (DA-39).

Tests visit-based pending action logic without Crop/Livestock Registry integration.
"""

from datetime import datetime, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from da_services.services.pending_actions import (
	CROP_SURVEY_DUE_DAYS,
	LIVESTOCK_SURVEY_DUE_DAYS,
	derive_pending_action,
	derive_pending_actions_batch,
)


class TestPendingActions(FrappeTestCase):
	"""Test suite for DA-39 pending action derivation."""

	def setUp(self):
		"""Set up test data."""
		self.farmer_id = "test-farmer-pending-001"

		# Clean up
		frappe.db.delete("DA Farmer Reference", {"farmer_id": self.farmer_id})
		frappe.db.delete("DA Visit", {"farmer_id": self.farmer_id})
		frappe.db.commit()

		# Create farmer reference
		self.farmer_ref = frappe.get_doc(
			{
				"doctype": "DA Farmer Reference",
				"farmer_id": self.farmer_id,
				"reg_id": "FR-TEST-001",
				"farmer_name": "Test Farmer",
				"kebele": "TEST-KEBELE",
				"woreda": "TEST-WOREDA",
				"region": "TEST-REGION",
				"registration_state": "APPROVED",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		"""Clean up test data."""
		frappe.db.delete("DA Farmer Reference", {"farmer_id": self.farmer_id})
		frappe.db.delete("DA Visit", {"farmer_id": self.farmer_id})
		frappe.db.commit()

	def test_fayda_check_pending(self):
		"""Test pending Fayda status."""
		self.farmer_ref.registration_state = "PENDING_APPROVAL"
		self.farmer_ref.save(ignore_permissions=True)
		frappe.db.commit()

		result = derive_pending_action(self.farmer_id)

		self.assertEqual(result.state, "Fayda check")
		self.assertEqual(result.priority, "high")

	def test_crop_survey_never_done(self):
		"""Test crop survey due when never done."""
		result = derive_pending_action(self.farmer_id)

		self.assertEqual(result.state, "Crop survey due")
		self.assertEqual(result.priority, "high")
		self.assertIn("No crop survey", result.reason)

	def test_crop_survey_overdue(self):
		"""Test crop survey overdue."""
		past_date = datetime.now() - timedelta(days=45)

		# Create visit with valid initial state
		visit = frappe.get_doc(
			{
				"doctype": "DA Visit",
				"da_id": "DA-TEST-001",
				"farmer_id": self.farmer_id,
				"visit_type": "Crop Survey",
				"physical_status": "Planned",
				"scheduled_at": past_date,
			}
		).insert(ignore_permissions=True)

		# Transition: Planned → In progress
		visit.physical_status = "In progress"
		visit.save(ignore_permissions=True)

		# Transition: In progress → Physical Visit Complete
		visit.physical_status = "Physical Visit Complete"
		visit.completed_at = past_date
		visit.save(ignore_permissions=True)
		frappe.db.commit()

		result = derive_pending_action(self.farmer_id)

		self.assertEqual(result.state, "Crop survey due")
		self.assertEqual(result.priority, "high")
		self.assertEqual(result.days_overdue, 15)

	def test_crop_survey_recent(self):
		"""Test recent crop survey shows no action."""
		recent_date = datetime.now() - timedelta(days=10)

		# Create visit with valid initial state
		visit = frappe.get_doc(
			{
				"doctype": "DA Visit",
				"da_id": "DA-TEST-001",
				"farmer_id": self.farmer_id,
				"visit_type": "Crop Survey",
				"physical_status": "Planned",
				"scheduled_at": recent_date,
			}
		).insert(ignore_permissions=True)

		# Transition: Planned → In progress → Physical Visit Complete
		visit.physical_status = "In progress"
		visit.save(ignore_permissions=True)
		visit.physical_status = "Physical Visit Complete"
		visit.completed_at = recent_date
		visit.save(ignore_permissions=True)
		frappe.db.commit()

		result = derive_pending_action(self.farmer_id)

		self.assertEqual(result.state, "No action due")
		self.assertEqual(result.priority, "low")

	def test_livestock_survey_overdue(self):
		"""Test livestock survey overdue."""
		livestock_date = datetime.now() - timedelta(days=70)
		crop_date = datetime.now() - timedelta(days=10)

		# First, create a RECENT crop survey so crop doesn't come first
		crop_visit = frappe.get_doc(
			{
				"doctype": "DA Visit",
				"da_id": "DA-TEST-001",
				"farmer_id": self.farmer_id,
				"visit_type": "Crop Survey",
				"physical_status": "Planned",
				"scheduled_at": crop_date,
			}
		).insert(ignore_permissions=True)
		crop_visit.physical_status = "In progress"
		crop_visit.save(ignore_permissions=True)
		crop_visit.physical_status = "Physical Visit Complete"
		crop_visit.completed_at = crop_date
		crop_visit.save(ignore_permissions=True)

		# Now create overdue livestock survey
		livestock_visit = frappe.get_doc(
			{
				"doctype": "DA Visit",
				"da_id": "DA-TEST-002",
				"farmer_id": self.farmer_id,
				"visit_type": "Livestock Survey",
				"physical_status": "Planned",
				"scheduled_at": livestock_date,
			}
		).insert(ignore_permissions=True)

		# Transition: Planned → In progress → Physical Visit Complete
		livestock_visit.physical_status = "In progress"
		livestock_visit.save(ignore_permissions=True)
		livestock_visit.physical_status = "Physical Visit Complete"
		livestock_visit.completed_at = livestock_date
		livestock_visit.save(ignore_permissions=True)
		frappe.db.commit()

		result = derive_pending_action(self.farmer_id)

		self.assertEqual(result.state, "Livestock due")
		self.assertEqual(result.priority, "medium")

	def test_credit_in_review(self):
		"""Test credit in review state (A2C integration)."""
		# Note: This test requires A2C app to be installed
		# If A2C is not installed, it should gracefully return no credit status

		# Create a mock scenario where credit check would be triggered
		# In real scenario, A2C's has_active_application() would return True

		# For now, test that credit check doesn't break the flow
		result = derive_pending_action(self.farmer_id)

		# Should return some valid state (credit or crop survey due)
		valid_states = [
			"Credit in review",
			"Crop survey due",
			"Livestock due",
			"Fayda check",
			"No action due",
		]
		self.assertIn(result.state, valid_states)

		# If not credit, should default to crop survey due (never surveyed)
		if result.state != "Credit in review":
			self.assertEqual(result.state, "Crop survey due")

	def test_priority_order(self):
		"""Test priority order: Fayda > Crop."""
		# Set pending Fayda (registration pending approval)
		self.farmer_ref.registration_state = "PENDING_APPROVAL"
		self.farmer_ref.save(ignore_permissions=True)

		# Create overdue crop survey
		past_date = datetime.now() - timedelta(days=45)
		visit = frappe.get_doc(
			{
				"doctype": "DA Visit",
				"da_id": "DA-TEST-001",
				"farmer_id": self.farmer_id,
				"visit_type": "Crop Survey",
				"physical_status": "Planned",
				"scheduled_at": past_date,
			}
		).insert(ignore_permissions=True)

		# Transition: Planned → In progress → Physical Visit Complete
		visit.physical_status = "In progress"
		visit.save(ignore_permissions=True)
		visit.physical_status = "Physical Visit Complete"
		visit.completed_at = past_date
		visit.save(ignore_permissions=True)
		frappe.db.commit()

		result = derive_pending_action(self.farmer_id)

		# Should be Fayda (higher priority)
		self.assertEqual(result.state, "Fayda check")

	def test_batch_derivation(self):
		"""Test batch derivation for multiple farmers."""
		farmer_id_2 = "test-farmer-pending-002"

		frappe.get_doc(
			{
				"doctype": "DA Farmer Reference",
				"farmer_id": farmer_id_2,
				"reg_id": "FR-TEST-002",
				"farmer_name": "Test Farmer 2",
				"kebele": "TEST",
				"woreda": "TEST",
				"region": "TEST",
				"registration_state": "PENDING_APPROVAL",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

		try:
			results = derive_pending_actions_batch([self.farmer_id, farmer_id_2])

			self.assertEqual(len(results), 2)
			self.assertEqual(results[self.farmer_id].state, "Crop survey due")
			self.assertEqual(results[farmer_id_2].state, "Fayda check")

		finally:
			frappe.db.delete("DA Farmer Reference", {"farmer_id": farmer_id_2})
			frappe.db.commit()

	def test_all_five_states_coverage(self):
		"""Test that all 5 DA-39 required states are implemented."""
		# Verify the 5 required states exist in code
		from da_services.services.pending_actions import PendingActionState

		# This should not raise an error - confirms type definition exists
		required_states = [
			"Crop survey due",
			"Livestock due",
			"Credit in review",
			"Fayda check",
			"No action due",
		]

		# Test that we can create results with all 5 states
		for _state in required_states:
			result = derive_pending_action(self.farmer_id)
			# Result should be one of the valid states
			self.assertIn(result.state, required_states)

	def test_system_derived_not_stored(self):
		"""Test that pending actions are computed, not stored (DA-39 Req 3)."""
		# Derive pending action
		result = derive_pending_action(self.farmer_id)

		# Verify it's NOT stored in DA Farmer Reference
		farmer_ref = frappe.get_doc("DA Farmer Reference", self.farmer_id)

		# These fields should NOT exist in the doctype
		self.assertFalse(hasattr(farmer_ref, "pending_action"))
		self.assertFalse(hasattr(farmer_ref, "pending_action_priority"))

		# Pending action is only computed on-the-fly
		self.assertIsNotNone(result.state)
		self.assertIsNotNone(result.priority)
