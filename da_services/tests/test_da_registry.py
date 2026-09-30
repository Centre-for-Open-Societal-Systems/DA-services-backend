"""DA Registry client boundary: mock behaviour, factory, and the v1 read endpoint."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from da_services.api.v1 import da as da_api
from da_services.integrations.da_registry.client import (
	DANotFound,
	DARegistryContractPending,
	HttpDARegistryClient,
	get_client,
)
from da_services.integrations.da_registry.mock import MockDARegistryClient
from da_services.integrations.da_registry.schemas import LifecycleOutcome
from da_services.services import constants as C

SUPERVISOR = "test-supervisor2@da.local"


class TestMockClient(IntegrationTestCase):
	def setUp(self):
		MockDARegistryClient.reset()
		self.client = MockDARegistryClient()

	def test_get_da_maps_registry_fields(self):
		ref = self.client.get_da("DA-000001")
		self.assertEqual(ref.full_name, "Abebe Kebede")
		self.assertEqual(ref.active_status, C.ACTIVE_STATUS_ACTIVE)
		self.assertEqual(ref.woreda, "ET04-W01")
		self.assertEqual(ref.kebele, "ET04-W01-K03")
		self.assertEqual(ref.source_version, "3")
		self.assertIsNotNone(ref.fetched_at)

	def test_unknown_da_raises_not_found(self):
		with self.assertRaises(DANotFound):
			self.client.get_da("DA-999999")
		self.assertFalse(self.client.validate_da_id("DA-999999"))
		self.assertTrue(self.client.validate_da_id("DA-000001"))

	def test_lifecycle_outcome_updates_status_and_is_idempotent(self):
		outcome = LifecycleOutcome(
			da_id="DA-000001",
			transition_type="Leave",
			new_active_status=C.ACTIVE_STATUS_ON_LEAVE,
			effective_date=today(),
			reason="Annual leave",
			approver="Administrator",
			reference="LT-0001",
		)
		first = self.client.push_lifecycle_outcome(outcome)
		self.assertTrue(first.accepted)
		self.assertEqual(self.client.get_da("DA-000001").active_status, C.ACTIVE_STATUS_ON_LEAVE)
		self.assertEqual(self.client.get_da("DA-000001").source_version, "4")

		replay = self.client.push_lifecycle_outcome(outcome)
		self.assertEqual(replay.external_reference, first.external_reference)
		self.assertEqual(self.client.get_da("DA-000001").source_version, "4")  # not bumped again

	def test_transfer_moves_kebele(self):
		outcome = LifecycleOutcome(
			da_id="DA-000001",
			transition_type="Transfer",
			new_active_status=None,
			effective_date=today(),
			reason="Coverage gap",
			approver="Administrator",
			reference="LT-0002",
			target_kebele="ET04-W01-K09",
		)
		self.client.push_lifecycle_outcome(outcome)
		self.assertEqual(self.client.get_da("DA-000001").kebele, "ET04-W01-K09")


class TestClientFactory(IntegrationTestCase):
	def test_default_backend_is_mock(self):
		MockDARegistryClient.reset()
		self.assertIsInstance(get_client(), MockDARegistryClient)
		self.assertIs(get_client(), get_client())  # shared instance

	def test_http_backend_is_blocked_until_contract_exists(self):
		client = HttpDARegistryClient("https://registry.example")
		with self.assertRaises(DARegistryContractPending):
			client.get_da("DA-000001")


class TestGetDaEndpoint(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		MockDARegistryClient.reset()
		frappe.db.delete("DA RBAC Assignment")
		if not frappe.db.exists("User", SUPERVISOR):
			u = frappe.new_doc("User")
			u.email = SUPERVISOR
			u.first_name = "Supervisor Two"
			u.send_welcome_email = 0
			u.insert(ignore_permissions=True)
		grant = frappe.new_doc("DA RBAC Assignment")
		grant.user = SUPERVISOR
		grant.role = C.ROLE_SUPERVISOR
		grant.region_scope = "ET04"
		grant.woreda_scope = "ET04-W01"
		grant.effective_from = today()
		grant.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_supervisor_reads_da_in_own_woreda(self):
		frappe.set_user(SUPERVISOR)
		out = da_api.get_da("DA-000001")
		self.assertEqual(out["da_id"], "DA-000001")
		self.assertEqual(out["woreda"], "ET04-W01")

	def test_supervisor_is_denied_outside_woreda(self):
		frappe.set_user(SUPERVISOR)
		with self.assertRaises(frappe.PermissionError):
			da_api.get_da("DA-000003")  # ET03-W02

	def test_guest_is_denied(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			da_api.get_da("DA-000001")

	def test_unknown_da_is_not_found(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.DoesNotExistError):
			da_api.get_da("DA-424242")
