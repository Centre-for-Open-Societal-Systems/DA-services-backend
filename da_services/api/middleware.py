"""Bind oan_auth_service's JWT validation to this app's own method namespace.

The ``/api/v1/da`` REST routes are protected by the shared ``/api/v1`` namespace
(see api/router.py). This module additionally claims the RPC form of our
endpoints, ``/api/method/da_services.*``, so a caller cannot sidestep the bearer
token by invoking the whitelisted function directly.
"""

# Only requests under this prefix are subject to JWT validation here; Desk and
# Frappe's standard APIs keep Frappe's own session auth.
API_NAMESPACE = "/api/method/da_services."

# Reachable without a token. Kept explicit so adding one is a visible diff.
EXEMPT_PATHS: list[str] = [
	"/api/method/da_services.api.router.get_health",
]


def register() -> None:
	try:
		from oan_auth_service.api.middleware import register_namespace

		register_namespace(API_NAMESPACE, EXEMPT_PATHS)
	except ImportError:
		# oan_auth_service is a required app; this only guards import-time ordering.
		pass


register()
