"""Farmer Registry client interface and factory.

Provides a boundary to the Farmer Registry (OpenG2P-based). The client interface
defines the operations; implementations (mock, HTTP) are swapped via factory.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

import frappe

from .schemas import Farmer, FarmerListItem, Plot


class FarmerRegistryClient(ABC):
    """Abstract interface to the Farmer Registry."""

    @abstractmethod
    def get_farmer(self, farmer_id: str) -> Optional[Farmer]:
        """Get a single farmer by ID.

        Args:
            farmer_id: Farmer Registry internal_record_id

        Returns:
            Farmer object or None if not found
        """
        pass

    @abstractmethod
    def list_farmers(
        self,
        *,
        woreda: Optional[str] = None,
        kebele: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[FarmerListItem], int]:
        """List farmers with filters.

        Args:
            woreda: Filter by woreda code
            kebele: Filter by kebele code
            state: Filter by farmer state (APPROVED, etc.)
            limit: Page size
            offset: Page offset

        Returns:
            (list of farmers, total count)
        """
        pass

    @abstractmethod
    def get_farmer_plots(self, farmer_id: str) -> List[Plot]:
        """Get land plots for a farmer.

        Args:
            farmer_id: Farmer Registry internal_record_id

        Returns:
            List of Plot objects
        """
        pass

    @abstractmethod
    def update_farmer(self, farmer_id: str, updates: dict) -> dict:
        """Update farmer data (for DA-41).

        Args:
            farmer_id: Farmer Registry internal_record_id
            updates: Fields to update

        Returns:
            Update result with version info
        """
        pass


def get_farmer_registry_client() -> FarmerRegistryClient:
    """Factory: returns the configured Farmer Registry client.

    Selection order:
    1. Site config `farmer_registry_backend` ("mock" or "http")
    2. Default: "mock"

    The mock backend is safe for development and testing without a live
    Farmer Registry. Switch to "http" once the registry is deployed.
    """
    backend = frappe.conf.get("farmer_registry_backend", "mock")

    if backend == "http":
        from .http import HTTPFarmerRegistryClient

        return HTTPFarmerRegistryClient()
    else:
        from .mock import MockFarmerRegistryClient

        return MockFarmerRegistryClient()
