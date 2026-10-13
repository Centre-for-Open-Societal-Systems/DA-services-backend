"""Geofence check: is a point inside an administrative boundary? (FSD FR-05, DA-38)

Pure functions over GeoJSON so they can be unit-tested without a site. Boundaries are
WGS84 Polygon / MultiPolygon with ``[lng, lat]`` rings, as every GIS export gives them.
Ray casting is enough at Kebele scale; holes (inner rings) are honoured.
"""

from __future__ import annotations

NOT_CHECKED = "Not checked"
IN_BOUNDARY = "In-boundary"
OUT_OF_BOUNDS = "Out-of-bounds"


def _in_ring(lng: float, lat: float, ring: list) -> bool:
	inside = False
	n = len(ring)
	for i in range(n):
		x1, y1 = ring[i][0], ring[i][1]
		x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
		if (y1 > lat) != (y2 > lat):
			x_at = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
			if lng < x_at:
				inside = not inside
	return inside


def _in_polygon(lng: float, lat: float, rings: list) -> bool:
	if not rings or not _in_ring(lng, lat, rings[0]):
		return False
	return not any(_in_ring(lng, lat, hole) for hole in rings[1:])


def point_in_boundary(lat: float, lng: float, boundary: dict) -> bool:
	"""True when (lat, lng) lies inside the GeoJSON Polygon / MultiPolygon."""
	kind = (boundary or {}).get("type")
	coords = (boundary or {}).get("coordinates") or []
	if kind == "Polygon":
		return _in_polygon(lng, lat, coords)
	if kind == "MultiPolygon":
		return any(_in_polygon(lng, lat, poly) for poly in coords)
	if kind == "Feature":
		return point_in_boundary(lat, lng, boundary.get("geometry") or {})
	raise ValueError(f"Unsupported GeoJSON type: {kind!r}")


def check(
	lat: float | None, lng: float | None, boundary: dict | None, area_label: str = ""
) -> tuple[str, str]:
	"""(result, reason) for the assignment screen.

	Not checked when either the DA position or the boundary is missing: the assignment
	still goes through, with the reason on record, rather than blocking every Kebele
	until GIS data exists.
	"""
	if lat is None or lng is None:
		return NOT_CHECKED, "DA position not available"
	if not boundary:
		return NOT_CHECKED, f"No boundary data for {area_label or 'this Kebele'}"
	try:
		inside = point_in_boundary(float(lat), float(lng), boundary)
	except (ValueError, TypeError, IndexError) as exc:
		return NOT_CHECKED, f"Boundary data unreadable: {exc}"
	if inside:
		return IN_BOUNDARY, f"DA position inside {area_label or 'the Kebele'} boundary"
	return OUT_OF_BOUNDS, f"DA position outside {area_label or 'the Kebele'} boundary"
