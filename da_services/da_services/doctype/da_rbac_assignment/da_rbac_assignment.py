# Copyright (c) 2026, COSS - Centre for Open Societal Systems and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from da_services.services import constants as C


class DARBACAssignment(Document):
	"""One role grant for one user, bounded by Region / Woreda and a date window.

	Saving a row also attaches the role to the User so Frappe's own DocPerm checks agree
	with ours; the scope questions (which Woreda, which DA) stay in utils.permissions.
	"""

	def validate(self):
		self._validate_role()
		self._validate_scope()
		self._validate_window()

	def before_insert(self):
		self.assigned_by = frappe.session.user

	def on_update(self):
		self._sync_user_role()

	def _validate_role(self):
		if self.role not in C.DA_SERVICES_ROLES:
			frappe.throw(
				_("Role {0} is not a DA Services role. Choose one of: {1}").format(
					self.role, ", ".join(C.DA_SERVICES_ROLES)
				)
			)

	def _validate_scope(self):
		if self.role == C.ROLE_DA and not self.da_id:
			frappe.throw(_("A Development Agent assignment needs the DA-ID it is bound to."))
		if self.role == C.ROLE_SUPERVISOR and not self.woreda_scope:
			# FSD 3.1.1: a Supervisor acts only on the DAs of their own Woreda.
			frappe.throw(_("A Supervisor assignment needs a Woreda scope."))
		if self.role == C.ROLE_EXECUTIVE and not self.region_scope:
			frappe.throw(_("An Executive assignment needs a Region scope."))
		if self.woreda_scope and not self.region_scope:
			frappe.throw(_("A Woreda scope needs its Region."))

	def _validate_window(self):
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To cannot be before Effective From."))

	def _sync_user_role(self):
		"""Keep the User's Has Role table in step with this grant (add only; never remove).

		Removing a role automatically would be wrong while another assignment for the same
		role is still live, so revocation is an explicit administrator action.
		"""
		if not self.active:
			return
		user = frappe.get_doc("User", self.user)
		if any(r.role == self.role for r in user.roles):
			return
		user.append("roles", {"role": self.role})
		user.flags.ignore_permissions = True
		user.save()
