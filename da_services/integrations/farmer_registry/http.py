"""HTTP client for live Farmer Registry (OpenG2P-based).

Connects to the Farmer Registry Staff API at the configured base URL.
Supports configurable API routes and versioning via site_config.json.

Configuration Example:
    {
        "farmer_registry_backend": "http",
        "farmer_registry_url": "http://farmer-registry:8080",
        "farmer_registry_api_key": "your-api-key",
        "farmer_registry_api_version": "v1",
        "farmer_registry_endpoints": {
            "get_farmer": "/api/{version}/registry/farmer/{farmer_id}",
            "list_farmers": "/api/{version}/registry/farmer",
            "get_plots": "/api/{version}/registry/land",
            "update_farmer": "/api/{version}/registry/farmer/{farmer_id}"
        }
    }
"""

from typing import List, Optional

import requests
import frappe
from frappe import _

from .client import FarmerRegistryClient
from .schemas import Farmer, FarmerListItem, Plot


class HTTPFarmerRegistryClient(FarmerRegistryClient):
    """HTTP client for live Farmer Registry with configurable routes."""

    # Default endpoint templates (can be overridden in config)
    DEFAULT_ENDPOINTS = {
        "get_farmer": "/api/{version}/registry/farmer/{farmer_id}",
        "list_farmers": "/api/{version}/registry/farmer",
        "get_plots": "/api/{version}/registry/land",
        "update_farmer": "/api/{version}/registry/farmer/{farmer_id}",
    }

    def __init__(self):
        """Initialize HTTP client with configurable endpoints."""
        # Base configuration
        self.base_url = frappe.conf.get("farmer_registry_url", "http://farmer-registry:8080")
        self.api_key = frappe.conf.get("farmer_registry_api_key")
        self.timeout = frappe.conf.get("farmer_registry_timeout", 30)  # seconds

        # API version (configurable for v1, v2, etc.)
        self.api_version = frappe.conf.get("farmer_registry_api_version", "v1")

        # Configurable endpoint paths with defaults
        self.endpoints = frappe.conf.get("farmer_registry_endpoints", self.DEFAULT_ENDPOINTS)

        # HTTP headers
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Add authentication if API key is configured
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def _build_url(self, endpoint_key: str, **params) -> str:
        """Build URL from configurable endpoint template.

        Args:
            endpoint_key: Key in self.endpoints dict (e.g., "get_farmer")
            **params: URL parameters to substitute (e.g., farmer_id="123")

        Returns:
            Complete URL with base_url + endpoint path

        Example:
            _build_url("get_farmer", farmer_id="farmer-uuid-001")
            → "http://farmer-registry:8080/api/v1/registry/farmer/farmer-uuid-001"
        """
        template = self.endpoints.get(endpoint_key, self.DEFAULT_ENDPOINTS.get(endpoint_key))

        if not template:
            frappe.throw(_("Endpoint '{0}' not configured").format(endpoint_key))

        # Replace {version} placeholder
        path = template.replace("{version}", self.api_version)

        # Replace other placeholders like {farmer_id}
        try:
            path = path.format(**params)
        except KeyError as e:
            frappe.throw(_("Missing URL parameter: {0}").format(str(e)))

        return f"{self.base_url}{path}"

    def get_farmer(self, farmer_id: str) -> Optional[Farmer]:
        """Get farmer details via HTTP GET.

        Args:
            farmer_id: Farmer Registry internal_record_id

        Returns:
            Farmer object or None if not found

        Raises:
            requests.RequestException: If HTTP request fails
        """
        url = self._build_url("get_farmer", farmer_id=farmer_id)

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)

            # Handle 404 - farmer not found
            if response.status_code == 404:
                return None

            # Raise for other errors (4xx, 5xx)
            response.raise_for_status()

            # Parse JSON response and convert to Farmer schema
            data = response.json()
            return Farmer(**data)

        except requests.RequestException as e:
            frappe.log_error(
                title="Farmer Registry HTTP Error",
                message=f"Failed to get farmer {farmer_id} from {url}: {str(e)}"
            )
            raise

    def list_farmers(
        self,
        *,
        woreda: Optional[str] = None,
        kebele: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[FarmerListItem], int]:
        """List farmers via HTTP GET with query parameters.

        Args:
            woreda: Filter by woreda code
            kebele: Filter by kebele name
            state: Filter by registration state
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            Tuple of (list of farmers, total count)

        Raises:
            requests.RequestException: If HTTP request fails
        """
        url = self._build_url("list_farmers")

        # Build query parameters
        params = {
            "limit": limit,
            "offset": offset,
        }

        if woreda:
            params["woreda"] = woreda
        if kebele:
            params["kebele"] = kebele
        if state:
            params["state"] = state

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()

            # Parse response - expecting {"results": [...], "total": N}
            farmers = [FarmerListItem(**f) for f in data.get("results", [])]
            total = data.get("total", 0)

            return farmers, total

        except requests.RequestException as e:
            frappe.log_error(
                title="Farmer Registry HTTP Error",
                message=f"Failed to list farmers from {url}: {str(e)}"
            )
            raise

    def get_farmer_plots(self, farmer_id: str) -> List[Plot]:
        """Get farmer's land plots via HTTP GET.

        Args:
            farmer_id: Farmer Registry internal_record_id

        Returns:
            List of Plot objects

        Raises:
            requests.RequestException: If HTTP request fails
        """
        url = self._build_url("get_plots")

        params = {
            "link_internal_record_id": farmer_id,
            "limit": 100,  # Get all plots for this farmer
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()

            # Parse plots from response
            plots = [Plot(**p) for p in data.get("results", [])]

            return plots

        except requests.RequestException as e:
            frappe.log_error(
                title="Farmer Registry HTTP Error",
                message=f"Failed to get plots for {farmer_id} from {url}: {str(e)}"
            )
            raise

    def update_farmer(self, farmer_id: str, updates: dict) -> dict:
        """Update farmer via HTTP PUT.

        Args:
            farmer_id: Farmer Registry internal_record_id
            updates: Dictionary of fields to update

        Returns:
            Updated farmer data as dict

        Raises:
            requests.RequestException: If HTTP request fails
        """
        url = self._build_url("update_farmer", farmer_id=farmer_id)

        try:
            response = requests.put(url, headers=self.headers, json=updates, timeout=self.timeout)
            response.raise_for_status()

            # Return updated farmer data
            return response.json()

        except requests.RequestException as e:
            frappe.log_error(
                title="Farmer Registry HTTP Error",
                message=f"Failed to update farmer {farmer_id} at {url}: {str(e)}"
            )
            raise
