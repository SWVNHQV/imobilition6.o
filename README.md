
# NexusChain AI Control Tower — Pro

This is the hackathon-ready version built around the uploaded synthetic SAP-style warehouse workbook.

## Core architecture

Excel workbook
→ Ingestion Agent
→ Data Quality Agent
→ Anomaly Agent
→ Relationship / Correlation Agent
→ LLM Root-Cause Agent
→ Impact scoring
→ Action / Remediation Agent
→ Human Approval
→ Simulated Execution
→ Audit Trail

## Workbook coverage

Required operational/master sheets:
- Material_Master
- Inventory_Stock
- Warehouse_Bin
- Deliveries_Dispatch
- Purchase_Replenish
- Vendor_Master

Documentation sheets:
- README
- Data_Dictionary

The app loads every sheet and exposes them in Data Explorer.

## What the system detects

Master data:
- missing Base UoM
- missing / negative Reorder Point
- ROP below Safety Stock
- duplicate material descriptions
- orphan material references
- obsolete/blocked lifecycle still active downstream
- blocked vendor with active PO
- hazmat/storage handling mismatch

Operational anomalies:
- negative stock
- expired batches
- stale/dead stock
- bin over-capacity
- overdue active deliveries
- missing route
- delivery demand > physical available stock
- overdue purchase orders

## Cross-system correlation

Cases are built around actual keys in the workbook:
- Material
- Plant
- Assigned Material
- Delivery
- Purchase Order
- Vendor

A correlated case contains evidence from all connected sheets:
Material_Master → Inventory_Stock → Warehouse_Bin → Deliveries_Dispatch → Purchase_Replenish → Vendor_Master.

## LLM capability

The LLM is built in but used only for explanation/synthesis. A small, fast model is sufficient because all operational detection, calculations, joins, correlation, and impact scoring are deterministic.

Set:
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4.1-mini

The LLM receives the structured evidence pack produced by deterministic agents and is instructed:
- never invent values
- use only supplied evidence
- explain cross-system causality
- distinguish facts from inference
- propose, not execute, actions

Without an API key, the app automatically uses a deterministic evidence-grounded fallback and clearly labels it as such.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Demo flow

1. Open Control Tower.
2. Select a critical case such as MAT-100024 or MAT-100003.
3. Open Root Cause AI.
4. Click Generate AI Root Cause Explanation.
5. Show evidence from every connected sheet.
6. Move to Approvals.
7. Edit the proposed action if needed.
8. Approve or Simulate Execute.
9. Open Audit to show the governed decision trail.

## Governance

No live ERP/SAP write-back is implemented. Corrective actions are proposed and simulated only, and human approval is mandatory before a case is marked Approved.
