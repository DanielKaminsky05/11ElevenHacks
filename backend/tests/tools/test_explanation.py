"""Tests for Family E — Explanation & Attribution tools.

Covers: who_is_affected (pure compute), explain_result (mocked NIM),
generate_brief (mocked NIM + caveat invariant).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# Import the tools package so all @tool registrations fire
import app.tools  # noqa: F401
from app.tools.registry import get_tool
from app.agent.nim_client import FakeNIMClient
from app.tools.explanation import (
    AreaAccessDelta,
    GenerateBriefArgs,
    ExplainResultArgs,
    Scenario,
    WhoIsAffectedArgs,
    _HONESTY_CAVEAT,
    _build_explain_prompt,
    _build_brief_prompt,
    generate_brief,
    explain_result,
    who_is_affected,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_scenario(
    deltas: list[tuple[int, float, float]],
    scenario_id: str = "test-scenario",
    description: str = "Test scenario",
) -> Scenario:
    """Build a Scenario from (nbhd_num, before, after) triples."""
    return Scenario(
        scenario_id=scenario_id,
        description=description,
        area_deltas=[
            AreaAccessDelta(nbhd_num=n, before_access_pct=b, after_access_pct=a)
            for n, b, a in deltas
        ],
    )


def _nim_response(content: str) -> dict:
    """Minimal fake NIM chat-completion response."""
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}}
        ]
    }


@pytest.fixture
def simple_scenario() -> Scenario:
    """A small scenario covering 5 real Toronto neighbourhoods (nbhds 1–5)."""
    return _make_scenario([
        (1, 40.0, 55.0),   # +15 pp — West Humber-Clairville
        (2, 30.0, 25.0),   # −5 pp  — Mount Olive-Silverstone-Jamestown
        (3, 50.0, 50.0),   # 0      — Thistletown-Beaumond Heights
        (4, 20.0, 35.0),   # +15 pp — Rexdale-Kipling
        (5, 45.0, 40.0),   # −5 pp  — Elms-Old Rexdale
    ])


@pytest.fixture
def all_gain_scenario() -> Scenario:
    """All neighbourhoods gain access — used for monotonicity / boundary checks."""
    return _make_scenario([
        (1, 30.0, 60.0),
        (2, 20.0, 50.0),
        (6, 40.0, 80.0),
    ])


@pytest.fixture
def all_lose_scenario() -> Scenario:
    """All neighbourhoods lose access."""
    return _make_scenario([
        (1, 60.0, 30.0),
        (2, 50.0, 20.0),
        (6, 80.0, 40.0),
    ])


@pytest.fixture
def single_nbhd_scenario() -> Scenario:
    """Minimal scenario with exactly one neighbourhood."""
    return _make_scenario([(10, 55.0, 70.0)])


# ---------------------------------------------------------------------------
# Section 1 — AreaAccessDelta & Scenario validation
# ---------------------------------------------------------------------------

class TestAreaAccessDeltaValidation:
    def test_valid_delta_computes_correctly(self):
        d = AreaAccessDelta(nbhd_num=1, before_access_pct=40.0, after_access_pct=55.0)
        assert d.delta == pytest.approx(15.0)

    def test_negative_delta_computes_correctly(self):
        d = AreaAccessDelta(nbhd_num=2, before_access_pct=50.0, after_access_pct=45.0)
        assert d.delta == pytest.approx(-5.0)

    def test_before_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            AreaAccessDelta(nbhd_num=1, before_access_pct=-1.0, after_access_pct=50.0)

    def test_after_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            AreaAccessDelta(nbhd_num=1, before_access_pct=50.0, after_access_pct=101.0)

    def test_zero_delta_is_valid(self):
        d = AreaAccessDelta(nbhd_num=1, before_access_pct=50.0, after_access_pct=50.0)
        assert d.delta == 0.0


class TestScenarioValidation:
    def test_empty_area_deltas_raises(self):
        with pytest.raises(ValidationError):
            Scenario(scenario_id="x", area_deltas=[])

    def test_empty_scenario_id_raises(self):
        with pytest.raises(ValidationError):
            Scenario(
                scenario_id="",
                area_deltas=[
                    AreaAccessDelta(nbhd_num=1, before_access_pct=40.0, after_access_pct=50.0)
                ],
            )


# ---------------------------------------------------------------------------
# Section 2 — WhoIsAffectedArgs validation
# ---------------------------------------------------------------------------

class TestWhoIsAffectedArgsValidation:
    def test_invalid_group_by_raises(self, simple_scenario):
        with pytest.raises(ValidationError):
            WhoIsAffectedArgs(scenario=simple_scenario, group_by="race")  # type: ignore[arg-type]

    def test_missing_group_by_raises(self, simple_scenario):
        with pytest.raises(ValidationError):
            WhoIsAffectedArgs(scenario=simple_scenario)  # type: ignore[call-arg]

    def test_valid_group_by_income(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        assert args.group_by == "income"

    def test_valid_group_by_age(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="age")
        assert args.group_by == "age"

    def test_valid_group_by_neighbourhood(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="neighbourhood")
        assert args.group_by == "neighbourhood"


# ---------------------------------------------------------------------------
# Section 3 — who_is_affected: happy path
# ---------------------------------------------------------------------------

class TestWhoIsAffectedHappyPath:
    def test_income_grouping_returns_four_bands(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        groups = result["groups"]
        band_names = {g["group"] for g in groups}
        assert band_names == {"low", "moderate", "middle", "high"}

    def test_age_grouping_returns_three_cohorts(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="age")
        result = who_is_affected(args)
        groups = result["groups"]
        labels = {g["group"] for g in groups}
        assert labels == {"youth_0_14", "working_age_15_64", "seniors_65_plus"}

    def test_neighbourhood_grouping_returns_per_area_rows(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="neighbourhood")
        result = who_is_affected(args)
        assert len(result["groups"]) == len(simple_scenario.area_deltas)

    def test_result_contains_required_keys(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        for key in ("scenario_id", "group_by", "nbhd_count", "total_population", "summary", "groups"):
            assert key in result, f"Missing key: {key}"

    def test_summary_keys_present(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        summary = result["summary"]
        for key in ("neighbourhoods_gaining_access", "neighbourhoods_losing_access", "neighbourhoods_unchanged"):
            assert key in summary

    def test_scenario_id_echoed(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        assert result["scenario_id"] == simple_scenario.scenario_id


# ---------------------------------------------------------------------------
# Section 4 — who_is_affected: invariants
# ---------------------------------------------------------------------------

class TestWhoIsAffectedInvariants:
    def test_winners_losers_unchanged_sum_to_nbhd_count(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        summary = result["summary"]
        total = (
            summary["neighbourhoods_gaining_access"]
            + summary["neighbourhoods_losing_access"]
            + summary["neighbourhoods_unchanged"]
        )
        assert total == result["nbhd_count"]

    def test_nbhd_count_matches_scenario_overlap(self, simple_scenario):
        """nbhd_count ≤ len(area_deltas) — only matched rows are counted."""
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        assert result["nbhd_count"] <= len(simple_scenario.area_deltas)

    def test_total_population_is_positive(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        assert result["total_population"] > 0

    def test_income_group_populations_sum_to_total(self, simple_scenario):
        """All income groups cover the same matched neighbourhoods — populations should sum to total."""
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        group_pop_sum = sum(g["population"] for g in result["groups"])
        assert group_pop_sum == result["total_population"]

    def test_all_gain_scenario_no_losers(self, all_gain_scenario):
        args = WhoIsAffectedArgs(scenario=all_gain_scenario, group_by="income")
        result = who_is_affected(args)
        assert result["summary"]["neighbourhoods_losing_access"] == 0
        assert result["summary"]["neighbourhoods_gaining_access"] > 0

    def test_all_lose_scenario_no_winners(self, all_lose_scenario):
        args = WhoIsAffectedArgs(scenario=all_lose_scenario, group_by="income")
        result = who_is_affected(args)
        assert result["summary"]["neighbourhoods_gaining_access"] == 0
        assert result["summary"]["neighbourhoods_losing_access"] > 0

    def test_determinism(self, simple_scenario):
        """Same input → same output."""
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        r1 = who_is_affected(args)
        r2 = who_is_affected(args)
        assert r1 == r2

    def test_neighbourhood_grouping_sorted_largest_gain_first(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="neighbourhood")
        result = who_is_affected(args)
        deltas = [g["delta_pct"] for g in result["groups"]]
        assert deltas == sorted(deltas, reverse=True)

    def test_neighbourhood_grouping_delta_values_are_correct(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="neighbourhood")
        result = who_is_affected(args)
        # nbhd 1: before=40, after=55 → delta=15; nbhd 2: before=30, after=25 → delta=-5
        by_num = {g["nbhd_num"]: g["delta_pct"] for g in result["groups"]}
        assert by_num[1] == pytest.approx(15.0)
        assert by_num[2] == pytest.approx(-5.0)
        assert by_num[3] == pytest.approx(0.0)

    def test_age_group_populations_are_non_negative(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="age")
        result = who_is_affected(args)
        for g in result["groups"]:
            assert g["population"] >= 0

    def test_income_group_winner_loser_counts_non_negative(self, simple_scenario):
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        for g in result["groups"]:
            assert g["winners"] >= 0
            assert g["losers"] >= 0
            assert g["unchanged"] >= 0


# ---------------------------------------------------------------------------
# Section 5 — who_is_affected: edge cases
# ---------------------------------------------------------------------------

class TestWhoIsAffectedEdgeCases:
    def test_single_neighbourhood(self, single_nbhd_scenario):
        args = WhoIsAffectedArgs(scenario=single_nbhd_scenario, group_by="neighbourhood")
        result = who_is_affected(args)
        assert result["nbhd_count"] == 1
        assert len(result["groups"]) == 1

    def test_unknown_nbhd_ignored_gracefully(self):
        """A neighbourhood number not in the profiles is silently excluded."""
        scenario = _make_scenario([(9999, 40.0, 60.0)])
        args = WhoIsAffectedArgs(scenario=scenario, group_by="income")
        result = who_is_affected(args)
        # Should return 0 matches (not crash)
        assert result["nbhd_count"] == 0
        assert result["total_population"] == 0

    def test_all_zero_delta(self):
        """When nothing changes, winners=0, losers=0, unchanged=all."""
        scenario = _make_scenario([(1, 50.0, 50.0), (2, 60.0, 60.0)])
        args = WhoIsAffectedArgs(scenario=scenario, group_by="income")
        result = who_is_affected(args)
        s = result["summary"]
        assert s["neighbourhoods_gaining_access"] == 0
        assert s["neighbourhoods_losing_access"] == 0
        assert s["neighbourhoods_unchanged"] == result["nbhd_count"]

    def test_income_groups_sum_per_band_winners_losers_to_nbhd_count_in_band(self, simple_scenario):
        """For each income band, winners + losers + unchanged == nbhd_count in band."""
        args = WhoIsAffectedArgs(scenario=simple_scenario, group_by="income")
        result = who_is_affected(args)
        for g in result["groups"]:
            total_in_band = g["winners"] + g["losers"] + g["unchanged"]
            assert total_in_band == g["nbhd_count"], (
                f"Band '{g['group']}': winners+losers+unchanged={total_in_band} "
                f"!= nbhd_count={g['nbhd_count']}"
            )


# ---------------------------------------------------------------------------
# Section 6 — Schema validity & registry
# ---------------------------------------------------------------------------

class TestSchemaAndRegistry:
    def test_who_is_affected_registered(self):
        spec = get_tool("who_is_affected")
        assert spec.name == "who_is_affected"

    def test_explain_result_registered(self):
        spec = get_tool("explain_result")
        assert spec.name == "explain_result"

    def test_generate_brief_registered(self):
        spec = get_tool("generate_brief")
        assert spec.name == "generate_brief"

    def test_who_is_affected_schema_produced(self):
        spec = get_tool("who_is_affected")
        schema = spec.input_model.model_json_schema()
        assert "properties" in schema

    def test_explain_result_schema_produced(self):
        spec = get_tool("explain_result")
        schema = spec.input_model.model_json_schema()
        assert "properties" in schema

    def test_generate_brief_schema_produced(self):
        spec = get_tool("generate_brief")
        schema = spec.input_model.model_json_schema()
        assert "properties" in schema

    def test_tools_have_non_empty_description(self):
        for name in ("who_is_affected", "explain_result", "generate_brief"):
            spec = get_tool(name)
            assert spec.description, f"Tool '{name}' has no description"


# ---------------------------------------------------------------------------
# Section 7 — explain_result: mocked NIM
# ---------------------------------------------------------------------------

_FAKE_NARRATION = (
    "This plan improves access for West Humber-Clairville significantly. "
    "However, Mount Olive-Silverstone-Jamestown sees a modest decline. "
    "The planner traded equity gains in low-income areas for slight losses elsewhere."
)


def _make_fake_client(content: str) -> MagicMock:
    """Return a mock NIM client whose chat() is an async method returning a canned response."""
    fake_client = MagicMock()
    fake_client.chat = AsyncMock(return_value=_nim_response(content))
    return fake_client


class TestExplainResult:
    def _run_explain(self, scenario: Scenario, nim_response_content: str = _FAKE_NARRATION) -> dict:
        """Helper: run explain_result with a mocked NIM client."""
        args = ExplainResultArgs(scenario=scenario)
        fake_client = _make_fake_client(nim_response_content)
        with patch("app.tools.explanation.get_nim_client", return_value=fake_client):
            result = asyncio.run(explain_result(args))
        return result

    def test_narration_comes_from_nim(self, simple_scenario):
        result = self._run_explain(simple_scenario)
        assert result["narration"] == _FAKE_NARRATION

    def test_result_contains_required_keys(self, simple_scenario):
        result = self._run_explain(simple_scenario)
        for key in ("scenario_id", "narration", "prompt_used", "distributional_summary", "model"):
            assert key in result, f"Missing key: {key}"

    def test_scenario_id_echoed(self, simple_scenario):
        result = self._run_explain(simple_scenario)
        assert result["scenario_id"] == simple_scenario.scenario_id

    def test_prompt_mentions_scenario_description(self, simple_scenario):
        result = self._run_explain(simple_scenario)
        assert simple_scenario.description in result["prompt_used"]

    def test_distributional_summary_has_expected_keys(self, simple_scenario):
        result = self._run_explain(simple_scenario)
        s = result["distributional_summary"]
        for key in (
            "neighbourhoods_gaining_access",
            "neighbourhoods_losing_access",
            "neighbourhoods_unchanged",
        ):
            assert key in s

    def test_nim_called_with_messages_list(self, simple_scenario):
        args = ExplainResultArgs(scenario=simple_scenario)
        fake_client = _make_fake_client(_FAKE_NARRATION)
        with patch("app.tools.explanation.get_nim_client", return_value=fake_client):
            asyncio.run(explain_result(args))
        fake_client.chat.assert_called_once()
        call_kwargs = fake_client.chat.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        assert isinstance(messages, list)
        assert len(messages) >= 1
        assert messages[0]["role"] == "user"

    def test_narration_is_string(self, simple_scenario):
        result = self._run_explain(simple_scenario)
        assert isinstance(result["narration"], str)

    def test_empty_nim_response_returns_empty_narration(self, simple_scenario):
        """Tool degrades gracefully when NIM returns empty content."""
        result = self._run_explain(simple_scenario, nim_response_content="")
        assert result["narration"] == ""


# ---------------------------------------------------------------------------
# Section 8 — generate_brief: mocked NIM + caveat invariant
# ---------------------------------------------------------------------------

_FAKE_EQUITY_NARRATIVE = (
    "Low-income neighbourhoods in the west end gain the most from this change. "
    "Middle-income areas see modest improvements. High-income areas are unaffected."
)


class TestGenerateBrief:
    def _run_brief(
        self,
        scenario: Scenario,
        question: str = "Where should we add stops to improve equity?",
        recommendation: str = "Add 3 stops in West Scarborough.",
        nim_response_content: str = _FAKE_EQUITY_NARRATIVE,
    ) -> dict:
        args = GenerateBriefArgs(
            scenario=scenario,
            question=question,
            recommendation=recommendation,
        )
        fake_client = _make_fake_client(nim_response_content)
        with patch("app.tools.explanation.get_nim_client", return_value=fake_client):
            result = asyncio.run(generate_brief(args))
        return result

    def test_markdown_contains_question(self, simple_scenario):
        q = "Where should we add stops to improve equity in the west end?"
        result = self._run_brief(simple_scenario, question=q)
        assert q in result["markdown"]

    def test_markdown_contains_recommendation(self, simple_scenario):
        rec = "Add 5 new stops along Finch West corridor."
        result = self._run_brief(simple_scenario, recommendation=rec)
        assert rec in result["markdown"]

    def test_honesty_caveat_always_present(self, simple_scenario):
        """The caveat must appear regardless of model output — test with three different responses."""
        for content in (_FAKE_EQUITY_NARRATIVE, "", "Some random output"):
            result = self._run_brief(simple_scenario, nim_response_content=content)
            assert "accessibility model, not a demand forecast" in result["markdown"], (
                f"Caveat missing when NIM returns: {content!r}"
            )

    def test_equity_narrative_from_nim_embedded(self, simple_scenario):
        result = self._run_brief(simple_scenario)
        assert _FAKE_EQUITY_NARRATIVE in result["markdown"]

    def test_result_contains_required_keys(self, simple_scenario):
        result = self._run_brief(simple_scenario)
        for key in ("scenario_id", "markdown", "equity_narrative", "prompt_used", "metrics", "model"):
            assert key in result, f"Missing key: {key}"

    def test_metrics_keys_present(self, simple_scenario):
        result = self._run_brief(simple_scenario)
        m = result["metrics"]
        for key in ("nbhd_count", "total_population", "mean_delta_pct", "max_gain_pct", "max_loss_pct", "summary"):
            assert key in m, f"Missing metric key: {key}"

    def test_scenario_id_echoed(self, simple_scenario):
        result = self._run_brief(simple_scenario)
        assert result["scenario_id"] == simple_scenario.scenario_id

    def test_max_gain_is_positive_when_any_gain(self, all_gain_scenario):
        result = self._run_brief(all_gain_scenario)
        assert result["metrics"]["max_gain_pct"] > 0

    def test_max_loss_is_negative_when_any_loss(self, all_lose_scenario):
        result = self._run_brief(all_lose_scenario)
        assert result["metrics"]["max_loss_pct"] < 0

    def test_nim_receives_income_breakdown_in_prompt(self, simple_scenario):
        """Prompt fed to NIM should include income group information."""
        args = GenerateBriefArgs(
            scenario=simple_scenario,
            question="Test question",
            recommendation="Test recommendation",
        )
        fake_client = _make_fake_client(_FAKE_EQUITY_NARRATIVE)
        with patch("app.tools.explanation.get_nim_client", return_value=fake_client):
            result = asyncio.run(generate_brief(args))
        # Prompt must contain income group labels
        for band in ("low", "moderate", "middle", "high"):
            assert band in result["prompt_used"], f"Income band '{band}' missing from prompt"

    def test_question_too_short_raises_validation_error(self, simple_scenario):
        with pytest.raises(ValidationError):
            GenerateBriefArgs(
                scenario=simple_scenario,
                question="Hi",
                recommendation="Do something.",
            )

    def test_recommendation_too_short_raises_validation_error(self, simple_scenario):
        with pytest.raises(ValidationError):
            GenerateBriefArgs(
                scenario=simple_scenario,
                question="What should we do about transit?",
                recommendation="Ok",
            )

    def test_offline_fake_client_returns_caveat(self, simple_scenario):
        """With the real FakeNIMClient (offline path), generate_brief still embeds the honesty caveat."""
        args = GenerateBriefArgs(
            scenario=simple_scenario,
            question="What stops should we add for equity?",
            recommendation="Add stops in underserved areas.",
        )
        fake_nim = FakeNIMClient()
        with patch("app.tools.explanation.get_nim_client", return_value=fake_nim):
            result = asyncio.run(generate_brief(args))
        assert "accessibility model, not a demand forecast" in result["markdown"]


# ---------------------------------------------------------------------------
# Section 9 — _build_explain_prompt content checks
# ---------------------------------------------------------------------------

class TestBuildExplainPrompt:
    def test_prompt_includes_metric_keywords(self, simple_scenario):
        who_result = {
            "summary": {
                "neighbourhoods_gaining_access": 2,
                "neighbourhoods_losing_access": 2,
                "neighbourhoods_unchanged": 1,
            },
            "total_population": 94000,
            "nbhd_count": 5,
        }
        prompt = _build_explain_prompt(simple_scenario, who_result)
        assert "94,000" in prompt or "94000" in prompt  # population
        assert "trade-off" in prompt.lower() or "tradeoff" in prompt.lower() or "trade" in prompt.lower()

    def test_prompt_mentions_scenario_id_or_description(self, simple_scenario):
        who_result = {
            "summary": {"neighbourhoods_gaining_access": 1, "neighbourhoods_losing_access": 1, "neighbourhoods_unchanged": 0},
            "total_population": 50000,
            "nbhd_count": 2,
        }
        prompt = _build_explain_prompt(simple_scenario, who_result)
        assert simple_scenario.description in prompt or simple_scenario.scenario_id in prompt
