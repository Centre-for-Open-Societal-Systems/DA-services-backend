"""REST routing initialization for DA Services.

Integrates with oan_auth_service.api.router by declaring routes using @prefixed(...)
or @rest(...), and ensuring all rules are registered into Frappe's API_URL_MAP.
"""

import threading

import frappe
from oan_auth_service.api.middleware import register_namespace
from oan_auth_service.api.router import (
	NAMESPACE,
	_exempt_paths,
	_rules,
	prefixed,
	rest,
)
from oan_auth_service.api.router import (
	ensure_routes_registered as ensure_auth_routes,
)
from oan_auth_service.api.utils import handle_api_errors, success_response

_REGISTERED = False
_REGISTRATION_LOCK = threading.Lock()

root_route = prefixed("/api/v1")


@root_route("/da-services/health", methods=("GET",), allow_guest=True, summary="DA Services health check")
@frappe.whitelist(allow_guest=True)
@handle_api_errors
def get_health():
	"""Health check endpoint for DA Services."""
	return success_response(
		data={
			"status": "healthy",
			"service": "da_services",
			"api_version": "v1",
		}
	)


def ensure_routes_registered() -> None:
	"""Add every declared DA Services route to Frappe's URL map and claim the namespace."""
	global _REGISTERED
	if _REGISTERED:
		return

	with _REGISTRATION_LOCK:
		if _REGISTERED:
			return
		_register()
		_REGISTERED = True


def _register() -> None:
	import frappe.api

	from da_services.api import middleware
	from da_services.api.middleware import check_da_assignment

	ensure_auth_routes()

	for rule in _rules:
		if rule not in frappe.api.API_URL_MAP._rules:
			frappe.api.API_URL_MAP.add(rule.empty())

	register_namespace(
		prefix=NAMESPACE, exempt_paths=sorted(_exempt_paths), revocation_check=check_da_assignment
	)
