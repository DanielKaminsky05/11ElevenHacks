"""Tests for the O-D demand substrate (app.tools._demand).

The keystone test validates the gravity access-to-opportunities model against
StatCan's Spatial Access Measures (SAM) transit employment-access index — the
"grounded in real data" claim. These tests read real local data files.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.tools import _demand


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation (Pearson on ranks); no scipy dependency."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


# ---------------------------------------------------------------------------
# SAM loader
# ---------------------------------------------------------------------------


def test_load_sam_job_access_is_normalised_and_nonempty():
    sam = _demand.load_sam_job_access()
    assert not sam.empty
    assert sam.index.name == "DAUID"
    emp = sam["emp_access"]
    assert emp.notna().all()
    assert emp.min() >= 0.0
    assert emp.max() <= 1.0
    # Toronto has thousands of dissemination areas.
    assert len(sam) > 2_000


def test_sam_access_points_have_toronto_coordinates():
    pts = _demand.sam_access_points()
    assert not pts.empty
    assert {"DAUID", "lon", "lat", "emp_access"} <= set(pts.columns)
    # Inside the Toronto bounding box.
    assert pts["lon"].between(-79.65, -79.10).mean() > 0.99
    assert pts["lat"].between(43.58, 43.86).mean() > 0.99


# ---------------------------------------------------------------------------
# Gravity model
# ---------------------------------------------------------------------------


def test_gravity_job_access_downtown_beats_periphery():
    # Downtown Financial District vs. far north-west suburban edge.
    downtown = _demand.gravity_job_access(-79.3806, 43.6487)[0]
    periphery = _demand.gravity_job_access(-79.62, 43.83)[0]
    assert downtown > periphery


def test_gravity_job_access_vectorised_shape():
    lon = np.array([-79.38, -79.40, -79.50])
    lat = np.array([43.65, 43.70, 43.75])
    out = _demand.gravity_job_access(lon, lat)
    assert out.shape == (3,)
    assert np.all(out >= 0.0)


def test_gravity_job_access_scalar_returns_length_one_array():
    out = _demand.gravity_job_access(-79.38, 43.65)
    assert out.shape == (1,)


# ---------------------------------------------------------------------------
# Keystone: validation against SAM
# ---------------------------------------------------------------------------


def test_gravity_model_correlates_with_sam_employment_access():
    """The gravity job-access model must track StatCan SAM's real transit
    employment-access index across Toronto's dissemination areas.

    Observed Spearman ≈ 0.82; we assert a comfortable floor so the test is a
    stable guard, not a flaky exact-match.
    """
    pts = _demand.sam_access_points()
    model = _demand.gravity_job_access(pts["lon"].to_numpy(), pts["lat"].to_numpy())
    rho = _spearman(model, pts["emp_access"].to_numpy())
    assert rho > 0.6, f"gravity vs SAM Spearman too low: {rho:.3f}"
