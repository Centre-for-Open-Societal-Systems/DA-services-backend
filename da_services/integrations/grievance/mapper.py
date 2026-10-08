"""Translate grievance service payloads into our schemas.

Field names on the right-hand side are the Grievance Service API contract names.
Change them here and nowhere else.
"""

from __future__ import annotations

from .schemas import GrievanceDetail, GrievanceResult, GrievanceSummary, TimelineEntry


def to_grievance_summary(payload: dict) -> GrievanceSummary:
	return GrievanceSummary(
		ticket_id=str(payload["ticket_id"]),
		subject=payload.get("subject") or "",
		status=payload.get("status") or "",
		priority=payload.get("priority") or "Medium",
		category=payload.get("category") or "",
		complainant_name=payload.get("complainant_name") or "",
		created_at=payload.get("created_at"),
		updated_at=payload.get("updated_at"),
	)


def to_grievance_detail(payload: dict) -> GrievanceDetail:
	raw_timeline = payload.get("timeline") or []
	timeline = [to_timeline_entry(e).to_dict() for e in raw_timeline]
	return GrievanceDetail(
		ticket_id=str(payload["ticket_id"]),
		subject=payload.get("subject") or "",
		description=payload.get("description") or "",
		status=payload.get("status") or "",
		priority=payload.get("priority") or "Medium",
		category=payload.get("category") or "",
		subcategory=payload.get("subcategory") or "",
		complainant_id=str(payload.get("complainant_id") or ""),
		complainant_name=payload.get("complainant_name") or "",
		complainant_role=payload.get("complainant_role") or "",
		region=payload.get("region"),
		woreda=payload.get("woreda"),
		assigned_to=payload.get("assigned_to"),
		resolution=payload.get("resolution"),
		created_at=payload.get("created_at"),
		updated_at=payload.get("updated_at"),
		resolved_at=payload.get("resolved_at"),
		timeline=timeline,
	)


def to_timeline_entry(payload: dict) -> TimelineEntry:
	return TimelineEntry(
		timestamp=payload.get("timestamp") or "",
		action=payload.get("action") or "",
		actor=payload.get("actor") or "",
		detail=payload.get("detail") or "",
	)


def to_grievance_result(payload: dict) -> GrievanceResult:
	return GrievanceResult(
		accepted=bool(payload.get("accepted", False)),
		ticket_id=payload.get("ticket_id"),
		message=payload.get("message"),
		retryable=bool(payload.get("retryable", False)),
		raw=payload,
	)
