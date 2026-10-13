# Copyright (c) 2026, COSS - Centre for Open Societal Systems and contributors
# For license information, please see license.txt

"""DA Kebele Assignment: the FR-05 decision record (data-model deviation, see docs).

States follow the portal: Proposed (drafted) → Validated (geofence in-boundary) →
Effective (applied), or Flagged (geofence out-of-bounds, needs an override), and
Superseded when a newer assignment for the same DA takes over. The DA Registry keeps the
posting of record; `registry_sync_state` says whether it has accepted this decision.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from da_services.da_services.doctype.da_administrative_area.da_administrative_area import ancestors_of

LIVE_STATES = ("Proposed", "Validated", "Flagged", "Effective")


class DAKebeleAssignment(Document):
	def validate(self):
		area = frappe.db.get_value("DA Administrative Area", self.kebele, ["level", "active"], as_dict=True)
		if not area:
			frappe.throw(_("Kebele {0} is not in the administrative area master.").format(self.kebele))
		if area.level != "Kebele":
			frappe.throw(_("{0} is a {1}, not a Kebele.").format(self.kebele, area.level))
		if not area.active and self.is_new():
			frappe.throw(_("Kebele {0} is inactive.").format(self.kebele))
		tree = ancestors_of(self.kebele)
		self.region, self.zone, self.woreda = tree["region"], tree["zone"], tree["woreda"]
		if self.is_new() and self.client_op_id:
			dup = frappe.db.get_value("DA Kebele Assignment", {"client_op_id": self.client_op_id}, "name")
			if dup:
				frappe.throw(
					_("Assignment {0} already exists for client_op_id {1}.").format(dup, self.client_op_id),
					frappe.DuplicateEntryError,
				)

	def after_insert(self):
		# One live assignment per DA: the newest one supersedes whatever was in force.
		if self.state not in LIVE_STATES:
			return
		prior = frappe.get_all(
			"DA Kebele Assignment",
			filters={"da_id": self.da_id, "state": ("in", LIVE_STATES), "name": ("!=", self.name)},
			pluck="name",
		)
		for name in prior:
			frappe.db.set_value(
				"DA Kebele Assignment",
				name,
				{"state": "Superseded", "superseded_by": self.name},
				update_modified=True,
			)
		if prior:
			self.db_set("supersedes", sorted(prior)[-1], update_modified=False)

	def on_trash(self):
		frappe.throw(_("Assignments are history; supersede them instead of deleting."))
