"""v1 Grievance API: proxy to OAN Grievance Service, scoped by the caller's RBAC.

Writes that fail against the upstream service are queued in DA Integration Event and
retried automatically. Reads are pass-through; if the upstream is down the caller gets
a 503 error.
"""

from __future__ import annotations

import frappe
from frappe import _
from oan_auth_service.api.router import prefixed
from oan_auth_service.api.utils import error_response, handle_api_errors, success_response

from da_services.integrations.grievance.client import (
	GrievanceNotFound,
	GrievanceServiceUnavailable,
	get_client,
)
from da_services.integrations.grievance.queue import enqueue_event, retry_failed
from da_services.integrations.grievance.schemas import GrievanceSubmission
from da_services.services import constants as C
from da_services.utils.permissions import require_roles

grievance_route = prefixed("/api/v1/da-services")

_UNAVAILABLE_MSG = _("Grievance Service is currently unavailable. Try again shortly.")


@grievance_route("/grievances", methods=("GET",), summary="List grievances scoped to caller")
@frappe.whitelist()
@handle_api_errors
def list_grievances():
	ctx = require_roles(*C.GRIEVANCE_ROLES)

	status_filter = frappe.form_dict.get("status")
	page = int(frappe.form_dict.get("page", 1))
	page_size = min(int(frappe.form_dict.get("page_size", 20)), 100)

	kwargs: dict = {"page": page, "page_size": page_size}
	if status_filter:
		kwargs["status"] = status_filter

	if ctx.has_any_role(C.ROLE_DA):
		da_ids = list(ctx.da_ids)
		if da_ids:
			kwargs["complainant_id"] = da_ids if len(da_ids) > 1 else da_ids[0]
	elif not ctx.unrestricted:
		if ctx.woreda_scopes:
			woredas = list(ctx.woreda_scopes)
			kwargs["woreda"] = woredas if len(woredas) > 1 else woredas[0]
		elif ctx.region_scopes:
			regions = list(ctx.region_scopes)
			kwargs["region"] = regions if len(regions) > 1 else regions[0]

	try:
		client = get_client()
		items, total = client.list_grievances(**kwargs)
		return success_response(
			data=[g.to_dict() for g in items],
			meta={"page": page, "page_size": page_size, "total": total},
		)
	except GrievanceServiceUnavailable:
		frappe.response["http_status_code"] = 503
		return error_response(str(_UNAVAILABLE_MSG), "SERVICE_UNAVAILABLE")


@grievance_route("/grievances", methods=("POST",), summary="Submit a new grievance")
@frappe.whitelist()
@handle_api_errors
def submit_grievance():
	ctx = require_roles(*C.GRIEVANCE_ROLES)

	body = frappe.request.get_json(silent=True) or {}
	subject = body.get("subject", "").strip()
	description = body.get("description", "").strip()
	category = body.get("category", "").strip()
	subcategory = body.get("subcategory", "").strip()
	priority = body.get("priority", "Medium").strip()
	raised_for = body.get("raised_for", "Self").strip()
	farmer_id = (body.get("farmer_id") or "").strip() or None
	client_op_id = (body.get("client_op_id") or "").strip() or None

	if not subject:
		frappe.throw(_("Subject is required."), frappe.ValidationError)

	if raised_for == "Farmer" and not farmer_id:
		frappe.throw(_("farmer_id is required when raised_for is Farmer."), frappe.ValidationError)

	complainant_id, complainant_name = _resolve_complainant_identity(ctx)

	submission = GrievanceSubmission(
		complainant_id=complainant_id,
		complainant_name=complainant_name,
		complainant_role=_resolve_complainant_role(ctx),
		region=sorted(ctx.region_scopes)[0] if ctx.region_scopes else None,
		woreda=sorted(ctx.woreda_scopes)[0] if ctx.woreda_scopes else None,
		category=category,
		subcategory=subcategory,
		subject=subject,
		description=description,
		priority=priority,
		raised_for=raised_for,
		farmer_id=farmer_id,
		attachments=body.get("attachments") or [],
	)

	reference_id = client_op_id or f"{complainant_id}:{subject[:50]}"

	try:
		client = get_client()
		result = client.submit_grievance(submission)
		frappe.response["http_status_code"] = 201
		return success_response(
			data={
				"ticket_id": result.ticket_id,
				"sync_state": "synced",
				"message": result.message,
			},
		)
	except GrievanceServiceUnavailable:
		event_name = enqueue_event(
			event_type="Grievance Submit",
			payload=submission.to_dict(),
			reference_id=reference_id,
		)
		frappe.response["http_status_code"] = 201
		return success_response(
			data={
				"ticket_id": None,
				"sync_state": "pending",
				"queue_ref": event_name,
				"message": "Grievance queued for submission — the service is temporarily unavailable.",
			},
		)


