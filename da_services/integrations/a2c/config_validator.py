"""A2C Configuration Validator - Command-line utility.

Usage:
    bench console
    >>> from da_services.integrations.a2c.config_validator import check_a2c_config
    >>> check_a2c_config()
"""

import frappe

from .client import get_a2c_client, validate_a2c_configuration


def check_a2c_config(verbose=True):
	"""Check and display A2C configuration status.

	Args:
	    verbose: Print detailed output

	Returns:
	    True if configuration is valid
	"""
	result = validate_a2c_configuration()

	if verbose:
		print("\n" + "=" * 60)
		print("A2C INTEGRATION CONFIGURATION CHECK")
		print("=" * 60 + "\n")

		# Overall status
		status = "✅ VALID" if result["valid"] else "❌ INVALID"
		print(f"Status: {status}\n")

		# Configuration details
		if result["configured"]:
			print("Configuration:")
			config = result["config"]
			print(f"  Doctype:       {config.get('application_doctype', 'N/A')}")
			print(f"  Farmer Field:  {config.get('farmer_id_field', 'N/A')}")
			print(f"  Status Field:  {config.get('status_field', 'N/A')}")
			print(f"  Active Statuses: {len(config.get('active_statuses', []))} configured")
			for status in config.get("active_statuses", []):
				print(f"    - {status}")
			print()

		# Doctype existence
		doctype_status = "✅ EXISTS" if result["doctype_exists"] else "❌ NOT FOUND"
		print(f"Doctype Existence: {doctype_status}")

		# Errors
		if result["errors"]:
			print(f"\n⚠️  Errors ({len(result['errors'])}):")
			for i, error in enumerate(result["errors"], 1):
				print(f"  {i}. {error}")
		else:
			print("\n✅ No errors found")

		# Client type
		client = get_a2c_client()
		client_type = type(client).__name__
		print(f"\nClient Type: {client_type}")

		# Test query (if valid)
		if result["valid"]:
			try:
				test_farmer_id = "test-farmer-123"
				has_app = client.has_active_application(test_farmer_id)
				print(f"\n✅ Test Query: Success (farmer '{test_farmer_id}' has application: {has_app})")
			except Exception as e:
				print(f"\n❌ Test Query Failed: {e}")

		print("\n" + "=" * 60 + "\n")

	return result["valid"]


def print_site_config_template():
	"""Print site_config.json template for A2C configuration."""
	template = """{
  "_comment": "A2C Integration Configuration",

  "a2c_backend": "direct",

  "a2c_application_doctype": "Loan Application",
  "a2c_farmer_id_field": "farmer_id",
  "a2c_status_field": "status",

  "a2c_active_statuses": [
    "Submitted",
    "Under Review",
    "Document Review",
    "Credit Assessment",
    "Final Approval",
    "Pending Bank Review"
  ]
}"""

	print("\nSITE_CONFIG.JSON TEMPLATE:")
	print("=" * 60)
	print(template)
	print("=" * 60)
	print("\nCopy relevant sections to your site_config.json")
	print("Location: sites/<your-site>/site_config.json\n")


def fix_a2c_config_interactive():
	"""Interactive A2C configuration fixer.

	Guides user through fixing configuration issues.
	"""
	result = validate_a2c_configuration()

	print("\n" + "=" * 60)
	print("A2C CONFIGURATION FIXER")
	print("=" * 60 + "\n")

	if result["valid"]:
		print("✅ Configuration is already valid. No changes needed.\n")
		return

	print("⚠️  Configuration issues detected:\n")
	for error in result["errors"]:
		print(f"  - {error}")

	print("\n" + "-" * 60)
	print("RECOMMENDED FIXES:")
	print("-" * 60 + "\n")

	if not result["doctype_exists"]:
		print("1. Install A2C app:")
		print("   bench --site <site-name> install-app oan_a2c\n")
		print("   OR\n")
		print("2. Configure correct doctype name:")
		print('   bench --site <site-name> set-config a2c_application_doctype "Correct Name"\n')

	for error in result["errors"]:
		if "Field" in error and "not found" in error:
			print("3. Check field names in A2C doctype:")
			print("   bench console")
			print(f"   >>> meta = frappe.get_meta('{result['config'].get('application_doctype')}')")
			print("   >>> [f.fieldname for f in meta.fields]\n")

	print("-" * 60)
	print("\nFor detailed help, see: docs/A2C-INTEGRATION-CONFIG.md\n")


if __name__ == "__main__":
	# Run check when executed directly
	check_a2c_config()
