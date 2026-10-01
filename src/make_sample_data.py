"""
Generate small, synthetic sample data that mirrors the real BBMED schema
(same columns, same relationships and the same data-quality quirks) so the
notebook in this repo can run end to end without the company's real data.

Numbers here are illustrative only. The actual findings in the write-up
were produced on BBMED's real dataset, which is not published in this repo.

Run:
    python src/make_sample_data.py
"""

import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(7)
OUT = Path(__file__).resolve().parents[1] / "sample_data"
OUT.mkdir(exist_ok=True)

MACHINES = ["KM1", "KM2", "AXO10", "AXO11", "AXO12"]
PRODUCTS = [f"1026920{i}" for i in range(2050, 2070)]

# baseline availability/performance per machine, used to generate periods
MACHINE_PROFILE = {
    "KM1": (0.55, 0.90), "KM2": (0.47, 0.94),
    "AXO10": (0.39, 0.97), "AXO11": (0.40, 0.96), "AXO12": (0.41, 0.96),
}


def make_production_periods(n_orders=120):
    rows = []
    wr = 10000
    start = pd.Timestamp("2025-06-01 06:00")
    for order_no in range(700000, 700000 + n_orders):
        machine = RNG.choice(MACHINES)
        product = RNG.choice(PRODUCTS)
        avail, perf = MACHINE_PROFILE[machine]
        avail = np.clip(RNG.normal(avail, 0.08), 0.15, 0.95)
        perf = np.clip(RNG.normal(perf, 0.03), 0.6, 1.05)
        target_upm = RNG.choice([20, 25, 30, 40, 55])
        n_periods = RNG.integers(3, 10)
        t = start + pd.Timedelta(hours=int(RNG.integers(0, 4000)))
        for _ in range(n_periods):
            usage_s = int(RNG.integers(600, 6000))
            prod_s = int(usage_s * avail)
            stop_s = usage_s - prod_s
            org_share = RNG.uniform(0.4, 0.85)
            units = int(prod_s / 60 * target_upm * perf)
            rows.append({
                "CompanyID": 1,
                "WorkRecordID": wr,
                "MachineID": machine,
                "PointStart": t,
                "PointEnd": t + pd.Timedelta(seconds=usage_s),
                "CalcUsageTime": usage_s,
                "CalcProductionTime": prod_s,
                "OrderNo": order_no,
                "MachineOperatorID": int(RNG.integers(1, 20)),
                "ProductID": product,
                "ProducedDuringThePeriod": units,
                "TotalProducedByTheEndOfPeriod": units,
                "NeedToProduce": int(units * RNG.uniform(1.0, 1.3)),
                "Timer": usage_s,
                "CycleCurrency": round(RNG.uniform(0.9, 1.1), 3),
                "UtilisationRate": round(avail, 3),
                "OrderComplete": 0,
                "TargetUnitsPerMinute": target_upm,
                "Productionday": t.date(),
                "BookingNo": wr,
                "JOBNr": wr,
                "OldState": 0,
                "TimeOldState": 0,
                "WorkerCount": int(RNG.integers(1, 5)),
                "Shift": RNG.choice(["F", "S", "F,S"]),
                "StoppageTimeOrganiz": int(stop_s * org_share),
                "StoppageTimeTechnic": int(stop_s * (1 - org_share)),
                "CreateDate": t,
                "AddEditDate": t,
            })
            t = t + pd.Timedelta(seconds=usage_s) + pd.Timedelta(minutes=int(RNG.integers(1, 90)))
            wr += 1
    df = pd.DataFrame(rows)

    # inject a handful of "stale target rate" rows, same quirk as the real data
    bad = df.sample(frac=0.02, random_state=1).index
    df.loc[bad, "TargetUnitsPerMinute"] = RNG.choice([10, 13], size=len(bad))

    return df