@grievance_route("/grievances/<ticket_id>", methods=("GET",), summary="Get grievance detail")
@frappe.whitelist()
@handle_api_errors
def get_grievance(ticket_id: str):
	require_roles(*C.GRIEVANCE_ROLES)

	try:
		client = get_client()
		detail = client.get_grievance(ticket_id)
		return success_response(data=detail.to_dict())
	except GrievanceNotFound:
		frappe.throw(_("Grievance {0} not found.").format(ticket_id), frappe.DoesNotExistError)
	except GrievanceServiceUnavailable:
		frappe.response["http_status_code"] = 503
		return error_response(str(_UNAVAILABLE_MSG), "SERVICE_UNAVAILABLE")


@grievance_route("/grievances/<ticket_id>/timeline", methods=("GET",), summary="Get grievance timeline")
@frappe.whitelist()
@handle_api_errors
def get_timeline(ticket_id: str):
	require_roles(*C.GRIEVANCE_ROLES)

	try:
		client = get_client()
		entries = client.get_timeline(ticket_id)
		return success_response(data=entries)
	except GrievanceNotFound:
		frappe.throw(_("Grievance {0} not found.").format(ticket_id), frappe.DoesNotExistError)
	except GrievanceServiceUnavailable:
		frappe.response["http_status_code"] = 503
		return error_response(str(_UNAVAILABLE_MSG), "SERVICE_UNAVAILABLE")


@grievance_route(
	"/grievances/options", methods=("GET",), allow_guest=False, summary="Get grievance form options"
)
@frappe.whitelist()
@handle_api_errors
def get_options():
	require_roles(*C.GRIEVANCE_ROLES)

	try:
		client = get_client()
		options = client.get_options()
		return success_response(data=options)
	except GrievanceServiceUnavailable:
		frappe.response["http_status_code"] = 503
		return error_response(str(_UNAVAILABLE_MSG), "SERVICE_UNAVAILABLE")


@grievance_route("/grievances/sync/retry", methods=("POST",), summary="Retry failed integration events")
@frappe.whitelist()
@handle_api_errors
def retry_sync():
	require_roles(C.ROLE_ADMIN)

	body = frappe.request.get_json(silent=True) or {}
	event_name = body.get("event_name")

	retried = retry_failed(event_name)
	return success_response(
		data={"retried": retried, "count": len(retried)},
	)


def _resolve_complainant_identity(ctx) -> tuple[str, str]:
	"""Derive complainant identity from the RBAC context — never from the request body."""
	if ctx.has_any_role(C.ROLE_DA) and ctx.da_ids:
		da_id = sorted(ctx.da_ids)[0]
		full_name = frappe.get_value("User", ctx.user, "full_name") or ctx.user
		return da_id, full_name
	full_name = frappe.get_value("User", ctx.user, "full_name") or ctx.user
	return ctx.user, full_name


def _resolve_complainant_role(ctx) -> str:
	for role in (C.ROLE_DA, C.ROLE_SUPERVISOR, C.ROLE_EXECUTIVE, C.ROLE_ADMIN):
		if ctx.has_any_role(role):
			return role
	return "Unknown"
