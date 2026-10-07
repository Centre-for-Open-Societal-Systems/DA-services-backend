"""Typed shapes exchanged with the OAN Grievance Service.

Same principle as da_registry/schemas.py: these are *our* projection, not the upstream
contract.  mapper.py translates raw payloads into these so the rest of the app never
sees transport details.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class GrievanceSubmission:
	"""Payload DA Services sends to create a grievance on behalf of a DA or supervisor."""

	complainant_id: str
	complainant_name: str
	complainant_role: str
	region: str | None = None
	woreda: str | None = None
	category: str = ""
	subcategory: str = ""
	subject: str = ""
	description: str = ""
	priority: str = "Medium"
	attachments: list[str] = field(default_factory=list)

	def to_dict(self) -> dict:
		return asdict(self)


@dataclass(frozen=True)
class GrievanceAction:
	"""An action taken on a grievance ticket (resolve, escalate, add note, etc.)."""

	ticket_id: str
	action_type: str
	comment: str = ""
	resolution: str | None = None
	assigned_to: str | None = None

	def to_dict(self) -> dict:
		return asdict(self)


@dataclass(frozen=True)
class GrievanceSummary:
	"""Read-model for grievance list views."""

	ticket_id: str
	subject: str
	status: str
	priority: str
	category: str
	complainant_name: str
	created_at: str | None = None
	updated_at: str | None = None

	def to_dict(self) -> dict:
		return asdict(self)


@dataclass(frozen=True)
class GrievanceDetail:
	"""Full grievance record returned by the upstream service."""

	ticket_id: str
	subject: str
	description: str
	status: str
	priority: str
	category: str
	subcategory: str
	complainant_id: str
	complainant_name: str
	complainant_role: str
	region: str | None = None
	woreda: str | None = None
	assigned_to: str | None = None
	resolution: str | None = None
	created_at: str | None = None
	updated_at: str | None = None
	resolved_at: str | None = None
	timeline: list[dict] = field(default_factory=list)

	def to_dict(self) -> dict:
		return asdict(self)


@dataclass(frozen=True)
class TimelineEntry:
	"""One event in a grievance's history."""

	timestamp: str
	action: str
	actor: str
	detail: str = ""

	def to_dict(self) -> dict:
		return asdict(self)


@dataclass(frozen=True)
class GrievanceResult:
	"""What came back from the grievance service for a write operation."""

	accepted: bool
	ticket_id: str | None = None
	message: str | None = None
	retryable: bool = False
	raw: dict = field(default_factory=dict)
