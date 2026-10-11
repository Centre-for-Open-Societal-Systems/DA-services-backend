"""v1 notifications: the bell list for the signed-in user (data-model 5.10, DA-196).

GET  /api/v1/da-services/notifications?unread=1&limit=20&start=0
POST /api/v1/da-services/notifications/<name>/read
POST /api/v1/da-services/notifications/read-all

A user only ever sees and changes their own rows; the service enforces it.
"""

from __future__ import annotations

import frappe
from oan_auth_service.api.utils import handle_api_errors, success_response

from da_services.api.router import route
from da_services.services import constants as C
from da_services.services import notifications as svc
from da_services.utils.permissions import require_roles


@route("/notifications", methods=("GET",), summary="My notifications")
@frappe.whitelist()
@handle_api_errors
def list_notifications(unread=None, limit=20, start=0):
	ctx = require_roles(*C.DA_SERVICES_ROLES)
	want_unread = str(unread).lower() in ("1", "true", "yes") if unread is not None else False
	rows, meta = svc.list_notifications(ctx, unread=want_unread, limit=limit, start=start)
	return success_response(data=rows, meta=meta)


@route("/notifications/read-all", methods=("POST",), summary="Mark all my notifications read")
@frappe.whitelist(methods=["POST"])
@handle_api_errors
def read_all():
	ctx = require_roles(*C.DA_SERVICES_ROLES)
	return success_response(data=svc.mark_all_read(ctx), message="All notifications marked read")


@route("/notifications/<notification_id>/read", methods=("POST",), summary="Mark one notification read")
@frappe.whitelist(methods=["POST"])
@handle_api_errors
def read_one(notification_id: str):
	ctx = require_roles(*C.DA_SERVICES_ROLES)
	return success_response(data=svc.mark_read(notification_id, ctx), message="Notification marked read")
