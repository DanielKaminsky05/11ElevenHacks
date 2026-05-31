"""TransitRL tools — Family E: Explanation & Attribution.

Tools that narrate and justify: who_is_affected, explain_result, generate_brief.
Register each with `@tool` from app.tools.registry.

NOTE: explain_result / narration may call the Nemotron NIM (app.agent.nim_client).
In tests, mock that call — never require a live model. who_is_affected is pure
compute and should be fully tested.

Owned by one tool-builder agent. See .claude/agents/tool-builder.md.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

import geopandas as gpd
import openpyxl
import pandas as pd
from pydantic import BaseModel, Field

from app.agent.nim_client import get_nim_client
from app.config import get_settings
from app.data import data_dir
from app.tools.registry import tool

# ---------------------------------------------------------------------------
# Data helpers (private to this module to avoid parallel-agent conflicts)
# ---------------------------------------------------------------------------

_INCOME_BANDS = [
    ("low", 0, 30_000),
    ("moderate", 30_000, 60_000),
    ("middle", 60_000, 100_000),
    ("high", 100_000, float("inf")),
]

# Row indices into the neighbourhood-profiles-2021.xlsx (0-based)
_ROW_NBHD_NAME = 0
_ROW_NBHD_NUM = 1
_ROW_TOTAL_POP = 3        # "Total - Age groups of the population - 25% sample data"
_ROW_POP_0_14 = 4         # "  0 to 14 years"
_ROW_POP_15_64 = 8        # "  15 to 64 years"
_ROW_POP_65_PLUS = 19     # "  65 years and over"
_ROW_MEDIAN_INCOME = 63   # "    Median total income in 2020 among recipients ($)"


@lru_cache(maxsize=1)
def _load_neighbourhood_profiles() -> pd.DataFrame:
    """Load the neighbourhood-profiles-2021.xlsx into a tidy DataFrame.

    Returns a DataFrame indexed by neighbourhood number (int) with columns:
      name, total_pop, pop_0_14, pop_15_64, pop_65_plus, median_income_2020
    """
    path = data_dir() / "census-demographics" / "neighbourhood-profiles-2021.xlsx"
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb.active
    rows = [tuple(r) for r in ws.iter_rows(values_only=True)]

    nbhd_nums = [int(v) for v in rows[_ROW_NBHD_NUM][1:] if v is not None]
    nbhd_names = [str(v) for v in rows[_ROW_NBHD_NAME][1 : len(nbhd_nums) + 1]]

    def _to_float(val: Any) -> float:
        try:
            return float(val) if val is not None else float("nan")
        except (TypeError, ValueError):
            return float("nan")

    total_pop = [_to_float(rows[_ROW_TOTAL_POP][1 + i]) for i in range(len(nbhd_nums))]
    pop_0_14 = [_to_float(rows[_ROW_POP_0_14][1 + i]) for i in range(len(nbhd_nums))]
    pop_15_64 = [_to_float(rows[_ROW_POP_15_64][1 + i]) for i in range(len(nbhd_nums))]
    pop_65_plus = [_to_float(rows[_ROW_POP_65_PLUS][1 + i]) for i in range(len(nbhd_nums))]
    median_income = [
        _to_float(rows[_ROW_MEDIAN_INCOME][1 + i]) for i in range(len(nbhd_nums))
    ]

    df = pd.DataFrame(
        {
            "nbhd_num": nbhd_nums,
            "name": nbhd_names,
            "total_pop": total_pop,
            "pop_0_14": pop_0_14,
            "pop_15_64": pop_15_64,
            "pop_65_plus": pop_65_plus,
            "median_income_2020": median_income,
        }
    ).set_index("nbhd_num")
    return df


@lru_cache(maxsize=1)
def _load_neighbourhoods_geo() -> gpd.GeoDataFrame:
    """Load the 158-neighbourhood GeoJSON."""
    path = data_dir() / "geospatial" / "neighbourhoods-158.geojson"
    gdf = gpd.read_file(str(path))
    gdf["nbhd_num"] = gdf["AREA_SHORT_CODE"].astype(int)
    return gdf.set_index("nbhd_num")


# ---------------------------------------------------------------------------
# Shared scenario types
# ---------------------------------------------------------------------------


class AreaAccessDelta(BaseModel):
    """Before/after accessibility change for one neighbourhood."""

    nbhd_num: int = Field(..., description="Neighbourhood number (1–174)")
    before_access_pct: float = Field(
        ..., ge=0.0, le=100.0, description="% of area pop within walk buffer before"
    )
    after_access_pct: float = Field(
        ..., ge=0.0, le=100.0, description="% of area pop within walk buffer after"
    )

    @property
    def delta(self) -> float:
        return self.after_access_pct - self.before_access_pct


class Scenario(BaseModel):
    """A before/after simulation result expressed as per-neighbourhood access deltas."""

    scenario_id: str = Field(..., min_length=1, description="Unique identifier for this scenario")
    description: str = Field("", description="Human-readable description")
    area_deltas: list[AreaAccessDelta] = Field(
        ..., min_length=1, description="Per-neighbourhood before/after access"
    )


# ---------------------------------------------------------------------------
# Family E — Tool 1: who_is_affected
# ---------------------------------------------------------------------------


class WhoIsAffectedArgs(BaseModel):
    """Arguments for who_is_affected."""

    scenario: Scenario = Field(..., description="Before/after scenario with per-area access deltas")
    group_by: Literal["income", "age", "neighbourhood"] = Field(
        ..., description="Dimension to group by: 'income', 'age', or 'neighbourhood'"
    )


def _income_band(median: float) -> str:
    """Classify a median income into a band label."""
    for label, lo, hi in _INCOME_BANDS:
        if lo <= median < hi:
            return label
    return "high"


def _who_is_affected_by_income(
    profiles: pd.DataFrame, deltas_df: pd.DataFrame
) -> list[dict]:
    """Group winners/losers by income band."""
    merged = profiles.join(deltas_df, how="inner")
    merged["income_band"] = merged["median_income_2020"].apply(_income_band)

    results = []
    for band in ["low", "moderate", "middle", "high"]:
        subset = merged[merged["income_band"] == band]
        if subset.empty:
            results.append(
                {
                    "group": band,
                    "nbhd_count": 0,
                    "population": 0,
                    "mean_delta_pct": 0.0,
                    "winners": 0,
                    "losers": 0,
                    "unchanged": 0,
                }
            )
            continue
        total_pop = float(subset["total_pop"].sum())
        mean_delta = float(subset["delta"].mean())
        winners = int((subset["delta"] > 0).sum())
        losers = int((subset["delta"] < 0).sum())
        unchanged = int((subset["delta"] == 0).sum())
        results.append(
            {
                "group": band,
                "nbhd_count": int(len(subset)),
                "population": int(total_pop),
                "mean_delta_pct": round(mean_delta, 3),
                "winners": winners,
                "losers": losers,
                "unchanged": unchanged,
            }
        )
    return results


def _who_is_affected_by_age(
    profiles: pd.DataFrame, deltas_df: pd.DataFrame
) -> list[dict]:
    """Group winners/losers by broad age cohort (youth, working-age, seniors)."""
    merged = profiles.join(deltas_df, how="inner")

    age_groups = [
        ("youth_0_14", "pop_0_14"),
        ("working_age_15_64", "pop_15_64"),
        ("seniors_65_plus", "pop_65_plus"),
    ]
    results = []
    for label, pop_col in age_groups:
        total_pop = float(merged[pop_col].sum())
        # Weight delta by relative group share within each neighbourhood
        total_weight = merged[pop_col].sum()
        if total_weight > 0:
            weighted_delta = float(
                (merged["delta"] * merged[pop_col]).sum() / total_weight
            )
        else:
            weighted_delta = 0.0
        winners = int((merged[merged["delta"] > 0][pop_col]).sum())
        losers = int((merged[merged["delta"] < 0][pop_col]).sum())
        unchanged = int((merged[merged["delta"] == 0][pop_col]).sum())
        results.append(
            {
                "group": label,
                "population": int(total_pop),
                "weighted_mean_delta_pct": round(weighted_delta, 3),
                "pop_in_winning_nbhds": winners,
                "pop_in_losing_nbhds": losers,
                "pop_in_unchanged_nbhds": unchanged,
            }
        )
    return results


def _who_is_affected_by_neighbourhood(
    profiles: pd.DataFrame, deltas_df: pd.DataFrame
) -> list[dict]:
    """Return per-neighbourhood breakdown sorted by delta (largest gain first)."""
    merged = profiles.join(deltas_df, how="inner")
    merged = merged.sort_values("delta", ascending=False)
    results = []
    for nbhd_num, row in merged.iterrows():
        results.append(
            {
                "nbhd_num": int(nbhd_num),
                "name": str(row["name"]),
                "population": int(row["total_pop"]),
                "before_access_pct": float(row["before_access_pct"]),
                "after_access_pct": float(row["after_access_pct"]),
                "delta_pct": round(float(row["delta"]), 3),
            }
        )
    return results


@tool(WhoIsAffectedArgs)
def who_is_affected(args: WhoIsAffectedArgs) -> dict:
    """Distributional impact of a scenario: who gains / loses access, broken down by income, age, or neighbourhood."""
    profiles = _load_neighbourhood_profiles()

    # Build a flat DataFrame from the scenario deltas
    delta_rows = [
        {
            "nbhd_num": d.nbhd_num,
            "before_access_pct": d.before_access_pct,
            "after_access_pct": d.after_access_pct,
            "delta": d.delta,
        }
        for d in args.scenario.area_deltas
    ]
    deltas_df = pd.DataFrame(delta_rows).set_index("nbhd_num")

    # Only keep rows present in both the profiles and the scenario
    common_ids = profiles.index.intersection(deltas_df.index)
    profiles_sub = profiles.loc[common_ids]
    deltas_sub = deltas_df.loc[common_ids]

    if args.group_by == "income":
        groups = _who_is_affected_by_income(profiles_sub, deltas_sub)
    elif args.group_by == "age":
        groups = _who_is_affected_by_age(profiles_sub, deltas_sub)
    else:  # neighbourhood
        groups = _who_is_affected_by_neighbourhood(profiles_sub, deltas_sub)

    # Summary statistics
    total_pop = int(profiles_sub["total_pop"].sum())
    n_winners = int((deltas_sub["delta"] > 0).sum())
    n_losers = int((deltas_sub["delta"] < 0).sum())
    n_unchanged = int((deltas_sub["delta"] == 0).sum())

    return {
        "scenario_id": args.scenario.scenario_id,
        "group_by": args.group_by,
        "nbhd_count": int(len(common_ids)),
        "total_population": total_pop,
        "summary": {
            "neighbourhoods_gaining_access": n_winners,
            "neighbourhoods_losing_access": n_losers,
            "neighbourhoods_unchanged": n_unchanged,
        },
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# Family E — Tool 2: explain_result
# ---------------------------------------------------------------------------


class ExplainResultArgs(BaseModel):
    """Arguments for explain_result."""

    scenario: Scenario = Field(..., description="Before/after scenario to narrate")
    nim_base_url: str = Field(
        default="",
        description="NIM endpoint; falls back to config if empty",
    )
    nim_model: str = Field(
        default="",
        description="NIM model name; falls back to config if empty",
    )


def _build_explain_prompt(scenario: Scenario, who_affected: dict) -> str:
    """Build the narration prompt from scenario metrics."""
    summary = who_affected.get("summary", {})
    n_winning = summary.get("neighbourhoods_gaining_access", 0)
    n_losing = summary.get("neighbourhoods_losing_access", 0)
    total_pop = who_affected.get("total_population", 0)
    nbhd_count = who_affected.get("nbhd_count", 0)

    deltas = [d.delta for d in scenario.area_deltas]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    max_gain = max(deltas) if deltas else 0.0
    max_loss = min(deltas) if deltas else 0.0

    prompt = (
        # /no_think keeps the narration clean (no leaked reasoning preamble).
        "/no_think\n"
        f"You are a transportation planning analyst. Explain the following transit "
        f"scenario in plain language for a city councillor.\n\n"
        f"Scenario: {scenario.description or scenario.scenario_id}\n\n"
        f"Key metrics:\n"
        f"- Neighbourhoods analysed: {nbhd_count} covering {total_pop:,} residents\n"
        f"- Mean access change: {mean_delta:+.1f} percentage points\n"
        f"- Neighbourhoods gaining access: {n_winning}\n"
        f"- Neighbourhoods losing access: {n_losing}\n"
        f"- Largest single gain: {max_gain:+.1f} pp\n"
        f"- Largest single loss: {max_loss:+.1f} pp\n\n"
        f"Write 3–5 sentences that: (1) summarise what changed, (2) name the main "
        f"winners and losers, (3) flag the key trade-off the planner implicitly chose."
    )
    return prompt


@tool(ExplainResultArgs)
async def explain_result(args: ExplainResultArgs) -> dict:
    """Narrate a before/after transit scenario in plain language using Nemotron NIM."""
    settings = get_settings()
    model = args.nim_model or settings.nim_model

    # Compute distributional impact first (reuse who_is_affected logic)
    who_args = WhoIsAffectedArgs(scenario=args.scenario, group_by="income")
    who_result = who_is_affected(who_args)

    prompt = _build_explain_prompt(args.scenario, who_result)
    messages = [{"role": "user", "content": prompt}]

    client = get_nim_client()
    response = await client.chat(messages=messages)

    narration = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )

    return {
        "scenario_id": args.scenario.scenario_id,
        "narration": narration,
        "prompt_used": prompt,
        "distributional_summary": who_result["summary"],
        "model": model,
    }


# ---------------------------------------------------------------------------
# Family E — Tool 3: generate_brief
# ---------------------------------------------------------------------------

_HONESTY_CAVEAT = (
    "> **Model caveat:** This analysis uses a walk-access accessibility model, "
    "not a demand forecast. Coverage percentages reflect who is physically within "
    "the walk buffer of a transit stop — they do not predict ridership changes or "
    "account for multi-leg transfer trips. Treat these figures as a diagnostic "
    "signal, not a forecast."
)


class GenerateBriefArgs(BaseModel):
    """Arguments for generate_brief."""

    scenario: Scenario = Field(..., description="Scenario to document")
    question: str = Field(
        ...,
        min_length=5,
        description="The planning question this scenario addresses",
    )
    recommendation: str = Field(
        ...,
        min_length=5,
        description="The recommended action or conclusion",
    )
    nim_base_url: str = Field(
        default="",
        description="NIM endpoint; falls back to config if empty",
    )
    nim_model: str = Field(
        default="",
        description="NIM model name; falls back to config if empty",
    )


def _build_brief_prompt(
    scenario: Scenario,
    question: str,
    recommendation: str,
    who_result: dict,
) -> str:
    """Build the prompt for the brief's equity narrative section."""
    groups = who_result.get("groups", [])
    group_lines = "\n".join(
        f"  - {g['group']}: mean delta {g.get('mean_delta_pct', g.get('weighted_mean_delta_pct', 0)):+.1f} pp, "
        f"pop {g.get('population', 0):,}"
        for g in groups
    )
    prompt = (
        # /no_think keeps the memo paragraph clean (no leaked reasoning preamble).
        "/no_think\n"
        f"Write a concise equity-impact paragraph (3–4 sentences) for a planner memo.\n\n"
        f"Planning question: {question}\n"
        f"Recommendation: {recommendation}\n"
        f"Scenario: {scenario.description or scenario.scenario_id}\n\n"
        f"Income-group breakdown:\n{group_lines}\n\n"
        f"Focus on which income groups gain or lose access and why this matters for equity."
    )
    return prompt


