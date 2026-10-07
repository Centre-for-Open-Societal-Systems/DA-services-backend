"""OAN Grievance Service client boundary.

DA Services never owns grievance data. It talks to the Grievance Service through this
interface only. Two implementations exist:

- ``MockGrievanceClient`` (mock.py): in-memory fixtures for local development and tests.
- ``HttpGrievanceClient``: the real adapter that calls the Grievance Service REST API.

Select the backend per site in ``site_config.json``::

    "grievance_backend": "mock" | "http",
    "grievance_base_url": "https://...",
    "grievance_timeout_seconds": 10
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

import frappe
import requests

from .mapper import to_grievance_detail, to_grievance_result, to_grievance_summary
from .schemas import (
	GrievanceAction,
	GrievanceDetail,
	GrievanceResult,
	GrievanceSubmission,
	GrievanceSummary,
)


class GrievanceServiceError(Exception):
	pass


class GrievanceNotFound(GrievanceServiceError):
	pass


class GrievanceServiceUnavailable(GrievanceServiceError):
	"""Transient: timeout, connection error, 5xx. Callers may retry."""


class GrievanceClient(ABC):
	@abstractmethod
	def submit_grievance(self, submission: GrievanceSubmission) -> GrievanceResult:
		"""Create a grievance (draft → submit). Returns the ticket reference."""

	@abstractmethod
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
		"""Scoped grievance list. Returns (items, total_count)."""

	@abstractmethod
	def get_grievance(self, ticket_id: str) -> GrievanceDetail:
		"""Fetch full grievance detail. Raises GrievanceNotFound."""

	@abstractmethod
	def take_action(self, action: GrievanceAction) -> GrievanceResult:
		"""Resolve, escalate, reassign, or add a note."""

	@abstractmethod
	def get_timeline(self, ticket_id: str) -> list[dict]:
		"""Fetch the timeline of events for a ticket."""

	@abstractmethod
	def get_options(self) -> dict:
		"""Fetch category / priority / status options for form dropdowns."""


class HttpGrievanceClient(GrievanceClient):
	def __init__(self, base_url: str, timeout: int = 10):
		self.base_url = base_url.rstrip("/")
		self.timeout = timeout

	def _headers(self) -> dict:
		token = frappe.request.headers.get("Authorization", "") if frappe.request else ""
		return {
			"Authorization": token,
			"Content-Type": "application/json",
			"Accept": "application/json",
		}

	def _url(self, path: str) -> str:
		return f"{self.base_url}{path}"

	def _handle_response(self, resp: requests.Response) -> dict:
		if resp.status_code == 404:
			raise GrievanceNotFound(resp.text)
		if resp.status_code >= 500:
			raise GrievanceServiceUnavailable(f"HTTP {resp.status_code}: {resp.text}")
		resp.raise_for_status()
		body = resp.json()
		return body.get("data", body)

	def submit_grievance(self, submission: GrievanceSubmission) -> GrievanceResult:
		try:
			resp = requests.post(
				self._url("/grievances"),
				json=submission.to_dict(),
				headers=self._headers(),
				timeout=self.timeout,
			)
			data = self._handle_response(resp)
			return to_grievance_result({"accepted": True, **data})
		except (requests.ConnectionError, requests.Timeout) as exc:
			raise GrievanceServiceUnavailable(str(exc)) from exc

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
		params: dict = {"page": page, "page_size": page_size}
		if region:
			params["region"] = region
		if woreda:
			params["woreda"] = woreda
		if complainant_id:
			params["complainant_id"] = complainant_id
		if status:
			params["status"] = status
		try:
			resp = requests.get(
				self._url("/grievances"),
				params=params,
				headers=self._headers(),
				timeout=self.timeout,
			)
			data = self._handle_response(resp)
			items = [to_grievance_summary(r) for r in (data.get("items") or data.get("results") or [])]
			total = int(data.get("total", data.get("total_count", len(items))))
			return items, total
		except (requests.ConnectionError, requests.Timeout) as exc:
			raise GrievanceServiceUnavailable(str(exc)) from exc

	def get_grievance(self, ticket_id: str) -> GrievanceDetail:
		try:
			resp = requests.get(
				self._url(f"/grievances/{ticket_id}"),
				headers=self._headers(),
				timeout=self.timeout,
			)
			data = self._handle_response(resp)
			return to_grievance_detail(data)
		except (requests.ConnectionError, requests.Timeout) as exc:
			raise GrievanceServiceUnavailable(str(exc)) from exc

	def take_action(self, action: GrievanceAction) -> GrievanceResult:
		try:
			resp = requests.post(
				self._url(f"/grievances/{action.ticket_id}/action"),
				json=action.to_dict(),
				headers=self._headers(),
				timeout=self.timeout,
			)
			data = self._handle_response(resp)
			return to_grievance_result({"accepted": True, **data})
		except (requests.ConnectionError, requests.Timeout) as exc:
			raise GrievanceServiceUnavailable(str(exc)) from exc

	def get_timeline(self, ticket_id: str) -> list[dict]:
		try:
			resp = requests.get(
				self._url(f"/grievances/{ticket_id}/timeline"),
				headers=self._headers(),
				timeout=self.timeout,
			)
			data = self._handle_response(resp)
			entries = data if isinstance(data, list) else data.get("entries") or []
			return entries
		except (requests.ConnectionError, requests.Timeout) as exc:
			raise GrievanceServiceUnavailable(str(exc)) from exc

	def get_options(self) -> dict:
		try:
			resp = requests.get(
				self._url("/grievances/options"),
				headers=self._headers(),
				timeout=self.timeout,
			)
			return self._handle_response(resp)
		except (requests.ConnectionError, requests.Timeout) as exc:
			raise GrievanceServiceUnavailable(str(exc)) from exc


def get_client() -> GrievanceClient:
	"""Build the configured client. Defaults to mock outside production."""
	backend = (frappe.conf.get("grievance_backend") or "mock").lower()
	if backend == "mock":
		from .mock import MockGrievanceClient

		return MockGrievanceClient.shared()
	if backend == "http":
		base_url = frappe.conf.get("grievance_base_url")
		if not base_url:
			raise GrievanceServiceError("grievance_base_url is not set in site_config.json")
		return HttpGrievanceClient(base_url, int(frappe.conf.get("grievance_timeout_seconds") or 10))
	raise GrievanceServiceError(f"Unknown grievance_backend: {backend!r}")
