"""
Loads /data CSVs and converts rows into the engine's Pydantic schemas.

This module does no calculation -- it only parses CSVs and constructs
engine.schemas objects (FunnelStage, CapacityEntry, CustomerConcentrationEntry).
Display-time source classification stays on the raw DataFrame; only the
numeric fields the engine actually needs are lifted into schema objects.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from engine.schemas import CapacityEntry, CustomerConcentrationEntry, FunnelStage

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_csv(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / name)
    return df.astype(object).where(pd.notnull(df), None)


def load_source_registry() -> pd.DataFrame:
    return _load_csv("source_registry.csv")


def load_calibration_timelines() -> pd.DataFrame:
    return _load_csv("calibration_timelines.csv")


def load_bot_auto_demo_inputs() -> pd.DataFrame:
    return _load_csv("bot_auto_demo_inputs.csv")


def load_symbotic_demo_customers() -> pd.DataFrame:
    return _load_csv("symbotic_demo_customers.csv")


def load_demo_pipeline() -> pd.DataFrame:
    return _load_csv("demo_pipeline.csv")


def load_demo_capacity() -> pd.DataFrame:
    return _load_csv("demo_capacity.csv")


def funnel_stages_from_pipeline_df(df: pd.DataFrame, stage_type: str) -> list[FunnelStage]:
    """stage_type is 'commercial' or 'deployment' (demo_pipeline.csv's stage_type column)."""
    subset = df[df["stage_type"] == stage_type].sort_values("stage_order")
    stages = []
    for _, row in subset.iterrows():
        stages.append(
            FunnelStage(
                stage_name=row["stage_name"],
                stage_order=int(row["stage_order"]),
                conversion_probability=float(row["conversion_probability"]),
                dwell_min_months=float(row["dwell_min_months"]),
                dwell_mode_months=float(row["dwell_mode_months"]),
                dwell_max_months=float(row["dwell_max_months"]),
                expected_units=float(row["expected_units"]),
                expansion_probability=float(row["expansion_probability"]),
                expansion_multiple=float(row["expansion_multiple"]),
            )
        )
    return stages


def capacity_entries_from_df(df: pd.DataFrame, only_base: bool = True) -> list[CapacityEntry]:
    """If only_base, return the day-one (lead_time_months == 0, classification
    'assumed') rows only. If False, return the scenario capacity-expansion
    addition rows (classification 'scenario') instead."""
    if only_base:
        subset = df[df["classification"] == "assumed"]
    else:
        subset = df[df["classification"] == "scenario"]

    entries = []
    for _, row in subset.iterrows():
        entries.append(
            CapacityEntry(
                capacity_type=row["capacity_type"],
                available_capacity=float(row["available_capacity"]),
                unit_of_measure=row["unit_of_measure"],
                lead_time_months=float(row["lead_time_months"]),
                upfront_cost=float(row["upfront_cost"]),
                monthly_cost=float(row["monthly_cost"]),
                ramp_months=float(row["ramp_months"]),
            )
        )
    return entries


def symbotic_entries_from_df(df: pd.DataFrame, scenario: str) -> list[CustomerConcentrationEntry]:
    """Build CustomerConcentrationEntry list for one Symbotic sensitivity
    scenario (e.g. 'equal_split_assumed'), excluding the disclosed-total
    summary row."""
    subset = df[(df["scenario"] == scenario) & (df["customer_id"] != "TOTAL")]
    return [
        CustomerConcentrationEntry(
            customer_id=row["customer_id"],
            customer_name=row["customer_name"],
            contracted_backlog=float(row["contracted_backlog_usd"]),
        )
        for _, row in subset.iterrows()
    ]


def bot_auto_input_value(df: pd.DataFrame, input_name: str) -> str:
    match = df[df["input_name"] == input_name]
    if match.empty:
        raise KeyError(f"bot_auto_demo_inputs.csv has no row named '{input_name}'")
    return match.iloc[0]["value"]
