"""Tests for Family F — Upcoming Events tools.

Coverage:
  1. Happy path — World Cup + closures appear for a summer-2026 window
  2. Schema validity — tools registered; schema present
  3. Input validation — ValidationError on bad inputs
  4. Filtering — by kind, category, bbox, window
  5. Determinism — same input → same output
  6. get_event — by id, and unknown id
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.common import BBox
from app.schemas.events import EventCategory, EventKind
from app.tools.events import (
    FindUpcomingEventsArgs,
    GetEventArgs,
    find_upcoming_events,
    get_event,
)
from app.tools.registry import get_tool

# Just before the World Cup; a 60-day window covers June–July 2026.
AS_OF = date(2026, 6, 1)
BMO_BBOX = BBox(west=-79.43, south=43.62, east=-79.40, north=43.64)


# 1. Happy path -------------------------------------------------------------
def test_finds_world_cup_and_closures():
    out = find_upcoming_events(FindUpcomingEventsArgs(as_of=AS_OF, days_ahead=60))
    assert out["count"] > 0
    ids = {e["id"] for e in out["events"]}
    assert "wc-2026-06-12" in ids               # opening match
    assert "ttc-line1-stclair-eglinton-2026-06-13" in ids  # a closure
    # sorted ascending by start
    starts = [e["start"] for e in out["events"]]
    assert starts == sorted(starts)


# 2. Schema validity --------------------------------------------------------
def test_tools_registered():
    assert get_tool("find_upcoming_events").input_model is FindUpcomingEventsArgs
    assert get_tool("get_event").input_model is GetEventArgs
    assert "properties" in FindUpcomingEventsArgs.model_json_schema()


# 3. Input validation -------------------------------------------------------
def test_bad_window_rejected():
    with pytest.raises(ValidationError):
        FindUpcomingEventsArgs(days_ahead=0)


def test_bad_bbox_rejected():
    with pytest.raises(ValidationError):
        FindUpcomingEventsArgs(bbox=BBox(west=0, south=0, east=-1, north=1))


# 4. Filtering --------------------------------------------------------------
def test_filter_by_kind_supply_disruption():
    out = find_upcoming_events(
        FindUpcomingEventsArgs(as_of=date(2026, 5, 29), days_ahead=30,
                               kinds=[EventKind.supply_disruption])
    )
    assert out["count"] >= 1
    assert all(e["kind"] == "supply_disruption" for e in out["events"])


def test_filter_by_category_sports():
    out = find_upcoming_events(
        FindUpcomingEventsArgs(as_of=AS_OF, days_ahead=60, categories=[EventCategory.sports])
    )
    assert all(e["category"] == "sports" for e in out["events"])
    assert any(e["id"].startswith("wc-2026") for e in out["events"])


def test_filter_by_bbox_keeps_bmo_field():
    out = find_upcoming_events(
        FindUpcomingEventsArgs(as_of=AS_OF, days_ahead=60, bbox=BMO_BBOX,
                               categories=[EventCategory.sports])
    )
    # All returned point-located events sit inside the bbox.
    for e in out["events"]:
        lat, lon = e["venue"]["lat"], e["venue"]["lon"]
        if lat is not None and lon is not None:
            assert BMO_BBOX.west <= lon <= BMO_BBOX.east
            assert BMO_BBOX.south <= lat <= BMO_BBOX.north


def test_window_excludes_quiet_period():
    # A 1-day window before any event (incl. the May–Dec construction) is empty.
    out = find_upcoming_events(FindUpcomingEventsArgs(as_of=date(2026, 4, 1), days_ahead=1))
    assert out["count"] == 0


# 5. Determinism ------------------------------------------------------------
def test_deterministic():
    a = find_upcoming_events(FindUpcomingEventsArgs(as_of=AS_OF, days_ahead=60))
    b = find_upcoming_events(FindUpcomingEventsArgs(as_of=AS_OF, days_ahead=60))
    assert a == b


# 6. get_event --------------------------------------------------------------
def test_get_event_by_id():
    out = get_event(GetEventArgs(id="wc-2026-06-12"))
    assert out["event"] is not None
    assert out["event"]["venue"]["name"].startswith("BMO Field")
    assert out["event"]["impact"]["expected_attendance"] == 30000


def test_get_event_unknown():
    out = get_event(GetEventArgs(id="does-not-exist"))
    assert out["event"] is None
    assert "known_ids" in out