def make_stoppages(periods: pd.DataFrame):
    """Reproduce the type 0/1/2/3 state-time ledger structure, including the
    orphaned rows (rows with no matching WorkRecordID) that show up in the
    real data.
    """
    rows = []
    reason_pool = list(range(0, 20))
    for _, p in periods.iterrows():
        prod = p.CalcProductionTime
        stop = p.CalcUsageTime - prod
        n_reasons = RNG.integers(1, 4)
        remaining = stop
        for i in range(n_reasons):
            share = remaining if i == n_reasons - 1 else int(remaining * RNG.uniform(0.2, 0.6))
            remaining -= share
            rows.append({
                "WorkRecordID": p.WorkRecordID, "StoppageType": 1,
                "StoppageNo": int(RNG.choice(reason_pool)),
                "PointEnd": p.PointEnd, "StoppageTime": max(share, 0),
                "StoppageCount": 1,
            })
        rows.append({
            "WorkRecordID": p.WorkRecordID, "StoppageType": 3,
            "StoppageNo": 0, "PointEnd": p.PointEnd,
            "StoppageTime": prod, "StoppageCount": 1,
        })
        if RNG.random() < 0.3:
            rows.append({
                "WorkRecordID": p.WorkRecordID, "StoppageType": 0,
                "StoppageNo": 0, "PointEnd": p.PointEnd,
                "StoppageTime": int(RNG.integers(10, 300)), "StoppageCount": int(RNG.integers(1, 5)),
            })
        # idle-before-start (type 2): large, unrelated to this period's own time
        if RNG.random() < 0.4:
            rows.append({
                "WorkRecordID": p.WorkRecordID, "StoppageType": 2,
                "StoppageNo": 0, "PointEnd": p.PointEnd,
                "StoppageTime": int(RNG.integers(60, 200000)), "StoppageCount": 1,
            })

    # orphaned stoppage rows: reference work record ids that don't exist
    max_wr = periods.WorkRecordID.max()
    for _ in range(int(len(periods) * 0.5)):
        rows.append({
            "WorkRecordID": int(max_wr + RNG.integers(1, 5000)), "StoppageType": int(RNG.choice([0, 1, 2])),
            "StoppageNo": int(RNG.choice(reason_pool)),
            "PointEnd": pd.Timestamp("2025-06-01"), "StoppageTime": int(RNG.integers(10, 5000)),
            "StoppageCount": 1,
        })
    return pd.DataFrame(rows)


def make_excel_log(periods: pd.DataFrame, match_rate=0.3, agree_rate=0.9):
    """A hand-kept log covering a subset of orders, mostly agreeing with MES
    but with a long tail of mismatches - same shape as the real reconciliation.
    """
    orders = periods.groupby("OrderNo").agg(
        machine=("MachineID", "first"),
        qty=("ProducedDuringThePeriod", "sum"),
        day=("Productionday", "first"),
    ).reset_index()
    sample = orders.sample(frac=match_rate, random_state=2).copy()
    rows = []
    for _, o in sample.iterrows():
        if RNG.random() < agree_rate:
            excel_qty = int(o.qty * RNG.uniform(0.95, 1.05))
        else:
            excel_qty = int(o.qty * RNG.choice([0.3, 0.5, 2.0, 5.0]))
        rows.append({
            "order_no": o.OrderNo, "day": o.day, "machine_number": o.machine,
            "excel_qty": excel_qty, "department": "202 Flasche/Spender",
        })
    return pd.DataFrame(rows)


def make_energy_readings(n_points=400):
    meters = {
        "IFD001": ("falschacht", 0.86), "IFD002": ("etikket", 0.12),
        "IFD003": ("verschr", 1.11), "IFD004": ("abf", 0.74),
        "IFD005": ("Flaschenbeschicker", 0.37),
    }
    rows = []
    t0 = pd.Timestamp("2026-09-23 14:26:40")
    for tag, (_, kw) in meters.items():
        cum = RNG.uniform(0, 500)
        for i in range(n_points):
            ts = t0 + pd.Timedelta(seconds=63 * i)
            cum += kw / 60 * (63 / 60) + RNG.normal(0, 0.002)
            rows.append({"reading_id": i, "timestamp": ts,
                         "energy_meter_device_asset_tag": f"{tag} Energy meter",
                         "total_energy_passed": round(cum, 4)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    periods = make_production_periods()
    stoppages = make_stoppages(periods)
    excel_log = make_excel_log(periods)
    energy = make_energy_readings()

    periods.to_csv(OUT / "sample_production_periods.csv", index=False)
    stoppages.to_csv(OUT / "sample_stoppages.csv", index=False)
    excel_log.to_csv(OUT / "sample_excel_log.csv", index=False)
    energy.to_csv(OUT / "sample_energy_readings.csv", index=False)

    print(f"Wrote {len(periods)} periods, {len(stoppages)} stoppage rows, "
          f"{len(excel_log)} excel rows, {len(energy)} energy readings to {OUT}")
