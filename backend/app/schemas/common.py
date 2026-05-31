"""Common request/response schemas reused across tools and routers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BBox(BaseModel):
    """A geographic bounding box in WGS84 (lon/lat)."""

    west: float = Field(..., description="Minimum longitude")
    south: float = Field(..., description="Minimum latitude")
    east: float = Field(..., description="Maximum longitude")
    north: float = Field(..., description="Maximum latitude")
