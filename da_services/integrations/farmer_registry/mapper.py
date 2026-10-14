"""Mapper: Farmer Registry ↔ DA backend field transformations.

Handles naming and format differences between systems.
"""

from typing import Any, Dict

from .schemas import Farmer


def farmer_to_reference_dict(farmer: Farmer) -> dict[str, Any]:
    """Map Farmer Registry schema → DA Farmer Reference fields.

    Args:
        farmer: Farmer object from registry

    Returns:
        Dict suitable for DA Farmer Reference doctype
    """
    return {
        "farmer_id": farmer.farmer_id,
        "reg_id": farmer.reg_id,
        "farmer_name": farmer.record_name or f"{farmer.given_name or ''} {farmer.family_name or ''}".strip(),
        "given_name": farmer.given_name,
        "family_name": farmer.family_name,
        "father_name": farmer.father_first_name,
        "phone": farmer.phone,
        "email": farmer.email,
        "region": farmer.region_name,
        "zone": farmer.zone_name,
        "woreda": farmer.woreda_name,
        "kebele": farmer.kebele_name,
        "gender": farmer.gender,
        "education_level": farmer.education_level,
        "household_size": farmer.household_size,
        "total_land_hectares": farmer.total_land_area,
        "land_ownership_type": farmer.land_ownership,
        "registration_state": farmer.state,
        "registered_at": farmer.registration_date,
        "source_of_income": farmer.source_of_income,
        "is_psnp_beneficiary": farmer.is_psnp_user,
    }


def reference_dict_to_profile(ref_dict: dict[str, Any], visit_data: dict[str, Any]) -> dict[str, Any]:
    """Merge farmer reference + visit data → profile response (DA-40).

    Args:
        ref_dict: DA Farmer Reference fields
        visit_data: Latest visit info from DA Visit service

    Returns:
        Combined profile for frontend
    """
    return {
        # Identity
        "farmer_id": ref_dict.get("farmer_id"),
        "reg_id": ref_dict.get("reg_id"),
        "name": ref_dict.get("farmer_name"),
        "kebele": ref_dict.get("kebele"),
        # Verification (Fayda ignored per user request)
        "verification_state": None,  # TODO: Add when Fayda integration is ready
        # Work status
        "pending_actions": visit_data.get("pending_task_count", 0),
        # Contact
        "phone": ref_dict.get("phone"),
        "email": ref_dict.get("email"),
        # Household
        "household_size": ref_dict.get("household_size"),
        # Land
        "total_land_area": ref_dict.get("total_land_hectares"),
        "land_ownership": ref_dict.get("land_ownership_type"),
        # Agriculture
        "primary_crop": None,  # TODO: Query from Crop table when needed
        # Registration
        "registration_date": ref_dict.get("registered_at"),
        # Field activity
        "last_visit_date": visit_data.get("last_visit_date"),
        "last_visit_outcome": visit_data.get("last_visit_outcome"),
        # Additional
        "region": ref_dict.get("region"),
        "woreda": ref_dict.get("woreda"),
        "gender": ref_dict.get("gender"),
        "education_level": ref_dict.get("education_level"),
        "source_of_income": ref_dict.get("source_of_income"),
    }