@tool(GenerateBriefArgs)
async def generate_brief(args: GenerateBriefArgs) -> dict:
    """Export a planner-ready markdown memo: question, recommendation, metrics, equity impact, and caveats."""
    settings = get_settings()
    model = args.nim_model or settings.nim_model

    # Compute distributional impact for income dimension
    who_args = WhoIsAffectedArgs(scenario=args.scenario, group_by="income")
    who_result = who_is_affected(who_args)

    # Build equity narrative via NIM
    prompt = _build_brief_prompt(
        args.scenario, args.question, args.recommendation, who_result
    )
    messages = [{"role": "user", "content": prompt}]

    client = get_nim_client()
    response = await client.chat(messages=messages)
    equity_narrative = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )

    # Assemble metrics table
    summary = who_result["summary"]
    deltas = [d.delta for d in args.scenario.area_deltas]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    max_gain = max(deltas) if deltas else 0.0
    max_loss = min(deltas) if deltas else 0.0

    groups = who_result.get("groups", [])
    income_table_rows = "\n".join(
        f"| {g['group'].title()} | {g.get('population', 0):,} | "
        f"{g.get('mean_delta_pct', 0):+.1f} | "
        f"{g.get('winners', 0)} | {g.get('losers', 0)} |"
        for g in groups
    )

    markdown = f"""# Planning Brief: {args.scenario.scenario_id}

## Question
{args.question}

## Recommendation
{args.recommendation}

## Scenario Description
{args.scenario.description or args.scenario.scenario_id}

## Key Metrics

| Metric | Value |
|---|---|
| Neighbourhoods analysed | {who_result['nbhd_count']} |
| Total population | {who_result['total_population']:,} |
| Mean access change | {mean_delta:+.1f} pp |
| Neighbourhoods gaining access | {summary['neighbourhoods_gaining_access']} |
| Neighbourhoods losing access | {summary['neighbourhoods_losing_access']} |
| Largest single gain | {max_gain:+.1f} pp |
| Largest single loss | {max_loss:+.1f} pp |

## Equity Impact by Income Group

| Income Group | Population | Mean Δ Access (pp) | Gaining Nbhds | Losing Nbhds |
|---|---|---|---|---|
{income_table_rows}

### Equity Narrative
{equity_narrative}

## Caveats

{_HONESTY_CAVEAT}
"""

    return {
        "scenario_id": args.scenario.scenario_id,
        "markdown": markdown,
        "equity_narrative": equity_narrative,
        "prompt_used": prompt,
        "metrics": {
            "nbhd_count": who_result["nbhd_count"],
            "total_population": who_result["total_population"],
            "mean_delta_pct": round(mean_delta, 3),
            "max_gain_pct": round(max_gain, 3),
            "max_loss_pct": round(max_loss, 3),
            "summary": summary,
        },
        "model": model,
    }
