"""
Core analysis functions used in notebooks/01_oee_and_downtime.ipynb and
notebooks/02_stoppage_decode_and_energy.ipynb.

These are written against the real BBMED schema (see docs/data_model.md) and
run unchanged on either the real data or the synthetic sample_data/ files.
"""

import numpy as np
import pandas as pd


def order_rollup(periods: pd.DataFrame) -> pd.DataFrame:
    """Roll production periods up to one row per OrderNo and compute
    Availability, Performance and OEE.

    Availability = production time / usage time
    Performance  = (units / production minutes) / target units per minute
    OEE          = Availability x Performance
    """
    g = periods.groupby("OrderNo").agg(
        machine_n=("MachineID", "nunique"),
        product_n=("ProductID", "nunique"),
        machine=("MachineID", "first"),
        product=("ProductID", "first"),
        usage_s=("CalcUsageTime", "sum"),
        prod_s=("CalcProductionTime", "sum"),
        units=("ProducedDuringThePeriod", "sum"),
        target_upm=("TargetUnitsPerMinute", "first"),
        target_upm_std=("TargetUnitsPerMinute", "std"),
        workers=("WorkerCount", "mean"),
        n_periods=("WorkRecordID", "count"),
    ).reset_index()

    g["availability"] = g.prod_s / g.usage_s
    prod_minutes = g.prod_s / 60
    g["performance"] = np.where(prod_minutes > 0, (g.units / prod_minutes) / g.target_upm, np.nan)
    g["oee"] = g.availability * g.performance
    return g


def clean_orders(rollup: pd.DataFrame, perf_bounds=(0.2, 1.3)) -> pd.DataFrame:
    """Apply the same cleaning rules used in the write-up:
    - drop orders spanning more than one machine or product
    - drop orders whose performance falls outside a plausible range
      (a symptom of stale target-rate master data)
    """
    single = (rollup.machine_n == 1) & (rollup.product_n == 1)
    plausible = rollup.performance.between(*perf_bounds)
    return rollup[single & plausible].copy()


def stoppage_org_technical_share(periods: pd.DataFrame) -> pd.DataFrame:
    """Organisational vs technical downtime share per machine, from the
    pre-aggregated period-level fields (robust to the stoppage-table's
    running-counter quirk - see decode_stoppage_types below)."""
    g = periods.groupby("MachineID").agg(
        org=("StoppageTimeOrganiz", "sum"),
        tech=("StoppageTimeTechnic", "sum"),
    )
    g["org_share"] = g.org / (g.org + g.tech)
    return g.sort_values("org_share", ascending=False)


def decode_stoppage_types(periods: pd.DataFrame, stoppages: pd.DataFrame) -> pd.DataFrame:
    """Test the hypothesis that mes_stoppages is a state-time ledger, not a
    broken per-event log:
        type 3 = producing        (should equal CalcProductionTime)
        type 1 = classified stop  (reason-coded)
        type 0 = unclassified micro-stop
        type 2 = idle time before the period started

    Returns one row per WorkRecordID with the summed time per type next to
    the period's own CalcProductionTime/CalcUsageTime, so you can check the
    match rate yourself.
    """
    pivot = stoppages.pivot_table(
        index="WorkRecordID", columns="StoppageType", values="StoppageTime",
        aggfunc="sum", fill_value=0,
    )
    pivot.columns = [f"type_{c}" for c in pivot.columns]
    merged = periods.set_index("WorkRecordID")[["CalcUsageTime", "CalcProductionTime"]].join(
        pivot, how="inner"
    )
    if "type_3" in merged:
        merged["type3_matches_prod_time"] = (merged.type_3 - merged.CalcProductionTime).abs() <= 2
    return merged


def reconcile_mes_excel(order_rollup_df: pd.DataFrame, excel_log: pd.DataFrame) -> pd.DataFrame:
    """Compare MES order totals against the hand-kept Excel log on shared
    order numbers. Returns per-order percent difference; summarise with the
    median, not the mean - a handful of mismatches otherwise dominate it.
    """
    mes = order_rollup_df.set_index("OrderNo")["units"]
    excel = excel_log.groupby("order_no")["excel_qty"].sum()
    both = pd.DataFrame({"mes_qty": mes, "excel_qty": excel}).dropna()
    both["pct_diff"] = (both.mes_qty - both.excel_qty) / both.excel_qty.replace(0, np.nan) * 100
    return both
