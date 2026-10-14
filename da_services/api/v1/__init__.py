"""Versioned public API contract (v1). Breaking changes ship as a new version segment alongside this one."""

# Import API modules to register routes
from . import (
	assignments,
	common,
	da,
	dashboard,
	farmers,
	farmers_update,
	grievance,
	me,
	notifications,
	profile,
	rbac,
	visits,
)
