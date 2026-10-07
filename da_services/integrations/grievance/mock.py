"""In-memory Grievance Service for development and tests.

Fixture grievances cover the states the Grievances page has to handle: open, in-progress,
resolved, and escalated.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .client import GrievanceClient, GrievanceNotFound
from .mapper import to_grievance_detail, to_grievance_summary
from .schemas import (
	GrievanceAction,
	GrievanceDetail,
	GrievanceResult,
	GrievanceSubmission,
	GrievanceSummary,
)

_COUNTER = 100

FIXTURE_GRIEVANCES: dict[str, dict] = {
	"GRV-000001": {
		"ticket_id": "GRV-000001",
		"subject": "Fertilizer delivery delayed",
		"description": "Expected delivery on 2026-09-15 has not arrived.",
		"status": "Open",
		"priority": "High",
		"category": "Supply Chain",
		"subcategory": "Input Delivery",
		"complainant_id": "DA-000001",
		"complainant_name": "Abebe Kebede",
		"complainant_role": "Development Agent",
		"region": "ET04",
		"woreda": "ET04-W01",
		"assigned_to": None,
		"resolution": None,
		"created_at": "2026-09-20T10:00:00Z",
		"updated_at": "2026-09-20T10:00:00Z",
		"resolved_at": None,
		"timeline": [
			{
				"timestamp": "2026-09-20T10:00:00Z",
				"action": "created",
				"actor": "DA-000001",
				"detail": "Grievance submitted",
			},
		],
	},
	"GRV-000002": {
		"ticket_id": "GRV-000002",
		"subject": "Training schedule conflict",
		"description": "Two training sessions scheduled at the same time for ET04-W01-K03.",
		"status": "In Progress",
		"priority": "Medium",
		"category": "Training",
		"subcategory": "Scheduling",
		"complainant_id": "DA-000001",
		"complainant_name": "Abebe Kebede",
		"complainant_role": "Development Agent",
		"region": "ET04",
		"woreda": "ET04-W01",
		"assigned_to": "supervisor@example.com",
		"resolution": None,
		"created_at": "2026-09-18T08:30:00Z",
		"updated_at": "2026-09-19T14:00:00Z",
		"resolved_at": None,
		"timeline": [
			{
				"timestamp": "2026-09-18T08:30:00Z",
				"action": "created",
				"actor": "DA-000001",
				"detail": "Grievance submitted",
			},
			{
				"timestamp": "2026-09-19T14:00:00Z",
				"action": "assigned",
				"actor": "admin@example.com",
				"detail": "Assigned to supervisor@example.com",
			},
		],
	},
	"GRV-000003": {
		"ticket_id": "GRV-000003",
		"subject": "Incorrect KPI data recorded",
		"description": "Monthly KPI for September shows wrong crop yield figures.",
		"status": "Resolved",
		"priority": "Low",
		"category": "Data Quality",
		"subcategory": "KPI",
		"complainant_id": "DA-000002",
		"complainant_name": "Marta Tesfaye",
		"complainant_role": "Development Agent",
		"region": "ET04",
		"woreda": "ET04-W01",
		"assigned_to": "supervisor@example.com",
		"resolution": "KPI data corrected in the system.",
		"created_at": "2026-09-10T09:00:00Z",
		"updated_at": "2026-09-12T16:00:00Z",
		"resolved_at": "2026-09-12T16:00:00Z",
		"timeline": [
			{
				"timestamp": "2026-09-10T09:00:00Z",
				"action": "created",
				"actor": "DA-000002",
				"detail": "Grievance submitted",
			},
			{
				"timestamp": "2026-09-11T10:00:00Z",
				"action": "assigned",
				"actor": "admin@example.com",
				"detail": "Assigned to supervisor@example.com",
			},
			{
				"timestamp": "2026-09-12T16:00:00Z",
				"action": "resolved",
				"actor": "supervisor@example.com",
				"detail": "KPI data corrected in the system.",
			},
		],
	},
}

FIXTURE_OPTIONS: dict = {
	"categories": [
		{"value": "Supply Chain", "subcategories": ["Input Delivery", "Equipment", "Storage"]},
		{"value": "Training", "subcategories": ["Scheduling", "Content", "Logistics"]},
		{"value": "Data Quality", "subcategories": ["KPI", "Registration", "Survey"]},
		{"value": "Administrative", "subcategories": ["Leave", "Transfer", "Policy"]},
	],
	"priorities": ["Low", "Medium", "High", "Critical"],
	"statuses": ["Open", "In Progress", "Escalated", "Resolved", "Closed"],
}


class MockGrievanceClient(GrievanceClient):
	_instance: MockGrievanceClient | None = None

	def __init__(self, records: dict[str, dict] | None = None):
		self._records = {k: dict(v) for k, v in (records or FIXTURE_GRIEVANCES).items()}

	@classmethod
	def shared(cls) -> MockGrievanceClient:
		if cls._instance is None:
			cls._instance = cls()
		return cls._instance

	@classmethod
	def reset(cls) -> None:
		cls._instance = None

	def submit_grievance(self, submission: GrievanceSubmission) -> GrievanceResult:
		global _COUNTER
		_COUNTER += 1
		ticket_id = f"GRV-{_COUNTER:06d}"
		now = datetime.now(UTC).isoformat()
		record = {
			"ticket_id": ticket_id,
			"subject": submission.subject,
			"description": submission.description,
			"status": "Open",
			"priority": submission.priority,
			"category": submission.category,
			"subcategory": submission.subcategory,
			"complainant_id": submission.complainant_id,
			"complainant_name": submission.complainant_name,
			"complainant_role": submission.complainant_role,
			"region": submission.region,
			"woreda": submission.woreda,
			"assigned_to": None,
			"resolution": None,
			"created_at": now,
			"updated_at": now,
			"resolved_at": None,
			"timeline": [
				{
					"timestamp": now,
					"action": "created",
					"actor": submission.complainant_id,
					"detail": "Grievance submitted",
				}
			],
		}
		self._records[ticket_id] = record
		return GrievanceResult(
			accepted=True,
			ticket_id=ticket_id,
			message="Grievance created",
			raw={"created_at": now},
		)

	def list_grievances(
		self,
		*,
		region: str | None = None,
		woreda: str | None = None,
		complainant_id: str | None = None,
		status: str | None = None,
		page: int = 1,
		page_size: int = 20,
	) -> tuple[list[GrievanceSummary], int]:
		filtered = list(self._records.values())
		if region:
			filtered = [r for r in filtered if r.get("region") == region]
		if woreda:
			filtered = [r for r in filtered if r.get("woreda") == woreda]
		if complainant_id:
			filtered = [r for r in filtered if r.get("complainant_id") == complainant_id]
		if status:
			filtered = [r for r in filtered if r.get("status") == status]

		total = len(filtered)
		start = (page - 1) * page_size
		page_items = filtered[start : start + page_size]
		return [to_grievance_summary(r) for r in page_items], total

	def get_grievance(self, ticket_id: str) -> GrievanceDetail:
		record = self._records.get(ticket_id)
		if not record:
			raise GrievanceNotFound(ticket_id)
		return to_grievance_detail(record)

	def take_action(self, action: GrievanceAction) -> GrievanceResult:
		record = self._records.get(action.ticket_id)
		if not record:
			raise GrievanceNotFound(action.ticket_id)

		now = datetime.now(UTC).isoformat()
		record["updated_at"] = now

		if action.action_type == "resolve":
			record["status"] = "Resolved"
			record["resolution"] = action.resolution or action.comment
			record["resolved_at"] = now
		elif action.action_type == "escalate":
			record["status"] = "Escalated"
		elif action.action_type == "reassign":
			record["assigned_to"] = action.assigned_to
		elif action.action_type == "close":
			record["status"] = "Closed"

		timeline = record.setdefault("timeline", [])
		timeline.append(
			{
				"timestamp": now,
				"action": action.action_type,
				"actor": action.assigned_to or "system",
				"detail": action.comment,
			}
		)
		return GrievanceResult(
			accepted=True, ticket_id=action.ticket_id, message=f"Action '{action.action_type}' applied"
		)

	def get_timeline(self, ticket_id: str) -> list[dict]:
		record = self._records.get(ticket_id)
		if not record:
			raise GrievanceNotFound(ticket_id)
		return record.get("timeline") or []

	def get_options(self) -> dict:
		return FIXTURE_OPTIONS
