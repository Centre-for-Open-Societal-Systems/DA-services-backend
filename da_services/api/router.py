"""REST routes for DA Services on top of oan_auth_service's router.

oan_auth_service owns the ``/api/v1`` namespace, the ``@rest``/``prefixed`` decorators,
the JWT middleware and the response envelope. This module only declares where our
routes live (``/api/v1/da/...``), imports the endpoint modules so their decorators
run, and adds the resulting rules to Frappe's URL map in every worker process.

Clean paths matter because the UI reaches us through Kong, which routes by path
prefix; ``/api/method/da_services.api...`` would still work but is not what the
gateway or the API contract uses.
"""

import threading

import frappe
from oan_auth_service.api.middleware import register_namespace
from oan_auth_service.api.router import NAMESPACE, _exempt_paths, _rules, prefixed
from oan_auth_service.api.router import ensure_routes_registered as ensure_auth_routes
from oan_auth_service.api.utils import handle_api_errors, success_response

# Every DA Services route hangs off this prefix. The auth app keeps /api/v1/auth/*
# and /api/v1/me for itself.
PREFIX = "/api/v1/da"
route = prefixed(PREFIX)

_REGISTERED = False
_REGISTRATION_LOCK = threading.Lock()


@route("/health", methods=("GET",), allow_guest=True, summary="DA Services health check")
@frappe.whitelist(allow_guest=True)  # nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
@handle_api_errors
def get_health():
	return success_response(data={"status": "healthy", "service": "da_services", "api_version": "v1"})


def ensure_routes_registered() -> None:
	"""Wired as a ``before_request`` hook; runs once per worker process."""
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

	# The auth routes (login, refresh, /me) must exist before ours.
	ensure_auth_routes()

	# Importing the endpoint modules executes their @route(...) registrations.
	from da_services.api.v1 import da, me, rbac

	# Rules compare by pattern; skip any the auth app or a hot reload already bound.
	for rule in _rules:
		if rule not in frappe.api.API_URL_MAP._rules:
			frappe.api.API_URL_MAP.add(rule.empty())

	register_namespace(prefix=NAMESPACE, exempt_paths=sorted(_exempt_paths))

	from da_services.api.middleware import register as register_method_namespace

	register_method_namespace()
