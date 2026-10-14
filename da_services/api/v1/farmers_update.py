"""v1: Farmer profile update API (DA-41).

PATCH /api/v1/da-services/farmers/{id}

Implements offline-first farmer profile updates with:
- Permission validation (linked farmers only)
- Field validation (approved fields only)
- Offline queue with retry
- Version conflict detection
"""

from __future__ import annotations

import frappe
from frappe import _
from oan_auth_service.api.utils import handle_api_errors, success_response

from da_services.api.router import route
from da_services.services import constants as C
from da_services.services import farmer_updates
from da_services.utils.permissions import require_roles

# Roles that can update farmers (DA only)
WRITE_ROLES = (C.ROLE_DA,)


@route("/farmers/<farmer_id>", methods=("PATCH",), summary="Update farmer profile")
@frappe.whitelist()
@handle_api_errors
def update_farmer_profile(farmer_id: str):
	"""Update farmer profile (DA-41 offline-first update).

	Only editable fields can be updated:
	- Basic contact: phone, email, alternative_contact
	- Household: household_size, dependents
	- Socio-economic: occupation, income_source, livelihood_type
	- Land: total_land_hectares, land_tenure, irrigated_land
	- Certifications: certifications, training_status

	Identity fields (farmer_name, national_id, etc.) cannot be updated.

	Updates are queued for offline sync. The endpoint returns immediately
	with queue reference. Actual sync happens in background with retry.

	Scope selector:
	- Development Agent: Can update ONLY linked farmers
	- Supervisor/Executive/Admin: Cannot update (read-only access)

	Args:
	    farmer_id: Farmer Registry internal_record_id (path parameter)

	Request body (JSON):
	    {
	        "phone": "912345678",        // Optional
	        "email": "new@example.com",  // Optional
	        "household_size": 5,         // Optional
	        ... // Other editable fields
	        "client_op_id": "unique-key" // Optional idempotency key
	    }

	Returns:
	    {
	        "success": true,
	        "message": "Update queued successfully",
	        "data": {
	            "farmer_id": "farmer-uuid-001",
	            "event_id": "DA-INT-00123",
	            "status": "queued",
	            "updates": {
	                "phone": "912345678",
	                "email": "new@example.com"
	            }
	        }
	    }

	Raises:
	    ValidationError (400):
	        - Missing farmer_id
	        - No fields to update
	        - Invalid field (readonly or unknown)
	        - Invalid field value (format, range)
	    PermissionError (403):
	        - Farmer not linked to current DA
	        - User is not DA role
	    DoesNotExistError (404):
	        - Farmer not found in Registry

	Example:
	    PATCH /api/v1/da-services/farmers/farmer-uuid-001
	    Authorization: Bearer <da_token>
	    Content-Type: application/json

	    {
	        "phone": "912345678",
	        "email": "farmer@example.com",
	        "household_size": 6
	    }

	    Response (200 OK):
	    {
	        "status": "success",
	        "message": "Update queued successfully. Will sync when online.",
	        "data": {
	            "farmer_id": "farmer-uuid-001",
	            "event_id": "DA-INT-00123",
	            "status": "queued",
	            "updates": {
	                "phone": "912345678",
	                "email": "farmer@example.com",
	                "household_size": 6
	            },
	            "queued_at": "2026-10-14T10:30:00"
	        }
	    }
	"""
	ctx = require_roles(*WRITE_ROLES)

	# Validate farmer_id
	if not farmer_id or not isinstance(farmer_id, str):
		frappe.throw(_("Farmer ID is required."), frappe.ValidationError)

	# Get update fields from request body
	request_data = frappe.request.get_json() if frappe.request else frappe.form_dict
	if not request_data:
		frappe.throw(_("Request body is required."), frappe.ValidationError)

	# Extract client_op_id if provided (for idempotency)
	client_op_id = request_data.pop("client_op_id", None)

	# Remaining fields are the updates
	updates = request_data

	if not updates:
		frappe.throw(_("No fields to update."), frappe.ValidationError)

	# Queue farmer update (validates permissions, fields, and values)
	event_id = farmer_updates.queue_farmer_update(
		farmer_id=farmer_id,
		updates=updates,
		ctx=ctx,
		client_op_id=client_op_id,
	)

	# Return success with queue reference
	return success_response(
		message=_("Update queued successfully. Will sync when online."),
		data={
			"farmer_id": farmer_id,
			"event_id": event_id,
			"status": "queued",
			"updates": updates,
			"queued_at": frappe.utils.now(),
		},
	)


@route("/farmers/<farmer_id>/update-status", methods=("GET",), summary="Get farmer update sync status")
@frappe.whitelist()
@handle_api_errors
def get_farmer_update_status(farmer_id: str):
	"""Get sync status of pending farmer updates.

	Shows all pending/processing updates for a farmer with retry status.

	Args:
	    farmer_id: Farmer Registry internal_record_id

	Returns:
	    {
	        "success": true,
	        "data": {
	            "farmer_id": "farmer-uuid-001",
	            "pending_updates": [
	                {
	                    "event_id": "DA-INT-00123",
	                    "status": "Pending",
	                    "attempts": 2,
	                    "next_retry": "2026-10-14T10:35:00",
	                    "last_error": "Connection timeout",
	                    "queued_at": "2026-10-14T10:30:00"
	                }
	            ],
	            "total_pending": 1
	        }
	    }
	"""
	require_roles(*WRITE_ROLES)

	if not farmer_id:
		frappe.throw(_("Farmer ID is required."), frappe.ValidationError)

	# Get pending updates for this farmer
	pending = farmer_updates.get_pending_updates(farmer_id)

	return success_response(
		data={
			"farmer_id": farmer_id,
			"pending_updates": pending,
			"total_pending": len(pending),
		}
	)


@route("/farmers/updates/<event_id>/retry", methods=("POST",), summary="Manually retry failed farmer update")
@frappe.whitelist()
@handle_api_errors
def retry_farmer_update(event_id: str):
	"""Manually retry a failed farmer update (Admin only).

	Resets event status to Pending and triggers immediate retry.

	Args:
	    event_id: DA Integration Event document name

	Returns:
	    {
	        "success": true,
	        "message": "Retry triggered",
	        "data": {
	            "event_id": "DA-INT-00123"
	        }
	    }

	Raises:
	    DoesNotExistError (404): Event not found
	    ValidationError (400): Event not in Failed/Conflict status
	"""
	require_roles(C.ROLE_ADMIN)  # Admin only

	if not event_id:
		frappe.throw(_("Event ID is required."), frappe.ValidationError)

	# Trigger retry
	result = farmer_updates.retry_failed_update(event_id)

	return success_response(message=result["message"], data={"event_id": event_id})
