from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.maps.registry import MapRegistry, PhysicalRegion


class UnsupportedGeometryError(ValueError):
    """Raised when a registered geometry cannot be evaluated by coordinates yet."""


def contains_point(
    region: PhysicalRegion,
    x: float,
    y: float,
    z: float | None = None,
    *,
    registry: MapRegistry | None = None,
) -> bool:
    geometry = region.geometry
    geometry_type = str(geometry.get("type") or "")
    boundary_policy = str(region.boundary_policy or "existing_behavior")
    if geometry_type == "bounding_box":
        return point_in_bounding_box(x, y, z, geometry, boundary_policy=boundary_policy)
    if geometry_type == "polygon":
        return point_in_polygon(x, y, geometry.get("points") or geometry.get("vertices") or [])
    if geometry_type == "composite":
        if registry is None:
            raise UnsupportedGeometryError("Composite geometry requires a map registry.")
        member_ids = geometry.get("member_regions") or geometry.get("region_ids") or []
        return any(
            contains_point(member, x, y, z, registry=registry)
            for member_id in member_ids
            if (member := registry.get_region(str(member_id))) is not None
        )
    if geometry_type in {"named_area", "existing_definition"}:
        raise UnsupportedGeometryError(
            f"Geometry type {geometry_type} for region {region.region_id} is place-name based and cannot be evaluated by coordinates."
        )
    raise UnsupportedGeometryError(f"Unsupported geometry type for region {region.region_id}: {geometry_type}")


def point_in_bounding_box(
    x: float,
    y: float,
    z: float | None,
    geometry: dict[str, Any],
    *,
    boundary_policy: str,
) -> bool:
    x_min = geometry.get("x_min")
    x_max = geometry.get("x_max")
    y_min = geometry.get("y_min")
    y_max = geometry.get("y_max")
    if x_min is None or x_max is None or y_min is None or y_max is None:
        raise UnsupportedGeometryError("Bounding box geometry requires x_min, x_max, y_min, and y_max.")

    in_xy = in_range(float(x), float(x_min), float(x_max), boundary_policy) and in_range(float(y), float(y_min), float(y_max), boundary_policy)
    if not in_xy:
        return False

    z_min = geometry.get("z_min")
    z_max = geometry.get("z_max")
    if z_min is None and z_max is None:
        return True
    if z is None:
        return False
    if z_min is not None and not in_range(float(z), float(z_min), float("inf") if z_max is None else float(z_max), boundary_policy):
        return False
    if z_max is not None and not in_range(float(z), float("-inf") if z_min is None else float(z_min), float(z_max), boundary_policy):
        return False
    return True


def in_range(value: float, lower: float, upper: float, boundary_policy: str) -> bool:
    if boundary_policy == "exclusive":
        return lower < value < upper
    if boundary_policy == "half_open":
        return lower <= value < upper
    return lower <= value <= upper


def point_in_polygon(x: float, y: float, points: Sequence[Any]) -> bool:
    vertices = [coerce_point(point) for point in points]
    if len(vertices) < 3:
        raise UnsupportedGeometryError("Polygon geometry requires at least three points.")
    inside = False
    j = len(vertices) - 1
    for i, (xi, yi) in enumerate(vertices):
        xj, yj = vertices[j]
        intersects = (yi > y) != (yj > y) and x < ((xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def coerce_point(point: Any) -> tuple[float, float]:
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"])
    if isinstance(point, Sequence) and len(point) >= 2 and not isinstance(point, str):
        return float(point[0]), float(point[1])
    raise UnsupportedGeometryError(f"Invalid polygon point: {point!r}")
