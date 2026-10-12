"""v1 DA dashboard (docs/api-da-screens.md 2.1, DA-198).

GET /api/v1/da-services/dashboard/summary?from=YYYY-MM-DD&to=YYYY-MM-DD[&da_id=]
GET /api/v1/da-services/dashboard/today?date=YYYY-MM-DD[&da_id=]

`da_id` is ignored for a Development Agent (always their own) and required for an
officer. The default range is the last 30 days ending today.
"""

from __future__ import annotations

import frappe
from oan_auth_service.api.utils import handle_api_errors, success_response

from da_services.api.router import route
from da_services.services import dashboard as svc
from da_services.utils.permissions import require_roles


def _query(*names: str) -> dict:
	# `from` is a Python keyword, so query parameters are read from the request, not kwargs.
	form = frappe.local.form_dict or {}
	return {n: form.get(n) for n in names}


@route("/dashboard/summary", methods=("GET",), summary="Dashboard tiles: visits, tasks, sync")
@frappe.whitelist()
@handle_api_errors
def summary(**_kwargs):
	ctx = require_roles(*svc.READ_ROLES)
	q = _query("from", "to", "da_id")
	return success_response(data=svc.summary(ctx, from_date=q["from"], to_date=q["to"], da_id=q["da_id"]))


@route("/dashboard/today", methods=("GET",), summary="Today's Plan: visits and tasks for one day")
@frappe.whitelist()
@handle_api_errors
def today(**_kwargs):
	ctx = require_roles(*svc.READ_ROLES)
	q = _query("date", "da_id")
	return success_response(data=svc.today(ctx, date=q["date"], da_id=q["da_id"]))
