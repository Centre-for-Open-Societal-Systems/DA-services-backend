"""Small helpers shared by the v1 endpoint modules."""

from __future__ import annotations

import json

import frappe
from frappe import _


def request_fields(kwargs: dict, *names: str, json_keys: tuple[str, ...] = ()) -> dict:
	"""Named request fields: the JSON body when there is one, else the call's kwargs.

	`json_keys` are nested values (objects / lists) that a form post may send as strings.
	"""
	request = getattr(frappe.local, "request", None)
	data = (request.get_json(silent=True) if request is not None else None) or {}
	out = {n: data.get(n, kwargs.get(n)) for n in names}
	for key in json_keys:
		if isinstance(out.get(key), str):
			try:
				out[key] = json.loads(out[key])
			except ValueError:
				frappe.throw(_("{0} must be JSON.").format(key), frappe.ValidationError)
	return out


def truthy(value) -> bool:
	return str(value).lower() in ("1", "true", "yes", "on")
