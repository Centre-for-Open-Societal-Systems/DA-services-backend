"""Mock Farmer Registry client for development and testing.

Returns fixture data matching the OpenG2P Farmer Registry schema. Safe to use
without a live Farmer Registry instance.
"""

from datetime import date, datetime

from .client import FarmerRegistryClient
from .schemas import Farmer, FarmerListItem, Plot

# Mock farmer data matching Farmer Registry schema
MOCK_FARMERS = {
    "farmer-uuid-001": Farmer(
        farmer_id="farmer-uuid-001",
        reg_id="FR-000101",
        given_name="Abebe",
        family_name="Kebede",
        father_first_name="Kebede",
        record_name="Abebe Kebede",
        phone="911234567",
        email="abebe@example.com",
        has_personal_phone=True,
        region_name="ET04",
        zone_name="ET04-Z01",
        woreda_name="ET04-W01",
        kebele_name="Bako 01",
        birth_date=date(1985, 3, 15),
        gender="male",
        education_level="Primary",
        is_household_head=True,
        household_size=5,
        total_land_area=2.5,
        land_ownership="OWNER",
        state="APPROVED",
        registration_date=datetime(2024, 6, 1, 10, 30),
        source_of_income="Crop production",
        is_psnp_user=False,
    ),
    "farmer-uuid-002": Farmer(
        farmer_id="farmer-uuid-002",
        reg_id="FR-000102",
        given_name="Almaz",
        family_name="Tesfaye",
        father_first_name="Tesfaye",
        record_name="Almaz Tesfaye",
        phone="922345678",
        email=None,
        has_personal_phone=True,
        region_name="ET04",
        zone_name="ET04-Z01",
        woreda_name="ET04-W01",
        kebele_name="Bako 02",
        birth_date=date(1990, 7, 22),
        gender="female",
        education_level="Secondary",
        is_household_head=False,
        household_size=4,
        total_land_area=1.8,
        land_ownership="TENANT",
        state="APPROVED",
        registration_date=datetime(2024, 6, 15, 14, 20),
        source_of_income="Mixed farming",
        is_psnp_user=True,
    ),
    "farmer-uuid-003": Farmer(
        farmer_id="farmer-uuid-003",
        reg_id="FR-000103",
        given_name="Chaltu",
        family_name="Deressa",
        father_first_name="Deressa",
        record_name="Chaltu Deressa",
        phone="933456789",
        email="chaltu@example.com",
        has_personal_phone=True,
        region_name="ET03",
        zone_name="ET03-Z01",
        woreda_name="ET03-W02",
        kebele_name="Kebele 03",
        birth_date=date(1988, 11, 5),
        gender="female",
        education_level="Tertiary",
        is_household_head=True,
        household_size=6,
        total_land_area=3.2,
        land_ownership="HYBRID",
        state="APPROVED",
        registration_date=datetime(2024, 5, 20, 9, 15),
        source_of_income="Livestock and crops",
        is_psnp_user=False,
    ),
}

# Mock plots
MOCK_PLOTS = {
    "farmer-uuid-001": [
        Plot(
            plot_id="plot-001-1",
            land_kebele="Bako 01",
            area_in_hectare=2.5,
            land_ownership_type="OWNER",
            soil_fertility="Good",
            current_land_use="CROP_PRODUCTION",
            certificate_provided=True,
        ),
    ],
    "farmer-uuid-002": [
        Plot(
            plot_id="plot-002-1",
            land_kebele="Bako 02",
            area_in_hectare=1.8,
            land_ownership_type="TENANT",
            soil_fertility="Medium",
            current_land_use="CROP_PRODUCTION",
            certificate_provided=False,
        ),
    ],
    "farmer-uuid-003": [
        Plot(
            plot_id="plot-003-1",
            land_kebele="Bako 01",
            area_in_hectare=2.0,
            land_ownership_type="OWNER",
            soil_fertility="Good",
            current_land_use="CROP_PRODUCTION",
            certificate_provided=True,
        ),
        Plot(
            plot_id="plot-003-2",
            land_kebele="Bako 01",
            area_in_hectare=1.2,
            land_ownership_type="TENANT",
            soil_fertility="Medium",
            current_land_use="GRAZING",
            certificate_provided=False,
        ),
    ],
}


class MockFarmerRegistryClient(FarmerRegistryClient):
    """Mock implementation for development without live Farmer Registry."""

    def get_farmer(self, farmer_id: str) -> Farmer | None:
        """Get farmer from mock fixtures."""
        return MOCK_FARMERS.get(farmer_id)

    def list_farmers(
        self,
        *,
        woreda: str | None = None,
        kebele: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FarmerListItem], int]:
        """List mock farmers with filters."""
        farmers = list(MOCK_FARMERS.values())

        # Apply filters
        if woreda:
            farmers = [f for f in farmers if f.woreda_name == woreda]
        if kebele:
            farmers = [f for f in farmers if f.kebele_name == kebele]
        if state:
            farmers = [f for f in farmers if f.state == state]

        total = len(farmers)

        # Pagination
        farmers = farmers[offset : offset + limit]

        # Convert to list items
        items = [
            FarmerListItem(
                farmer_id=f.farmer_id,
                reg_id=f.reg_id,
                name=f.record_name or f"{f.given_name} {f.family_name}",
                phone=f.phone,
                kebele=f.kebele_name,
                woreda=f.woreda_name,
                region=f.region_name,
                total_land_area=f.total_land_area,
                state=f.state,
                registration_date=f.registration_date,
            )
            for f in farmers
        ]

        return items, total

    def get_farmer_plots(self, farmer_id: str) -> list[Plot]:
        """Get mock plots for a farmer."""
        return MOCK_PLOTS.get(farmer_id, [])

    def update_farmer(self, farmer_id: str, updates: dict) -> dict:
        """Mock update (for DA-41, not implemented yet)."""
        return {
            "success": True,
            "farmer_id": farmer_id,
            "version": 1,
            "message": "Mock update - not persisted",
        }
