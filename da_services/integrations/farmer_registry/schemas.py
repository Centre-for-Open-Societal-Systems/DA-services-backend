"""Pydantic schemas for Farmer Registry data.

Models match the Farmer Registry's OpenG2P-based schema (farmer.py models).
Only fields needed for DA-40 profile display are included.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class FarmerIdentity(BaseModel):
    """Farmer identification and basic info."""

    farmer_id: str = Field(..., description="Farmer Registry ID (internal_record_id)")
    reg_id: Optional[str] = Field(None, description="External Farmer-ID (FR-xxxxx)")
    given_name: Optional[str] = Field(None, description="First name (English)")
    family_name: Optional[str] = Field(None, description="Last name (English)")
    father_first_name: Optional[str] = Field(None, description="Father's first name")
    first_name_amh: Optional[str] = Field(None, description="First name (Amharic)")
    first_name_om: Optional[str] = Field(None, description="First name (Afaan Oromo)")
    record_name: Optional[str] = Field(None, description="Display name (from registry)")


class FarmerContact(BaseModel):
    """Farmer contact information."""

    phone: Optional[str] = Field(None, description="Primary phone number")
    email: Optional[str] = Field(None, description="Email address")
    has_personal_phone: bool = Field(False, description="Has a personal phone")


class FarmerLocation(BaseModel):
    """Farmer geographic location."""

    region_name: Optional[str] = Field(None, description="Region name")
    zone_name: Optional[str] = Field(None, description="Zone name")
    woreda_name: Optional[str] = Field(None, description="Woreda name")
    kebele_name: Optional[str] = Field(None, description="Kebele name")
    woreda_level_value_id: Optional[str] = Field(None, description="Woreda ID for filtering")


class FarmerDemographics(BaseModel):
    """Farmer demographic information."""

    birth_date: Optional[date] = Field(None, description="Birth date (Gregorian)")
    birth_date_ec: Optional[str] = Field(None, description="Birth date (Ethiopian calendar)")
    estimated_age: Optional[int] = Field(None, description="Estimated age in years")
    gender: Optional[str] = Field(None, description="Gender (male/female/other)")
    disabled: bool = Field(False, description="Has disability")
    disability_type: Optional[str] = Field(None, description="Type of disability")
    language_spoken: Optional[str] = Field(None, description="Primary language")
    education_level: Optional[str] = Field(None, description="Education level")


class FarmerHousehold(BaseModel):
    """Farmer household information."""

    is_household_head: bool = Field(False, description="Is head of household")
    size_of_group: Optional[int] = Field(None, description="Household size (from Household table)")
    number_of_children: Optional[int] = Field(None, description="Number of children")


class FarmerSocioeconomic(BaseModel):
    """Farmer socio-economic data."""

    source_of_income: Optional[str] = Field(None, description="Primary source of income")
    is_psnp_user: bool = Field(False, description="PSNP beneficiary")
    national_id_masked: Optional[str] = Field(None, description="Masked national ID")


class FarmerLand(BaseModel):
    """Farmer land holdings summary."""

    total_land_area: Optional[float] = Field(None, description="Total land area (hectares)")
    total_land_owned_area: Optional[float] = Field(None, description="Owned land (hectares)")
    total_land_rent_area: Optional[float] = Field(None, description="Rented land (hectares)")
    land_ownership: Optional[str] = Field(None, description="Ownership type (OWNER/TENANT/HYBRID)")


class FarmerRegistration(BaseModel):
    """Farmer registration metadata."""

    state: str = Field("APPROVED", description="Farmer state (DRAFT/PENDING_APPROVAL/APPROVED)")
    import_source: Optional[str] = Field(None, description="Data source (INTAKE_FORM/PARTNER/etc)")
    registration_date: Optional[datetime] = Field(None, description="When registered")
    is_duplicated: bool = Field(False, description="Flagged as potential duplicate")
    enumerator_name: Optional[str] = Field(None, description="Enumerator who collected data")


class Farmer(BaseModel):
    """Complete farmer record (DA-40 profile view).

    Combines all farmer data needed for the DA profile screen.
    """

    # Identity
    farmer_id: str = Field(..., description="Farmer Registry ID")
    reg_id: Optional[str] = Field(None, description="External Farmer-ID")
    given_name: Optional[str] = Field(None, description="First name")
    family_name: Optional[str] = Field(None, description="Last name")
    father_first_name: Optional[str] = Field(None, description="Father's first name")
    record_name: Optional[str] = Field(None, description="Display name")

    # Contact
    phone: Optional[str] = None
    email: Optional[str] = None
    has_personal_phone: bool = False

    # Location
    region_name: Optional[str] = None
    zone_name: Optional[str] = None
    woreda_name: Optional[str] = None
    kebele_name: Optional[str] = None

    # Demographics
    birth_date: Optional[date] = None
    gender: Optional[str] = None
    education_level: Optional[str] = None

    # Household
    is_household_head: bool = False
    household_size: Optional[int] = Field(None, description="From Household table")

    # Land
    total_land_area: Optional[float] = None
    land_ownership: Optional[str] = None

    # Registration
    state: str = "APPROVED"
    registration_date: Optional[datetime] = None

    # Socio-economic
    source_of_income: Optional[str] = None
    is_psnp_user: bool = False


class FarmerListItem(BaseModel):
    """Farmer list item for /farmers endpoint."""

    farmer_id: str
    reg_id: Optional[str] = None
    name: str = Field(..., description="Display name")
    phone: Optional[str] = None
    kebele: Optional[str] = None
    woreda: Optional[str] = None
    region: Optional[str] = None
    total_land_area: Optional[float] = None
    state: str
    registration_date: Optional[datetime] = None


class Plot(BaseModel):
    """Land plot information for /farmers/{id}/plots."""

    plot_id: str = Field(..., description="Land record ID")
    land_kebele: Optional[str] = Field(None, description="Plot kebele")
    area_in_hectare: Optional[float] = Field(None, description="Area in hectares")
    land_ownership_type: Optional[str] = Field(None, description="OWNER/TENANT/etc")
    soil_fertility: Optional[str] = None
    current_land_use: Optional[str] = None
    certificate_provided: bool = False
