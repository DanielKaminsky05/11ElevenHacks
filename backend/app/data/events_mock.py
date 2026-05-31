"""Mock events service.

Stands in for real ingestion (venue schedules, the City Festivals & Events
dataset, TTC service alerts, and a news tier) behind one interface:
``MockEventsProvider.fetch()`` returns a list of :class:`Event`. Swap this class
for a live provider later — the tool layer only depends on ``fetch()``.

The data below is **real, researched** upcoming Toronto activity for 2026
(FIFA World Cup at BMO Field, Blue Jays home games, summer festivals, and a TTC
Line 2 closure) — but it is hard-coded, hence ``source="mock"``. Times are
Eastern (EDT, UTC-4).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from app.schemas.events import (
    Event,
    EventCategory,
    EventKind,
    Magnitude,
    TransitImpact,
    Venue,
)

ET = timezone(timedelta(hours=-4))  # Eastern Daylight Time

# --- venues (WGS84) -------------------------------------------------------
BMO_FIELD = Venue(name="BMO Field (Toronto Stadium)", lat=43.6332, lon=-79.4185)
ROGERS_CENTRE = Venue(name="Rogers Centre", lat=43.6414, lon=-79.3894)
SCOTIABANK_ARENA = Venue(name="Scotiabank Arena", lat=43.6435, lon=-79.3791)
EXHIBITION_PLACE = Venue(name="Exhibition Place / Lakeshore", lat=43.6326, lon=-79.4185)
CHURCH_WELLESLEY = Venue(name="Church-Wellesley Village", lat=43.6656, lon=-79.3806)
MTCC = Venue(name="Metro Toronto Convention Centre", lat=43.6427, lon=-79.3860)
LINE2_WEST = Venue(name="Line 2: Jane–Ossington", lat=43.6556, lon=-79.4500)
LINE1_MIDTOWN = Venue(name="Line 1: St Clair–Eglinton", lat=43.6920, lon=-79.3960)
EGLINTON_CORRIDOR = Venue(name="Eglinton Ave (Crosstown corridor)", lat=43.7050, lon=-79.3900)


def _dt(y: int, m: int, d: int, h: int = 0, mn: int = 0) -> datetime:
    return datetime(y, m, d, h, mn, tzinfo=ET)


def _match(idx: str, day: int, hour: int, teams: str, mag: Magnitude, attendance: int) -> Event:
    """Helper for the World Cup group-stage / knockout matches at BMO Field."""
    return Event(
        id=f"wc-2026-06-{day:02d}" if day <= 30 else f"wc-2026-07-{day - 30:02d}",
        title=f"FIFA World Cup 26 — {teams}",
        category=EventCategory.sports,
        kind=EventKind.demand_surge,
        venue=BMO_FIELD,
        start=_dt(2026, 6, day, hour) if day <= 30 else _dt(2026, 7, day - 30, hour),
        end=_dt(2026, 6, day, hour + 3) if day <= 30 else _dt(2026, 7, day - 30, hour + 3),
        impact=TransitImpact(
            magnitude=mag, expected_attendance=attendance, radius_km=2.5
        ),
        description=f"World Cup match at BMO Field. {teams}. Major arrival/departure surge "
        "on Line 1 (Exhibition/Bathurst), GO Lakeshore, and 509/511 streetcars.",
        source="mock",
    )


# --- the mock catalogue ---------------------------------------------------
_EVENTS: list[Event] = [
    # ===== FIFA World Cup 2026 — BMO Field (6 matches) =====
    _match("a", 12, 18, "Canada vs Bosnia & Herzegovina (Opening)", Magnitude.severe, 30000),
    _match("b", 17, 19, "Ghana vs Panama (Group L)", Magnitude.high, 28000),
    _match("c", 20, 16, "Germany vs Ivory Coast (Group E)", Magnitude.severe, 30000),
    _match("d", 23, 19, "Panama vs Croatia (Group L)", Magnitude.high, 28000),
    _match("e", 26, 16, "Group stage match", Magnitude.high, 28000),
    _match("f", 32, 16, "Round of 32 match", Magnitude.severe, 30000),  # day 32 -> July 2

    # ===== FIFA Fan Festival (downtown, tournament-long) =====
    Event(
        id="wc-fan-festival-2026",
        title="FIFA Fan Festival",
        category=EventCategory.festival,
        kind=EventKind.demand_surge,
        venue=EXHIBITION_PLACE,
        start=_dt(2026, 6, 12, 12),
        end=_dt(2026, 7, 19, 23),
        impact=TransitImpact(magnitude=Magnitude.high, expected_attendance=40000, radius_km=2.0),
        description="Tournament-long fan festival drawing sustained daily crowds.",
        source="mock",
    ),

    # ===== Toronto Blue Jays — Rogers Centre (selected home games) =====
    Event(
        id="bj-2026-06-05-orioles",
        title="Blue Jays vs Orioles",
        category=EventCategory.sports,
        kind=EventKind.demand_surge,
        venue=ROGERS_CENTRE,
        start=_dt(2026, 6, 5, 19),
        end=_dt(2026, 6, 5, 22),
        impact=TransitImpact(magnitude=Magnitude.medium, expected_attendance=32000, radius_km=1.5),
        description="Evening home game; Union Station surge on Line 1 + GO.",
        source="mock",
    ),
    Event(
        id="bj-2026-06-12-yankees",
        title="Blue Jays vs Yankees",
        category=EventCategory.sports,
        kind=EventKind.demand_surge,
        venue=ROGERS_CENTRE,
        start=_dt(2026, 6, 12, 19),
        end=_dt(2026, 6, 12, 22),
        impact=TransitImpact(magnitude=Magnitude.high, expected_attendance=42000, radius_km=1.5),
        description="High-draw Yankees series opener — near sell-out at Union Station.",
        source="mock",
    ),
    Event(
        id="bj-2026-07-01-mets",
        title="Blue Jays vs Mets (Canada Day)",
        category=EventCategory.sports,
        kind=EventKind.demand_surge,
        venue=ROGERS_CENTRE,
        start=_dt(2026, 7, 1, 15),
        end=_dt(2026, 7, 1, 18),
        impact=TransitImpact(magnitude=Magnitude.high, expected_attendance=42000, radius_km=1.5),
        description="Canada Day game; overlaps with waterfront holiday crowds.",
        source="mock",
    ),

    # ===== Festivals =====
    Event(
        id="pride-parade-2026",
        title="Pride Toronto — Parade",
        category=EventCategory.festival,
        kind=EventKind.demand_surge,
        venue=CHURCH_WELLESLEY,
        start=_dt(2026, 6, 28, 10),
        end=_dt(2026, 6, 28, 20),
        impact=TransitImpact(
            magnitude=Magnitude.severe, expected_attendance=500000, radius_km=2.0
        ),
        description="Pride Parade; large crowds + downtown road closures (Yonge/Bloor) "
        "forcing streetcar and bus diversions.",
        source="mock",
    ),
    Event(
        id="caribana-grand-parade-2026",
        title="Toronto Caribbean Carnival — Grand Parade",
        category=EventCategory.festival,
        kind=EventKind.demand_surge,
        venue=EXHIBITION_PLACE,
        start=_dt(2026, 8, 1, 9),
        end=_dt(2026, 8, 1, 21),
        impact=TransitImpact(
            magnitude=Magnitude.severe, expected_attendance=1000000, radius_km=3.0
        ),
        description="Grand Parade along Lakeshore Blvd; ~1M attendees, Exhibition GO/509 "
        "overwhelmed, Lakeshore closed.",
        source="mock",
    ),
    Event(
        id="cne-2026",
        title="Canadian National Exhibition (CNE)",
        category=EventCategory.festival,
        kind=EventKind.demand_surge,
        venue=EXHIBITION_PLACE,
        start=_dt(2026, 8, 14, 10),
        end=_dt(2026, 9, 7, 23),
        impact=TransitImpact(magnitude=Magnitude.high, expected_attendance=100000, radius_km=2.0),
        description="18-day fair; sustained daily demand at Exhibition Place.",
        source="mock",
    ),
    Event(
        id="tiff-market-2026",
        title="TIFF: The Market",
        category=EventCategory.festival,
        kind=EventKind.demand_surge,
        venue=MTCC,
        start=_dt(2026, 9, 10, 9),
        end=_dt(2026, 9, 16, 22),
        impact=TransitImpact(magnitude=Magnitude.medium, expected_attendance=50000, radius_km=1.5),
        description="Film festival market week; King St / entertainment-district crowds.",
        source="mock",
    ),

    # ===== Supply disruptions (closures / construction) =====
    Event(
        id="ttc-line2-jane-ossington-2026-05-30",
        title="TTC Line 2 closure: Jane ↔ Ossington",
        category=EventCategory.closure,
        kind=EventKind.supply_disruption,
        venue=LINE2_WEST,
        start=_dt(2026, 5, 30, 0),
        end=_dt(2026, 5, 31, 23, 59),
        impact=TransitImpact(
            magnitude=Magnitude.high,
            affected_lines=["Line 2 Bloor-Danforth"],
            affected_stations=["Jane", "Runnymede", "High Park", "Keele", "Dundas West",
                               "Lansdowne", "Dufferin", "Ossington"],
            shuttle_replacement=True,
        ),
        description="~5 km weekend closure for track work ahead of the World Cup. "
        "Runnymede, High Park, Lansdowne, Dufferin fully closed; shuttle buses run.",
        source="mock",
    ),
    Event(
        id="ttc-line1-stclair-eglinton-2026-06-13",
        title="TTC Line 1 closure: St Clair ↔ Eglinton",
        category=EventCategory.closure,
        kind=EventKind.supply_disruption,
        venue=LINE1_MIDTOWN,
        start=_dt(2026, 6, 13, 0),
        end=_dt(2026, 6, 14, 23, 59),
        impact=TransitImpact(
            magnitude=Magnitude.high,
            affected_lines=["Line 1 Yonge-University"],
            affected_stations=["St Clair", "Davisville", "Eglinton"],
            shuttle_replacement=True,
        ),
        description="Weekend Yonge-line closure; midtown riders shuttle-bused. "
        "(Mock — plausible upcoming closure.)",
        source="mock",
    ),
    Event(
        id="eglinton-crosstown-construction-2026",
        title="Eglinton Crosstown construction impacts",
        category=EventCategory.construction,
        kind=EventKind.supply_disruption,
        venue=EGLINTON_CORRIDOR,
        start=_dt(2026, 5, 1, 0),
        end=_dt(2026, 12, 31, 23, 59),
        impact=TransitImpact(
            magnitude=Magnitude.medium,
            affected_lines=["32 Eglinton West", "34 Eglinton East"],
            shuttle_replacement=False,
        ),
        description="Ongoing lane reductions and bus slowdowns along the Eglinton corridor.",
        source="mock",
    ),
]


class MockEventsProvider:
    """In-memory provider of curated upcoming events.

    Replace with a live provider (venue APIs + Festivals & Events dataset + TTC
    alerts + news) that returns the same ``list[Event]`` from ``fetch()``.
    """

    def fetch(self) -> list[Event]:
        return list(_EVENTS)


@lru_cache(maxsize=1)
def get_provider() -> MockEventsProvider:
    return MockEventsProvider()
