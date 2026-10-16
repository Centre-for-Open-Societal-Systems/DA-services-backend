"""A2C (Access to Credit) client interface - CONFIGURABLE.

A2C is a Frappe app on the same bench as DA Services. This client queries
A2C's Loan Application doctype directly for credit status integration.

All A2C-specific names (doctype, fields, statuses) are configurable via
site_config.json to handle future changes without code modification.

Configuration Example (site_config.json):
{
    "a2c_backend": "direct",
    "a2c_application_doctype": "Loan Application",
    "a2c_farmer_id_field": "farmer_id",
    "a2c_status_field": "status",
    "a2c_active_statuses": [
        "Submitted",
        "Under Review",
        "Document Review",
        "Credit Assessment",
        "Final Approval"
    ]
}
"""

from abc import ABC, abstractmethod

import frappe
from frappe import _

# Default configuration (can be overridden in site_config.json)
DEFAULT_CONFIG = {
	"application_doctype": "Loan Application",
	"farmer_id_field": "farmer_id",
	"status_field": "status",
	"active_statuses": [
		"Submitted",
		"Under Review",
		"Document Review",
		"Credit Assessment",
		"Final Approval",
		"Pending Bank Review",
	],
}


def get_a2c_config(key: str, default=None):
	"""Get A2C configuration from site_config.json with fallback to defaults.

	Args:
	    key: Configuration key (e.g., "application_doctype")
	    default: Fallback value if not in config or defaults

	Returns:
	    Configuration value
	"""
	config_key = f"a2c_{key}"
	value = frappe.conf.get(config_key)

	if value is not None:
		return value

	return DEFAULT_CONFIG.get(key, default)


class A2CClient(ABC):
	"""Abstract interface to A2C service."""

	@abstractmethod
	def has_active_application(self, farmer_id: str) -> bool:
		"""Check if farmer has any active credit application.

		Args:
		    farmer_id: Farmer Registry internal_record_id

		Returns:
		    True if farmer has application under review
		"""
		pass


class DirectA2CClient(A2CClient):
	"""Direct database client for A2C (same Frappe bench).

	Queries A2C doctypes directly using configurable doctype/field names.
	"""

	def __init__(self):
		"""Initialize with configurable A2C settings."""
		# Load configuration
		self.application_doctype = get_a2c_config("application_doctype")
		self.farmer_id_field = get_a2c_config("farmer_id_field")
		self.status_field = get_a2c_config("status_field")
		self.active_statuses = get_a2c_config("active_statuses")

		# Validate configuration
		if not self.application_doctype:
			frappe.throw(_("A2C application doctype not configured"))

	def has_active_application(self, farmer_id: str) -> bool:
		"""Fast check for active applications using configured fields.

		Args:
		    farmer_id: Farmer Registry internal_record_id

		Returns:
		    True if any active application exists
		"""
		try:
			# Check if doctype exists (handles A2C not installed)
			if not frappe.db.exists("DocType", self.application_doctype):
				frappe.log_error(
					title="A2C Integration Warning",
					message=f"Doctype '{self.application_doctype}' does not exist. A2C may not be installed.",
				)
				return False

			# Build filters dynamically using configured field names
			filters = {
				self.farmer_id_field: farmer_id,
				self.status_field: ["in", self.active_statuses],
			}

			count = frappe.db.count(self.application_doctype, filters=filters)
			return count > 0

		except Exception as e:
			# Log error but don't break the pending action derivation
			frappe.log_error(
				title="A2C Integration Error",
				message=f"Failed to check applications for {farmer_id} in {self.application_doctype}: {e!s}",
			)
			return False

	def get_configuration(self) -> dict:
		"""Get current A2C configuration for debugging.

		Returns:
		    Dict with current configuration values
		"""
		return {
			"application_doctype": self.application_doctype,
			"farmer_id_field": self.farmer_id_field,
			"status_field": self.status_field,
			"active_statuses": self.active_statuses,
		}


class MockA2CClient(A2CClient):
	"""Mock A2C client for testing without A2C app installed."""

	def has_active_application(self, farmer_id: str) -> bool:
		"""Always return False (no applications)."""
		return False


def get_a2c_client() -> A2CClient:
	"""Factory: returns configured A2C client.

	Auto-detects if A2C app is installed using configured doctype name.
	Falls back to mock client if A2C is not available.

	Configuration:
	    Set "a2c_backend" in site_config.json:
	    - "direct": Use DirectA2CClient (same bench)
	    - "mock": Use MockA2CClient (testing)
	    - null/unset: Auto-detect based on doctype existence

	Returns:
	    A2CClient instance
	"""
	backend = frappe.conf.get("a2c_backend")

	# Auto-detect if not configured
	if not backend:
		try:
			application_doctype = get_a2c_config("application_doctype")
			if frappe.db.exists("DocType", application_doctype):
				backend = "direct"
			else:
				backend = "mock"
		except Exception:
			backend = "mock"

	if backend == "direct":
		return DirectA2CClient()
	else:
		return MockA2CClient()


def validate_a2c_configuration() -> dict:
	"""Validate A2C configuration and return status.

	Returns:
	    Dict with validation results:
	    {
	        "configured": bool,
	        "doctype_exists": bool,
	        "config": dict,
	        "errors": list
	    }
	"""
	errors = []
	config = {}

	# Load configuration
	try:
		client = DirectA2CClient()
		config = client.get_configuration()

		# Check if doctype exists
		doctype_exists = frappe.db.exists("DocType", config["application_doctype"])

		if not doctype_exists:
			errors.append(f"Doctype '{config['application_doctype']}' not found")

		# Check if fields exist in doctype
		if doctype_exists:
			meta = frappe.get_meta(config["application_doctype"])

			if not meta.has_field(config["farmer_id_field"]):
				errors.append(f"Field '{config['farmer_id_field']}' not found in {config['application_doctype']}")

			if not meta.has_field(config["status_field"]):
				errors.append(f"Field '{config['status_field']}' not found in {config['application_doctype']}")

		return {
			"configured": True,
			"doctype_exists": doctype_exists,
			"config": config,
			"errors": errors,
			"valid": len(errors) == 0,
		}

	except Exception as e:
		return {
			"configured": False,
			"doctype_exists": False,
			"config": {},
			"errors": [str(e)],
			"valid": False,
		}
