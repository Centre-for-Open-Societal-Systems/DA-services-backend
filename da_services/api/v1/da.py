"""v1: read a DA reference from the registry, within the caller's scope.

Path: /api/method/da_services.api.v1.da.get_da?da_id=DA-000001

Thin by design: authorize, call the integration, shape the response. The scope rule
lives in utils.permissions and the registry access in integrations.da_registry.
"""

import frappe
from frappe import _

from da_services.integrations.da_registry.client import DANotFound, DARegistryUnavailable, get_client
from da_services.services import constants as C
from da_services.utils.permissions import require_da_access, require_roles


@frappe.whitelist()
def get_da(da_id: str) -> dict:
	ctx = require_roles(*C.DA_READ_ROLES)
	if not da_id:
		frappe.throw(_("da_id is required"), frappe.ValidationError)

	try:
		ref = get_client().get_da(da_id)
	except DANotFound:
		frappe.throw(_("DA {0} was not found in the registry.").format(da_id), frappe.DoesNotExistError)
	except DARegistryUnavailable:
		frappe.throw(_("The DA Registry is unavailable. Try again shortly."), frappe.ValidationError)

	# Scope is checked against the registry's own Region / Woreda for this DA, never
	# against anything the caller supplied.
	require_da_access(ref.da_id, ref.region, ref.woreda, ctx)
	return ref.to_dict()
