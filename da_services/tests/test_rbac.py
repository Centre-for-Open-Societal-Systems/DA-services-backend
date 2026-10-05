"""Roles, DA RBAC Assignment validation, and the scope rule."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from da_services.services import constants as C
from da_services.utils.permissions import get_scope_context, require_da_access

SUPERVISOR = "test-supervisor@da.local"
DA_USER = "test-da@da.local"
EXEC = "test-exec@da.local"
COMMS = "test-comms@da.local"


def _user(email: str) -> str:
	if not frappe.db.exists("User", email):
		u = frappe.new_doc("User")
		u.email = email
		u.first_name = email.split("@")[0]
		u.send_welcome_email = 0
		u.insert(ignore_permissions=True)
	return email


def _grant(user, role, **kw):
	doc = frappe.new_doc("DA RBAC Assignment")
	doc.user = user
	doc.role = role
	doc.effective_from = kw.pop("effective_from", today())
	for k, v in kw.items():
		setattr(doc, k, v)
	doc.insert(ignore_permissions=True)
	return doc


class TestRoles(IntegrationTestCase):
	def test_all_five_roles_are_seeded(self):
		for role in C.DA_SERVICES_ROLES:
			self.assertTrue(frappe.db.exists("Role", role), role)

	def test_da_role_has_no_desk_access(self):
		self.assertEqual(frappe.db.get_value("Role", C.ROLE_DA, "desk_access"), 0)


class TestRBACAssignment(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("DA RBAC Assignment")
		for e in (SUPERVISOR, DA_USER, EXEC, COMMS):
			_user(e)

	def test_supervisor_needs_woreda(self):
		with self.assertRaises(frappe.ValidationError):
			_grant(SUPERVISOR, C.ROLE_SUPERVISOR, region_scope="ET04")

	def test_da_needs_da_id(self):
		with self.assertRaises(frappe.ValidationError):
			_grant(DA_USER, C.ROLE_DA)

	def test_woreda_needs_region(self):
		with self.assertRaises(frappe.ValidationError):
			_grant(SUPERVISOR, C.ROLE_SUPERVISOR, woreda_scope="ET04-W01")

	def test_window_cannot_be_inverted(self):
		with self.assertRaises(frappe.ValidationError):
			_grant(
				SUPERVISOR,
				C.ROLE_SUPERVISOR,
				region_scope="ET04",
				woreda_scope="ET04-W01",
				effective_to=add_days(today(), -1),
			)

	def test_non_da_services_role_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_grant(SUPERVISOR, "System Manager")

	def test_grant_attaches_role_to_user_and_records_assigner(self):
		doc = _grant(SUPERVISOR, C.ROLE_SUPERVISOR, region_scope="ET04", woreda_scope="ET04-W01")
		self.assertEqual(doc.assigned_by, "Administrator")
		self.assertIn(C.ROLE_SUPERVISOR, frappe.get_roles(SUPERVISOR))


class TestScopeRule(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("DA RBAC Assignment")
		for e in (SUPERVISOR, DA_USER, EXEC, COMMS):
			_user(e)
		_grant(SUPERVISOR, C.ROLE_SUPERVISOR, region_scope="ET04", woreda_scope="ET04-W01")
		_grant(EXEC, C.ROLE_EXECUTIVE, region_scope="ET03")
		_grant(DA_USER, C.ROLE_DA, da_id="DA-000001", region_scope="ET04", woreda_scope="ET04-W01")
		_grant(COMMS, C.ROLE_COMMS)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_supervisor_covers_own_woreda_only(self):
		ctx = get_scope_context(SUPERVISOR)
		self.assertTrue(ctx.covers("ET04", "ET04-W01"))
		self.assertFalse(ctx.covers("ET04", "ET04-W02"))
		self.assertFalse(ctx.covers("ET03", "ET03-W02"))

	def test_executive_covers_whole_region(self):
		ctx = get_scope_context(EXEC)
		self.assertTrue(ctx.covers("ET03", "ET03-W02"))
		self.assertFalse(ctx.covers("ET04", "ET04-W01"))

	def test_da_sees_only_own_record(self):
		ctx = get_scope_context(DA_USER)
		require_da_access("DA-000001", "ET04", "ET04-W01", ctx)
		with self.assertRaises(frappe.PermissionError):
			require_da_access("DA-000002", "ET04", "ET04-W01", ctx)

	def test_comms_officer_never_reaches_da_identity(self):
		ctx = get_scope_context(COMMS)
		with self.assertRaises(frappe.PermissionError):
			require_da_access("DA-000001", "ET04", "ET04-W01", ctx)

	def test_expired_grant_gives_no_scope(self):
		frappe.db.delete("DA RBAC Assignment", {"user": SUPERVISOR})
		_grant(
			SUPERVISOR,
			C.ROLE_SUPERVISOR,
			region_scope="ET04",
			woreda_scope="ET04-W01",
			effective_from=add_days(today(), -30),
			effective_to=add_days(today(), -1),
		)
		ctx = get_scope_context(SUPERVISOR)
		self.assertFalse(ctx.covers("ET04", "ET04-W01"))

	def test_administrator_is_unrestricted(self):
		ctx = get_scope_context("Administrator")
		self.assertTrue(ctx.unrestricted)
		self.assertTrue(ctx.covers("ET99", "ET99-W99"))

	def test_non_admin_sees_only_own_assignments_in_list(self):
		frappe.set_user(SUPERVISOR)
		rows = frappe.get_list("DA RBAC Assignment", fields=["user"])
		self.assertTrue(rows)
		self.assertTrue(all(r.user == SUPERVISOR for r in rows))
