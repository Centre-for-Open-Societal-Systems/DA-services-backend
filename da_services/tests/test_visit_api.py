"""Visits API: plan, list, detail timeline, reschedule, cancel (DA-43)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from da_services.api.v1 import visits as api
from da_services.services import constants as C

DA1 = "vapi-da1@da.local"  # DA-000001, ET04 / ET04-W01
SUP = "vapi-sup@da.local"  # Supervisor ET04-W01
EXEC = "vapi-exec@da.local"  # Executive ET04
COMMS = "vapi-comms@da.local"


def _user(email, roles):
	if not frappe.db.exists("User", email):
		u = frappe.new_doc("User")
		u.email = email
		u.first_name = email.split("@")[0]
		u.send_welcome_email = 0
		u.insert(ignore_permissions=True)
	u = frappe.get_doc("User", email)
	for r in roles:
		if r not in frappe.get_roles(email):
			u.add_roles(r)
	return email


def _grant(user, role, **kw):
	doc = frappe.new_doc("DA RBAC Assignment")
	doc.user = user
	doc.role = role
	doc.effective_from = today()
	for k, v in kw.items():
		setattr(doc, k, v)
	doc.insert(ignore_permissions=True)
	return doc


class TestVisitAPI(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for dt in ("DA Notification", "DA Visit", "DA Task", "DA RBAC Assignment"):
			frappe.db.delete(dt)
		_user(DA1, [C.ROLE_DA])
		_user(SUP, [C.ROLE_SUPERVISOR])
		_user(EXEC, [C.ROLE_EXECUTIVE])
		_user(COMMS, [C.ROLE_COMMS])
		_grant(DA1, C.ROLE_DA, da_id="DA-000001", region_scope="ET04", woreda_scope="ET04-W01")
		_grant(SUP, C.ROLE_SUPERVISOR, region_scope="ET04", woreda_scope="ET04-W01")
		_grant(EXEC, C.ROLE_EXECUTIVE, region_scope="ET04")
		_grant(COMMS, C.ROLE_COMMS)
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.local.request = None  # API helpers then read kwargs, as the form would send them

	def tearDown(self):
		frappe.set_user("Administrator")
		for dt in ("DA Notification", "DA Visit", "DA Task", "DA RBAC Assignment"):
			frappe.db.delete(dt)
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

	def _plan(self, **kw):
		base = {"farmer_id": "FRM-000101", "date": add_days(today(), 1), "time": "10:30"}
		return api.plan(**{**base, **kw})

	# -- plan ---------------------------------------------------------------------

	def test_da_plans_from_the_form_fields(self):
		frappe.set_user(DA1)
		out = self._plan(
			visit_type="Advisory",
			purpose="Input advisory",
			duration_min="60",
			priority="High",
			priority_reason="Overdue by 12 days",
			location={"lat": 9.1234, "lng": 37.5678},
			notify_farmer_sms="true",
			advisory_qa=[{"question": "Fertiliser timing?", "answer": ""}],
		)
		self.assertEqual(out["status"], "success", out)
		v = out["data"]
		self.assertEqual(v["da_id"], "DA-000001")
		self.assertEqual(v["scheduled_at"], f"{add_days(today(), 1)}T10:30:00")
		self.assertEqual((v["visit_type"], v["duration_min"], v["priority"]), ("Advisory", 60, "High"))
		self.assertEqual((v["location_lat"], v["location_lng"]), (9.1234, 37.5678))
		self.assertEqual(v["advisory_qa"], [{"question": "Fertiliser timing?", "answer": ""}])
		self.assertEqual(v["physical_status"], "Planned")
		self.assertEqual(frappe.db.get_value("DA Visit", v["name"], "notify_farmer_sms"), 1)
		self.assertIsNone(v["assigned_by"])

	def test_plan_validates_required_fields(self):
		frappe.set_user(DA1)
		out = api.plan(date=add_days(today(), 1))
		self.assertEqual(out["status"], "error")
		self.assertEqual(frappe.response.get("http_status_code"), 400)
		out = api.plan(farmer_id="FRM-000101")
		self.assertEqual(out["status"], "error")

	def test_plan_is_idempotent_on_client_op_id(self):
		frappe.set_user(DA1)
		a = self._plan(client_op_id="op-43-1")["data"]
		b = self._plan(client_op_id="op-43-1", purpose="changed")["data"]
		self.assertEqual(a["name"], b["name"])
		self.assertEqual(frappe.db.count("DA Visit"), 1)

	def test_supervisor_plans_for_a_da_in_woreda_only(self):
		frappe.set_user(SUP)
		out = self._plan(da_id="DA-000001")
		self.assertEqual(out["status"], "success", out)
		self.assertEqual(out["data"]["assigned_by"], SUP)
		out = self._plan(da_id="DA-000003")  # ET03, outside the Supervisor's Woreda
		self.assertEqual(out["status"], "error")
		self.assertEqual(frappe.response.get("http_status_code"), 403)
		out = self._plan()  # officer must name the DA
		self.assertEqual(out["status"], "error")

	def test_executive_and_comms_cannot_plan(self):
		frappe.set_user(EXEC)
		self.assertEqual(self._plan(da_id="DA-000001")["status"], "error")
		frappe.set_user(COMMS)
		self.assertEqual(self._plan()["status"], "error")
		self.assertEqual(api.list_visits()["status"], "error")

	# -- list / detail -------------------------------------------------------------

	def test_list_filters_and_pagination(self):
		frappe.set_user(DA1)
		self._plan(date=today(), time="08:00")
		self._plan(date=today(), time="14:00", farmer_id="FRM-000102")
		self._plan(date=add_days(today(), 2))
		out = api.list_visits(date=today())
		self.assertEqual(out["meta"]["total"], 2)
		self.assertEqual([r["farmer_id"] for r in out["data"]], ["FRM-000101", "FRM-000102"])
		out = api.list_visits(date=today(), limit=1, start=1)
		self.assertEqual((len(out["data"]), out["meta"]["total"]), (1, 2))
		out = api.list_visits(**{"from": today(), "to": add_days(today(), 2), "status": "Planned"})
		self.assertEqual(out["meta"]["total"], 3)
		out = api.list_visits(farmer_id="FRM-000102")
		self.assertEqual(out["meta"]["total"], 1)

	def test_executive_reads_region_but_not_other_region(self):
		frappe.set_user(DA1)
		mine = self._plan()["data"]
		frappe.set_user("Administrator")
		self._plan(da_id="DA-000003")
		frappe.set_user(EXEC)
		out = api.list_visits()
		self.assertEqual([r["da_id"] for r in out["data"]], ["DA-000001"])
		self.assertEqual(api.get_visit(mine["name"])["status"], "success")

	def test_detail_has_a_timeline(self):
		frappe.set_user(DA1)
		v = self._plan()["data"]
		out = api.get_visit(v["name"])
		self.assertEqual(out["status"], "success", out)
		tl = out["data"]["timeline"]
		self.assertEqual([e["label"] for e in tl], ["Planned"])
		self.assertEqual(tl[0]["by"], DA1)
		self.assertTrue(tl[0]["when"])
		# a Supervisor-planned visit names the Supervisor as the planner
		frappe.set_user(SUP)
		v2 = self._plan(da_id="DA-000001")["data"]
		self.assertEqual(api.get_visit(v2["name"])["data"]["timeline"][0]["by"], SUP)

	# -- reschedule / cancel ---------------------------------------------------------

	def test_reschedule_supersedes_and_shows_in_timeline(self):
		frappe.set_user(DA1)
		v = self._plan()["data"]
		out = api.reschedule(v["name"], date=add_days(today(), 3), time="11:00", reason="Farmer unavailable")
		self.assertEqual(out["status"], "success", out)
		new = out["data"]
		self.assertEqual(new["rescheduled_from"], v["name"])
		self.assertEqual(new["scheduled_at"], f"{add_days(today(), 3)}T11:00:00")
		old = api.get_visit(v["name"])["data"]
		self.assertEqual(old["physical_status"], "Rescheduled")
		self.assertIn("Rescheduled", [e["label"] for e in old["timeline"]])
		# a superseded visit cannot be moved again
		out = api.reschedule(v["name"], date=add_days(today(), 4))
		self.assertEqual(out["status"], "error")
		out = api.reschedule(new["name"])  # no time given
		self.assertEqual(out["status"], "error")

	def test_cancel_and_scope(self):
		frappe.set_user(DA1)
		v = self._plan()["data"]
		frappe.set_user("Administrator")
		other = self._plan(da_id="DA-000003")["data"]
		frappe.db.commit()  # nosemgrep: an API error below rolls back uncommitted rows
		frappe.set_user(DA1)
		self.assertEqual(api.cancel(other["name"], reason="not mine")["status"], "error")
		self.assertEqual(frappe.response.get("http_status_code"), 403)
		out = api.cancel(v["name"], reason="Farmer moved")
		self.assertEqual(out["status"], "success", out)
		self.assertEqual(out["data"]["physical_status"], "Cancelled")
