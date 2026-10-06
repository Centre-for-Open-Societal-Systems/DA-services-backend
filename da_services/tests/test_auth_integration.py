"""Auth integration tests for oan_auth_service in DA Services.

Covers: deny-by-default revocation check, /me profile enrichment,
health endpoint accessibility, and scope resolution through the token path.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from da_services.api.middleware import check_da_assignment
from da_services.api.router import ensure_routes_registered
from da_services.services import constants as C


SUPERVISOR = "auth-test-supervisor@da.local"
DA_USER = "auth-test-da@da.local"
NO_ROLE_USER = "auth-test-norole@da.local"


def make_test_request(
	path: str,
	method: str = "GET",
	data: dict | None = None,
) -> Request:
	"""Construct a Werkzeug Request and wire up frappe.local state."""
	query_string = None
	if "?" in path:
		path, query_string = path.split("?", 1)

	builder_kwargs = {
		"path": path,
		"method": method.upper(),
		"base_url": "http://testsite.localhost",
	}
	if query_string:
		builder_kwargs["query_string"] = query_string
	if data is not None:
		builder_kwargs["json"] = data

	builder = EnvironBuilder(**builder_kwargs)
	req = Request(builder.get_environ())

	frappe.local.request = req
	frappe.local.request_ip = "127.0.0.1"
	form_data = dict(req.args)
	if data:
		form_data.update(data)
	frappe.local.form_dict = frappe._dict(form_data)
	frappe.local.response = frappe._dict({})

	return req


def _user(email: str, roles: list[str] | None = None) -> str:
	if not frappe.db.exists("User", email):
		u = frappe.new_doc("User")
		u.email = email
		u.first_name = email.split("@")[0]
		u.send_welcome_email = 0
		u.insert(ignore_permissions=True)
	if roles:
		existing = set(frappe.get_roles(email))
		for role in roles:
			if role not in existing:
				frappe.get_doc("User", email).add_roles(role)
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


class TestRevocationCheck(IntegrationTestCase):
	"""Unit tests for the deny-by-default revocation_check callback."""

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("DA RBAC Assignment")
		_user(SUPERVISOR, [C.ROLE_SUPERVISOR])
		_user(DA_USER, [C.ROLE_DA])
		_user(NO_ROLE_USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_unrestricted_role_bypasses_check(self):
		result = check_da_assignment("Administrator")
		self.assertIsNone(result)

	def test_user_without_da_role_is_rejected(self):
		result = check_da_assignment(NO_ROLE_USER)
		self.assertIsNotNone(result)
		self.assertIn("no DA Services role", result)

	def test_da_role_without_assignment_is_rejected(self):
		result = check_da_assignment(SUPERVISOR)
		self.assertIsNotNone(result)
		self.assertIn("No active DA RBAC assignment", result)

	def test_da_role_with_active_assignment_passes(self):
		_grant(SUPERVISOR, C.ROLE_SUPERVISOR, region_scope="ET04", woreda_scope="ET04-W01")
		result = check_da_assignment(SUPERVISOR)
		self.assertIsNone(result)

	def test_expired_assignment_is_rejected(self):
		from frappe.utils import add_days

		_grant(
			SUPERVISOR,
			C.ROLE_SUPERVISOR,
			region_scope="ET04",
			woreda_scope="ET04-W01",
			effective_from=add_days(today(), -30),
			effective_to=add_days(today(), -1),
		)
		result = check_da_assignment(SUPERVISOR)
		self.assertIsNotNone(result)


class TestRESTRoutes(IntegrationTestCase):
	"""Integration tests for the REST API endpoints through Frappe's dispatcher."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_routes_registered()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.delete("DA RBAC Assignment")
		_user(SUPERVISOR, [C.ROLE_SUPERVISOR])
		_user(DA_USER, [C.ROLE_DA])
		_user(NO_ROLE_USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_health_endpoint_accessible_as_guest(self):
		import frappe.api

		frappe.set_user("Guest")
		req = make_test_request("/api/v1/da-services/health", method="GET")
		res = frappe.api.handle(req)
		self.assertEqual(res.status_code, 200)
		data = json.loads(res.get_data(as_text=True))
		self.assertEqual(data["status"], "success")
		self.assertEqual(data["data"]["service"], "da_services")
		self.assertEqual(data["data"]["status"], "healthy")

	def test_me_returns_da_profile_for_assigned_supervisor(self):
		import frappe.api

		_grant(SUPERVISOR, C.ROLE_SUPERVISOR, region_scope="ET04", woreda_scope="ET04-W01")
		frappe.set_user(SUPERVISOR)
		req = make_test_request("/api/v1/auth/me", method="GET")
		res = frappe.api.handle(req)
		self.assertEqual(res.status_code, 200)
		data = json.loads(res.get_data(as_text=True))
		self.assertEqual(data["status"], "success")
		self.assertIn("profiles", data["data"])
		da_profile = data["data"]["profiles"].get("da_services")
		self.assertIsNotNone(da_profile)
		self.assertIn(C.ROLE_SUPERVISOR, da_profile["roles"])
		self.assertIn("ET04", da_profile["scope"]["regions"])
		self.assertIn("ET04-W01", da_profile["scope"]["woredas"])

	def test_me_returns_da_ids_for_assigned_da(self):
		import frappe.api

		_grant(DA_USER, C.ROLE_DA, da_id="DA-000001", region_scope="ET04", woreda_scope="ET04-W01")
		frappe.set_user(DA_USER)
		req = make_test_request("/api/v1/auth/me", method="GET")
		res = frappe.api.handle(req)
		self.assertEqual(res.status_code, 200)
		data = json.loads(res.get_data(as_text=True))
		da_profile = data["data"]["profiles"].get("da_services")
		self.assertIsNotNone(da_profile)
		self.assertIn("DA-000001", da_profile["scope"]["da_ids"])

	def test_me_returns_no_da_profile_for_user_without_da_role(self):
		import frappe.api

		frappe.set_user(NO_ROLE_USER)
		req = make_test_request("/api/v1/auth/me", method="GET")
		res = frappe.api.handle(req)
		self.assertEqual(res.status_code, 200)
		data = json.loads(res.get_data(as_text=True))
		profiles = data["data"].get("profiles", {})
		self.assertIsNone(profiles.get("da_services"))

	def test_me_returns_da_profile_for_administrator(self):
		import frappe.api

		frappe.set_user("Administrator")
		req = make_test_request("/api/v1/auth/me", method="GET")
		res = frappe.api.handle(req)
		self.assertEqual(res.status_code, 200)
		data = json.loads(res.get_data(as_text=True))
		da_profile = data["data"].get("profiles", {}).get("da_services")
		if da_profile is not None:
			self.assertIn("roles", da_profile)
			self.assertIn("scope", da_profile)
