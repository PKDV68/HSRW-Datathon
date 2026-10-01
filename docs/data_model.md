# Data model

BBMED (a cosmetics manufacturer) provided 20 files from four systems: a
Manufacturing Execution System (MES), ERP product master data, a hand-kept
Excel operator log, and energy meters on line KM1. None of these systems
share a consistent key, so mapping the relationships between them was the
first and most important step of the project.

## Entity map

```
Product master (ERP)  --article no.-->  Production order  <--order no. + day--  Excel operator log
                                                |
                                                v
        Machine / line  ------------->  Work record (period)  <--line + timestamp--  KM1 energy meters
                                                |
                        --------------------------------------------
                        |                       |                  |
                        v                       v                  v
                Stoppage states          Staff assignment      Reject records
                        |
                        v
                Stoppage reason (per machine group)
```

- **Solid relationships** share an explicit ID column (`OrderNo`,
  `WorkRecordID`, `MachineID`, `ArticleNo`).
- **Dashed relationships** have no shared ID at all:
  - the Excel log only matches MES on `order number + calendar day`
  - the energy meters only match MES on `line + timestamp window`

## Known gaps

| Table | Gap | Effect |
|---|---|---|
| `mes_stoppages` | 32% of rows reference a `WorkRecordID` that doesn't exist in the period table | Reason-level totals are a lower bound |
| `mes_rejections_ids_x_work_ids` | Links to under 3% of work records | No reliable Quality factor for OEE |
| `excl_production_data_2026` | Only about 29% of MES orders have a matching Excel row | Reconciliation covers a partial sample |
| energy readings | Continuous logging only started recently, covering one order | Order-level energy figures are a single-case proof of concept |

See `docs/findings.md` for how each of these was handled, and what it means
for the reliability of the numbers.
