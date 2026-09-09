
from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime

SNAPSHOT_DATE = pd.Timestamp("2026-09-05")
CORE_SHEETS = [
    "Material_Master", "Inventory_Stock", "Warehouse_Bin",
    "Deliveries_Dispatch", "Purchase_Replenish", "Vendor_Master"
]

def load_workbook(path: str) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(path)
    missing = [s for s in CORE_SHEETS if s not in xls.sheet_names]
    if missing:
        raise ValueError(f"Required sheets missing: {missing}")
    return {s: pd.read_excel(path, sheet_name=s) for s in xls.sheet_names}

def clean_data(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for name, df in data.items():
        d = df.copy()
        d.columns = [str(c).strip() for c in d.columns]
        for c in d.columns:
            if d[c].dtype == "object":
                d[c] = d[c].map(lambda x: x.strip() if isinstance(x, str) else x)
        out[name] = d
    return out

def num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def text(s):
    return s.astype(str).replace({"nan": "", "None": ""}).str.strip()

def active_delivery(d):
    return text(d["Status"]).str.upper().isin(["OPEN", "PICKED", "PACKED"])

def active_po(p):
    return text(p["PO Status"]).str.upper().isin(["OPEN", "PARTIAL"])

def issue(issue_id, category, severity, entity, title, detail, evidence, agent):
    return {
        "issue_id": issue_id, "category": category, "severity": severity,
        "entity": str(entity), "title": title, "detail": detail,
        "evidence": evidence, "agent": agent
    }

def _is_missing_series(s):
    """Return a boolean mask for genuinely missing values across common Excel types."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.isna()
    if pd.api.types.is_numeric_dtype(s):
        return s.isna()
    return s.isna() | text(s).eq("")


def _column_severity(sheet_name, column_name):
    """Assign a useful default severity to generic completeness findings."""
    name = str(column_name).strip().lower()
    key_terms = ("material", "vendor", "delivery", "purchase order", "po", "bin")
    critical_terms = ("status", "lifecycle", "plant", "uom", "unit", "type", "group", "route", "date")
    if sheet_name == "Material_Master":
        if any(x in name for x in key_terms) or any(x in name for x in critical_terms):
            return "High"
        return "Medium"
    if any(x in name for x in key_terms):
        return "High"
    return "Medium"


def _generic_missing_column_findings(sheet_name, df, out):
    """Detect missing values in ANY column, including columns added in future workbook versions.

    This is intentionally schema-agnostic: no hard-coded list of allowed column names is used.
    Business-specific rules below still handle semantic/relational problems that a null check cannot.
    """
    # Prefer a business identifier for the finding entity when one exists.
    id_candidates = [
        "Material", "Vendor", "Delivery", "Purchase Order", "Bin",
        "Assigned Material", "PO", "ID", "Code"
    ]
    id_col = next((c for c in id_candidates if c in df.columns), None)

    for col in df.columns:
        missing = _is_missing_series(df[col])
        if not bool(missing.any()):
            continue

        severity = _column_severity(sheet_name, col)
        affected = df.index[missing].tolist()

        # One finding per affected record gives the operator an exact row/ID and value.
        for idx in affected:
            row = df.loc[idx]
            entity = row[id_col] if id_col and not _is_missing_series(pd.Series([row[id_col]])).iloc[0] else f"{sheet_name} row {idx + 2}"
            actual = row[col]
            evidence = {
                "Sheet": sheet_name,
                "Column": str(col),
                "ActualValue": None if pd.isna(actual) else actual,
                "RowNumber": int(idx) + 2,
            }
            if id_col:
                evidence[id_col] = row[id_col]

            out.append(issue(
                f"DQ-{len(out)+1:04d}",
                "Data Completeness",
                severity,
                entity,
                f"Missing {col}",
                f"Column '{col}' is blank for {entity} in {sheet_name}.",
                evidence,
                "Data Quality Agent"
            ))


def data_quality_agent(data):
    m, inv, bins, d, po, v = [data[x] for x in CORE_SHEETS]
    out = []

    # GENERIC/FUTURE-PROOF COMPLETENESS CHECK
    # Detect missing values in every column of every loaded core sheet.
    # This catches newly introduced fields such as Material Type or Material Group
    # without requiring another hard-coded rule.
    for sheet_name, df in [("Material_Master", m), ("Inventory_Stock", inv),
                           ("Warehouse_Bin", bins), ("Deliveries_Dispatch", d),
                           ("Purchase_Replenish", po), ("Vendor_Master", v)]:
        _generic_missing_column_findings(sheet_name, df, out)

    # Business-specific master-data validity rules.
    if "Reorder Point" in m.columns:
        for _, r in m[num(m["Reorder Point"]) < 0].iterrows():
            out.append(issue(f"DQ-{len(out)+1:04d}", "Master Data", "Critical", r["Material"],
                             "Negative Reorder Point", "Reorder point is below zero.",
                             {"Material": r["Material"], "Reorder Point": r["Reorder Point"]}, "Data Quality Agent"))

    # PO vendor referential integrity.
    if "Vendor" in v.columns and "Vendor" in po.columns:
        vendor_ids = set(text(v["Vendor"]))
        for ven in sorted(set(text(po["Vendor"])) - vendor_ids - {""}):
            out.append(issue(f"DQ-{len(out)+1:04d}", "Referential Integrity", "Critical", ven,
                             "Orphan vendor reference", "Purchase_Replenish references a vendor absent from Vendor_Master.",
                             {"Vendor": ven}, "Data Quality Agent"))

    # PO temporal relationship.
    if "Order Date" in po.columns and "Expected Delivery" in po.columns:
        od = pd.to_datetime(po["Order Date"], errors="coerce")
        ed = pd.to_datetime(po["Expected Delivery"], errors="coerce")
        bad_dates = od.notna() & ed.notna() & (ed < od)
        for _, r in po[bad_dates].iterrows():
            out.append(issue(f"DQ-{len(out)+1:04d}", "Procurement Data", "High", r["Purchase Order"],
                             "Invalid PO dates", "Expected delivery date precedes order date.",
                             {"PO": r["Purchase Order"], "Order Date": str(r["Order Date"]), "Expected Delivery": str(r["Expected Delivery"])}, "Data Quality Agent"))

    # Planning relationship: only evaluate when both fields exist.
    if "Reorder Point" in m.columns and "Safety Stock" in m.columns:
        q = m[num(m["Reorder Point"]) < num(m["Safety Stock"])]
        for _, r in q.iterrows():
            # Avoid treating a missing ROP as a semantic value of zero; completeness is handled above.
            if pd.isna(r["Reorder Point"]) or text(pd.Series([r["Reorder Point"]])).iloc[0] == "":
                continue
            out.append(issue(f"DQ-{len(out)+1:04d}", "Planning Data", "High", r["Material"],
                             "ROP below Safety Stock", "Reorder Point is lower than Safety Stock.",
                             {"Material": r["Material"], "ROP": r["Reorder Point"], "SafetyStock": r["Safety Stock"]},
                             "Data Quality Agent"))

    # Description / material-group semantic consistency checks (deterministic keyword guardrail).
    if "Description" in m.columns and "Material Group" in m.columns:
        group_terms = {
            "FASTEN": ["FASTEN", "BOLT", "NUT", "SCREW", "WASHER", "CLAMP"],
            "FLUID": ["FLUID", "OIL", "COOLANT", "LUBRIC", "HYDRAULIC"],
            "ELEC": ["ELEC", "CABLE", "WIRE", "CONNECTOR", "SWITCH"],
        }
        for _, r in m.iterrows():
            if _is_missing_series(pd.Series([r.get("Description", "")])).iloc[0] or _is_missing_series(pd.Series([r.get("Material Group", "")])).iloc[0]:
                continue
            desc = text(pd.Series([r.get("Description", "")])).iloc[0].upper()
            grp = str(r.get("Material Group", "")).strip().upper()
            expected = group_terms.get(grp, [])
            if desc and expected and not any(term in desc for term in expected):
                out.append(issue(f"DQ-{len(out)+1:04d}", "Master Data", "Medium", r["Material"],
                                 "Description / Material Group mismatch",
                                 f"Description '{r['Description']}' does not contain a term expected for Material Group '{r['Material Group']}'.",
                                 {"Material": r["Material"], "Description": r["Description"], "Material Group": r["Material Group"]}, "Data Quality Agent"))

    # Duplicate descriptions.
    if "Description" in m.columns:
        dup = m[m["Description"].notna() & ~text(m["Description"]).eq("") & m["Description"].duplicated(False)]
        for desc, g in dup.groupby("Description"):
            mats = g["Material"].astype(str).tolist() if "Material" in g.columns else g.index.astype(str).tolist()
            out.append(issue(f"DQ-{len(out)+1:04d}", "Master Data", "High", "|".join(mats),
                             "Potential duplicate material records",
                             f"Multiple material IDs share the same description: {desc}.",
                             {"Materials": mats, "Description": desc}, "Data Quality Agent"))

    # Orphan references.
    if "Material" in m.columns:
        master = set(text(m["Material"]))
        for sheet_name, df in [("Inventory_Stock", inv), ("Deliveries_Dispatch", d),
                               ("Purchase_Replenish", po), ("Warehouse_Bin", bins)]:
            col = "Material" if "Material" in df.columns else "Assigned Material" if "Assigned Material" in df.columns else None
            if not col:
                continue
            refs = set(text(df[col])) - {""}
            for mat in sorted(refs - master):
                out.append(issue(f"DQ-{len(out)+1:04d}", "Referential Integrity", "Critical", mat,
                                 f"Orphan material reference in {sheet_name}",
                                 f"{mat} appears in {sheet_name} but is absent from Material_Master.",
                                 {"Sheet": sheet_name, "Material": mat}, "Data Quality Agent"))

    # Lifecycle propagation.
    if "Lifecycle Status" in m.columns and "Material" in m.columns:
        for _, r in m[text(m["Lifecycle Status"]).str.upper().isin(["OBSOLETE", "BLOCKED"])].iterrows():
            mat = str(r["Material"])
            iv = inv[text(inv["Material"]) == mat] if "Material" in inv.columns else inv.iloc[0:0]
            dd = d[text(d["Material"]) == mat] if "Material" in d.columns else d.iloc[0:0]
            pp = po[text(po["Material"]) == mat] if "Material" in po.columns else po.iloc[0:0]
            if len(iv) + len(dd) + len(pp):
                out.append(issue(f"DQ-{len(out)+1:04d}", "Lifecycle Governance", "Critical", mat,
                                 f"{r['Lifecycle Status']} material still operational",
                                 "Lifecycle status is not propagated to operational processes.",
                                 {"Lifecycle": r["Lifecycle Status"], "InventoryRows": len(iv),
                                  "DeliveryRows": len(dd), "PORows": len(pp)},
                                 "Data Quality Agent"))

    # Vendor governance.
    if "Vendor" in v.columns and "Procurement Block" in v.columns and "Vendor" in po.columns:
        blocked_vendors = set(text(v.loc[text(v["Procurement Block"]).str.upper().isin(["Y", "YES", "BLOCKED"]), "Vendor"]))
        for ven in sorted(blocked_vendors - {""}):
            rows = po[text(po["Vendor"]) == ven]
            active = rows[active_po(rows)] if not rows.empty else rows
            if not active.empty:
                out.append(issue(f"DQ-{len(out)+1:04d}", "Vendor Governance", "High", ven,
                                 "Blocked vendor has active PO",
                                 "Procurement block conflicts with an open/partial purchase order.",
                                 {"Vendor": ven, "POs": text(active["Purchase Order"]).tolist()},
                                 "Data Quality Agent"))

    # Hazmat / storage mismatch.
    if "Material" in m.columns and "Hazmat Flag" in m.columns and "Assigned Material" in bins.columns and "Storage Type" in bins.columns:
        for _, r in m.iterrows():
            mat = str(r["Material"])
            b = bins[text(bins["Assigned Material"]) == mat]
            if b.empty:
                continue
            is_haz = str(r["Hazmat Flag"]).upper() in {"Y", "YES"}
            types = set(text(b["Storage Type"]).str.upper())
            if is_haz and any(t != "HAZ" for t in types):
                out.append(issue(f"DQ-{len(out)+1:04d}", "Compliance", "High", mat,
                                 "Hazmat material in non-HAZ storage",
                                 "Hazmat flag conflicts with warehouse storage type.",
                                 {"HazmatFlag": r["Hazmat Flag"], "StorageTypes": sorted(types)},
                                 "Data Quality Agent"))
            if (not is_haz) and "HAZ" in types:
                out.append(issue(f"DQ-{len(out)+1:04d}", "Compliance", "High", mat,
                                 "Non-hazmat material in HAZ storage",
                                 "Warehouse handling type conflicts with master hazmat flag.",
                                 {"HazmatFlag": r["Hazmat Flag"], "StorageTypes": sorted(types)},
                                 "Data Quality Agent"))
    return pd.DataFrame(out)

def _fmt_num(x):
    try:
        x=float(x)
        return f"{x:,.0f}" if x.is_integer() else f"{x:,.2f}"
    except Exception:
        return str(x)

def _days_text(days):
    return f"{int(days)} day" if int(days) == 1 else f"{int(days)} days"

def anomaly_agent(data):
    m, inv, bins, d, po, v = [data[x] for x in CORE_SHEETS]
    out = []

    # Negative inventory: calculate the size of the deficit and net position after blocked stock.
    for _, r in inv[num(inv["Qty On Hand"]) < 0].iterrows():
        on_hand=float(num(pd.Series([r["Qty On Hand"]])).iloc[0])
        blocked=float(num(pd.Series([r["Blocked Qty"]])).iloc[0])
        transit=float(num(pd.Series([r["In-Transit Qty"]])).iloc[0])
        net=on_hand-blocked
        projected=on_hand-blocked+transit
        out.append(issue(f"AN-{len(out)+1:04d}", "Inventory", "Critical", r["Material"],
                         "Negative on-hand inventory",
                         f"On-hand is {_fmt_num(on_hand)} units, which is {_fmt_num(abs(on_hand))} below zero. Blocked stock is {_fmt_num(blocked)} and in-transit is {_fmt_num(transit)}, giving a current net available of {_fmt_num(net)} and projected position after inbound of {_fmt_num(projected)}.",
                         {"Material": r["Material"], "Plant": r["Plant"], "Storage": r["Storage Location"],
                          "Batch": r["Batch"], "QtyOnHand": on_hand, "BlockedQty": blocked, "InTransitQty": transit,
                          "NetAvailable": net, "ProjectedAfterInbound": projected}, "Anomaly Agent"))

    # Expired inventory: quantify how old the stock is and how much remains.
    expiry = pd.to_datetime(inv["Batch Expiry"], errors="coerce")
    for _, r in inv[(expiry < SNAPSHOT_DATE) & (num(inv["Qty On Hand"]) > 0)].iterrows():
        exp=pd.to_datetime(r["Batch Expiry"], errors="coerce")
        days=(SNAPSHOT_DATE-exp).days
        qty=float(num(pd.Series([r["Qty On Hand"]])).iloc[0])
        out.append(issue(f"AN-{len(out)+1:04d}", "Inventory", "Critical", r["Material"],
                         "Expired inventory",
                         f"Batch expired on {exp.strftime('%Y-%m-%d')}, {_days_text(days)} before the {SNAPSHOT_DATE.strftime('%Y-%m-%d')} snapshot, while {_fmt_num(qty)} units remain on hand.",
                         {"Material": r["Material"], "Batch": r["Batch"], "Expiry": exp.strftime('%Y-%m-%d'), "DaysExpired": days, "Qty": qty}, "Anomaly Agent"))

    # Stale inventory: calculate exact days since movement.
    last_move = pd.to_datetime(inv["Last Movement Date"], errors="coerce")
    for _, r in inv[(SNAPSHOT_DATE-last_move).dt.days > 90].iterrows():
        lm=pd.to_datetime(r["Last Movement Date"], errors="coerce")
        days=(SNAPSHOT_DATE-lm).days
        qty=float(num(pd.Series([r["Qty On Hand"]])).iloc[0])
        out.append(issue(f"AN-{len(out)+1:04d}", "Inventory", "Medium", r["Material"],
                         "Stale inventory",
                         f"Last movement was {lm.strftime('%Y-%m-%d')}, {_days_text(days)} ago. {_fmt_num(qty)} units remain on hand, so the stock has been inactive beyond the 90-day threshold by {_days_text(days-90)}.",
                         {"Material": r["Material"], "LastMovement": lm.strftime('%Y-%m-%d'), "DaysSinceMovement": days, "QtyOnHand": qty, "ThresholdDays": 90}, "Anomaly Agent"))

    # Blocked quantity cannot exceed on-hand quantity.
    bad_blocked = num(inv["Blocked Qty"]) > num(inv["Qty On Hand"])
    for _, r in inv[bad_blocked].iterrows():
        blocked=float(num(pd.Series([r["Blocked Qty"]])).iloc[0]); oh=float(num(pd.Series([r["Qty On Hand"]])).iloc[0])
        excess=blocked-oh
        out.append(issue(f"AN-{len(out)+1:04d}", "Inventory", "Critical", r["Material"],
                         "Blocked quantity exceeds on-hand",
                         f"Blocked quantity is {_fmt_num(blocked)} against {_fmt_num(oh)} on-hand, exceeding physical stock by {_fmt_num(excess)} units. This makes the implied available quantity {_fmt_num(oh-blocked)} units.",
                         {"Material": r["Material"], "Plant": r["Plant"], "BlockedQty": blocked, "QtyOnHand": oh, "ExcessBlocked": excess, "ImpliedAvailable": oh-blocked}, "Anomaly Agent"))

    # Bin capacity: calculate excess units and utilization percentage.
    for _, r in bins[num(bins["Occupied"]) > num(bins["Capacity"])].iterrows():
        cap=float(num(pd.Series([r["Capacity"]])).iloc[0]); occ=float(num(pd.Series([r["Occupied"]])).iloc[0])
        excess=occ-cap; util=(occ/cap*100) if cap else None
        util_txt=f"{util:.0f}%" if util is not None else "undefined"
        out.append(issue(f"AN-{len(out)+1:04d}", "Warehouse", "High", r["Assigned Material"],
                         "Warehouse bin over capacity",
                         f"Bin {r['Bin']} holds {_fmt_num(occ)} units against capacity {_fmt_num(cap)}: {_fmt_num(excess)} units over capacity ({util_txt} utilization).",
                         {"Bin": r["Bin"], "Capacity": cap, "Occupied": occ, "Excess": excess,
                          "UtilizationPct": round(util,1) if util is not None else None, "Plant": r["Plant"]}, "Anomaly Agent"))

    if "Bin Status" in bins.columns:
        bad_status = text(bins["Bin Status"]).str.upper().eq("FREE") & (num(bins["Occupied"]) > 0)
        for _, r in bins[bad_status].iterrows():
            occ=float(num(pd.Series([r["Occupied"]])).iloc[0])
            out.append(issue(f"AN-{len(out)+1:04d}", "Warehouse", "High", r["Bin"],
                             "FREE bin has occupied stock",
                             f"Bin status is FREE but {_fmt_num(occ)} units are recorded as occupied; the status conflicts with the physical quantity field.",
                             {"Bin": r["Bin"], "Plant": r["Plant"], "Occupied": occ, "BinStatus": r["Bin Status"]}, "Anomaly Agent"))

    # Missing planned GI date on active delivery.
    if "Planned GI Date" in d.columns:
        missing_gi = active_delivery(d) & pd.to_datetime(d["Planned GI Date"], errors="coerce").isna()
        for _, r in d[missing_gi].iterrows():
            out.append(issue(f"AN-{len(out)+1:04d}", "Dispatch", "High", r["Delivery"],
                             "Missing planned GI date", f"Delivery {r['Delivery']} is {r['Status']} with {_fmt_num(r['Order Qty'])} units, but no planned goods-issue date is available.",
                             {"Delivery": r["Delivery"], "Material": r["Material"], "Status": r["Status"], "OrderQty": r["Order Qty"]}, "Anomaly Agent"))

    # Overdue deliveries: calculate days late.
    planned = pd.to_datetime(d["Planned GI Date"], errors="coerce")
    overdue = active_delivery(d) & (planned < SNAPSHOT_DATE)
    for _, r in d[overdue].iterrows():
        pg=pd.to_datetime(r["Planned GI Date"], errors="coerce"); days=(SNAPSHOT_DATE-pg).days; qty=float(num(pd.Series([r["Order Qty"]])).iloc[0])
        out.append(issue(f"AN-{len(out)+1:04d}", "Dispatch", "High", r["Delivery"],
                         "Overdue active delivery",
                         f"Delivery {r['Delivery']} is {r['Status']} and {days} days overdue: planned GI {pg.strftime('%Y-%m-%d')} versus snapshot {SNAPSHOT_DATE.strftime('%Y-%m-%d')}. Order quantity is {_fmt_num(qty)} units.",
                         {"Delivery": r["Delivery"], "Material": r["Material"], "Status": r["Status"], "PlannedGI": pg.strftime('%Y-%m-%d'), "DaysOverdue": days, "OrderQty": qty}, "Anomaly Agent"))

    # Missing route
    for _, r in d[d["Route"].isna() | text(d["Route"]).eq("")].iterrows():
        out.append(issue(f"AN-{len(out)+1:04d}", "Dispatch", "Medium", r["Delivery"],
                         "Missing delivery route", f"Delivery {r['Delivery']} for {_fmt_num(r['Order Qty'])} units has no route assigned to ship to {r['Ship-To']}.",
                         {"Delivery": r["Delivery"], "Material": r["Material"], "ShipTo": r["Ship-To"], "OrderQty": r["Order Qty"], "Route": r["Route"]}, "Anomaly Agent"))

    # Demand vs physical availability by material + plant. Include coverage and inbound projection.
    inv2 = inv.copy(); inv2["Available"] = num(inv2["Qty On Hand"]) - num(inv2["Blocked Qty"])
    avail = inv2.groupby(["Material","Plant"])["Available"].sum()
    transit_by_key = inv2.groupby(["Material","Plant"])["In-Transit Qty"].sum()
    active = d[active_delivery(d)].copy(); active["Demand"] = num(active["Order Qty"])
    demand = active.groupby(["Material","Plant"])["Demand"].sum()
    for key, qty in demand.items():
        available=float(avail.get(key,0)); transit=float(transit_by_key.get(key,0)); projected=available+transit
        shortfall=max(0,float(qty)-available); projected_shortfall=max(0,float(qty)-projected)
        coverage=(available/float(qty)*100) if qty else 100
        projected_coverage=(projected/float(qty)*100) if qty else 100
        if qty > available:
            out.append(issue(f"AN-{len(out)+1:04d}", "Supply Risk", "Critical", key[0],
                             "Active delivery demand exceeds available stock",
                             f"Active demand is {_fmt_num(qty)} units versus {_fmt_num(available)} available, covering {coverage:.1f}% of demand and leaving a {_fmt_num(shortfall)}-unit shortfall. Including {_fmt_num(transit)} in-transit units, projected supply is {_fmt_num(projected)} with {_fmt_num(projected_shortfall)} units still short ({projected_coverage:.1f}% coverage).",
                             {"Material": key[0], "Plant": key[1], "ActiveDemand": float(qty), "Available": available,
                              "CoveragePct": round(coverage,1), "InTransit": transit, "ProjectedSupply": projected,
                              "Shortfall": shortfall, "ProjectedShortfall": projected_shortfall,
                              "ProjectedCoveragePct": round(projected_coverage,1)}, "Anomaly Agent"))

    # Phantom expiry
    phantom = inv[inv["Batch"].isna() & inv["Batch Expiry"].notna()]
    for _, r in phantom.iterrows():
        out.append(issue(f"AN-{len(out)+1:04d}", "Inventory", "High", r["Material"],
                         "Expiry date without Batch ID", f"Expiry date {pd.to_datetime(r['Batch Expiry']).strftime('%Y-%m-%d')} is populated, but the batch identifier is blank, so the expiry cannot be tied to a specific batch.",
                         {"Material": r["Material"], "Plant": r["Plant"], "Expiry": str(r["Batch Expiry"]), "Batch": r["Batch"]}, "Anomaly Agent"))

    if "Unit Price" in po.columns:
        for _, r in po[num(po["Unit Price"]).eq(0) & po["Unit Price"].notna()].iterrows():
            out.append(issue(f"AN-{len(out)+1:04d}", "Procurement", "High", r["Purchase Order"],
                             "Zero PO unit price", f"PO {r['Purchase Order']} has {_fmt_num(r['PO Qty'])} units at unit price 0, so the recorded PO line value calculates to 0.",
                             {"PO": r["Purchase Order"], "POQty": r["PO Qty"], "UnitPrice": r["Unit Price"], "CalculatedLineValue": 0}, "Anomaly Agent"))
    if "Order Date" in po.columns and "Expected Delivery" in po.columns:
        od=pd.to_datetime(po["Order Date"],errors="coerce"); ed=pd.to_datetime(po["Expected Delivery"],errors="coerce")
        for _, r in po[od.notna() & ed.notna() & (ed < od)].iterrows():
            order_dt=pd.to_datetime(r["Order Date"]); exp_dt=pd.to_datetime(r["Expected Delivery"]); gap=(order_dt-exp_dt).days
            out.append(issue(f"AN-{len(out)+1:04d}", "Procurement", "High", r["Purchase Order"],
                             "Expected delivery precedes PO date", f"Expected delivery {exp_dt.strftime('%Y-%m-%d')} is {gap} days before order date {order_dt.strftime('%Y-%m-%d')}, which is impossible chronologically.",
                             {"PO": r["Purchase Order"], "OrderDate": order_dt.strftime('%Y-%m-%d'), "ExpectedDelivery": exp_dt.strftime('%Y-%m-%d'), "DaysReversed": gap}, "Anomaly Agent"))

    # Overdue POs: calculate lateness and outstanding quantity.
    expected = pd.to_datetime(po["Expected Delivery"], errors="coerce")
    overdue_po = active_po(po) & (expected < SNAPSHOT_DATE)
    for _, r in po[overdue_po].iterrows():
        exp=pd.to_datetime(r["Expected Delivery"]); days=(SNAPSHOT_DATE-exp).days; qty=float(num(pd.Series([r["PO Qty"]])).iloc[0])
        out.append(issue(f"AN-{len(out)+1:04d}", "Procurement", "High", r["Purchase Order"],
                         "Overdue purchase order",
                         f"PO {r['Purchase Order']} is {r['PO Status']} and {days} days past expected delivery ({exp.strftime('%Y-%m-%d')}). The PO quantity is {_fmt_num(qty)} units, so inbound replenishment is late by {days} days.",
                         {"PO": r["Purchase Order"], "Material": r["Material"], "Vendor": r["Vendor"], "ExpectedDelivery": exp.strftime('%Y-%m-%d'), "DaysOverdue": days, "POQty": qty}, "Anomaly Agent"))
    return pd.DataFrame(out)

def relationship_graph(data):
    """Return an auditable graph of real workbook relationships."""
    m, inv, bins, d, po, v = [data[x] for x in CORE_SHEETS]
    nodes, edges = [], []

    def node(kind, key, label, meta=None):
        nid=f"{kind}:{key}"
        if not any(x["id"]==nid for x in nodes):
            nodes.append({"id":nid,"kind":kind,"key":str(key),"label":label,"meta":meta or {}})
        return nid

    def edge(a,b,rel):
        edges.append({"from":a,"to":b,"relation":rel})

    for _,r in m.iterrows():
        if pd.notna(r["Material"]):
            node("material",r["Material"],str(r["Material"]),{"lifecycle":r["Lifecycle Status"],"plant":r["Plant"]})
    for _,r in inv.iterrows():
        if pd.notna(r["Material"]):
            k=f'{r["Material"]}|{r["Plant"]}|{r["Storage Location"]}|{r["Batch"]}'
            node("inventory",k,f'Inventory {r["Material"]}',{"qty":r["Qty On Hand"]})
            if str(r["Material"]) in set(text(m["Material"])): edge(f'material:{r["Material"]}',f'inventory:{k}',"has inventory")
    for _,r in bins.iterrows():
        if pd.notna(r["Bin"]):
            node("bin",r["Bin"],str(r["Bin"]),{"capacity":r["Capacity"],"occupied":r["Occupied"]})
            if pd.notna(r["Assigned Material"]): edge(f'material:{r["Assigned Material"]}',f'bin:{r["Bin"]}',"stored in")
    for _,r in d.iterrows():
        if pd.notna(r["Delivery"]):
            node("delivery",r["Delivery"],str(r["Delivery"]),{"status":r["Status"],"qty":r["Order Qty"]})
            edge(f'material:{r["Material"]}',f'delivery:{r["Delivery"]}',"requested by")
    for _,r in po.iterrows():
        if pd.notna(r["Purchase Order"]):
            node("po",r["Purchase Order"],str(r["Purchase Order"]),{"status":r["PO Status"],"qty":r["PO Qty"]})
            edge(f'material:{r["Material"]}',f'po:{r["Purchase Order"]}',"replenished by")
            edge(f'vendor:{r["Vendor"]}',f'po:{r["Purchase Order"]}',"supplies")
    for _,r in v.iterrows():
        if pd.notna(r["Vendor"]):
            node("vendor",r["Vendor"],str(r["Vendor"]),{"name":r["Vendor Name"],"blocked":r["Procurement Block"]})
    return {"nodes":nodes,"edges":edges}

def _records(df, cols, n=15):
    if df.empty: return []
    cols=[c for c in cols if c in df.columns]
    return df[cols].head(n).to_dict("records")

def _impact(shortfall, demand, overdue, expired_qty, overcap_qty, lifecycle, vendor_block):
    score=0
    if demand>0: score += min(35, 35*max(shortfall,0)/demand)
    score += min(20, overdue*5)
    score += min(15, expired_qty/100)
    score += min(15, overcap_qty/100)
    if lifecycle in {"OBSOLETE","BLOCKED"}: score += 12
    if vendor_block: score += 8
    score=int(round(min(100,score)))
    sev="Critical" if score>=80 else "High" if score>=60 else "Medium" if score>=40 else "Low"
    return score, sev

def correlation_agent(data, dq, an):
    m, inv, bins, d, po, v = [data[x] for x in CORE_SHEETS]
    mats=set(text(inv["Material"])) | set(text(d["Material"])) | set(text(po["Material"])) | set(text(bins["Assigned Material"]))
    cases=[]

    for mat in sorted(x for x in mats if x):
        mm=m[text(m["Material"])==mat]
        iv=inv[text(inv["Material"])==mat]
        bb=bins[text(bins["Assigned Material"])==mat]
        dd=d[text(d["Material"])==mat]
        pp=po[text(po["Material"])==mat]
        if mm.empty and iv.empty and dd.empty and pp.empty and bb.empty: continue

        lifecycle = str(mm["Lifecycle Status"].iloc[0]) if not mm.empty else "UNKNOWN"
        oh=float(num(iv["Qty On Hand"]).sum()) if not iv.empty else 0
        blocked=float(num(iv["Blocked Qty"]).sum()) if not iv.empty else 0
        in_transit=float(num(iv["In-Transit Qty"]).sum()) if not iv.empty else 0
        available=oh-blocked
        active=dd[active_delivery(dd)] if not dd.empty else dd
        demand=float(num(active["Order Qty"]).sum()) if not active.empty else 0
        # Keep raw and derived inventory measures separate so downstream reasoning
        # can distinguish workbook facts from calculated operational measures.
        blocked_excess=max(0, blocked-oh)
        usable_available=max(0, available)
        shortage=max(0,demand-usable_available)
        planned=pd.to_datetime(active["Planned GI Date"],errors="coerce") if not active.empty else pd.Series(dtype="datetime64[ns]")
        overdue=int((planned<SNAPSHOT_DATE).sum()) if not active.empty else 0
        expired_mask=pd.to_datetime(iv["Batch Expiry"],errors="coerce")<SNAPSHOT_DATE if not iv.empty else pd.Series(dtype=bool)
        expired_qty=float(num(iv.loc[expired_mask,"Qty On Hand"]).sum()) if not iv.empty else 0
        overcap_qty=float((num(bb["Occupied"])-num(bb["Capacity"])).clip(lower=0).sum()) if not bb.empty else 0

        vendor_ids=set(text(pp["Vendor"])) if not pp.empty else set()
        vv=v[text(v["Vendor"]).isin(vendor_ids)] if vendor_ids else v.iloc[0:0]
        vendor_block=bool((text(vv["Procurement Block"]).str.upper().isin(["Y","YES","BLOCKED"])).any()) if not vv.empty else False

        reasons=[]
        signals=[]
        if lifecycle in {"OBSOLETE","BLOCKED"} and (len(iv)+len(dd)+len(pp)>0):
            reasons.append(f"{lifecycle} master status remains active downstream")
            signals.append("Lifecycle propagation failure")
        if demand>usable_available:
            reasons.append(f"active delivery demand of {demand:,.0f} exceeds usable available stock of {usable_available:,.0f} by {shortage:,.0f}")
            signals.append("Supply-demand shortage")
        if blocked_excess>0:
            reasons.append(f"blocked inventory quantity of {blocked:,.0f} exceeds physical on-hand of {oh:,.0f} by {blocked_excess:,.0f}, so usable available stock is {usable_available:,.0f}")
            signals.append("Inventory quantity integrity")
        if overdue:
            reasons.append(f"{overdue} active delivery record(s) are overdue")
            signals.append("Delivery execution risk")
        if expired_qty>0:
            reasons.append(f"{expired_qty:,.0f} units are in expired inventory records")
            signals.append("Expired stock")
        if overcap_qty>0:
            reasons.append(f"{overcap_qty:,.0f} units exceed warehouse-bin capacity")
            signals.append("Warehouse capacity risk")
        if vendor_block:
            reasons.append("an associated vendor is procurement-blocked while linked PO activity exists")
            signals.append("Vendor governance risk")

        if not reasons: continue

        score, sev=_impact(shortage,demand,overdue,expired_qty,overcap_qty,lifecycle,vendor_block)
        evidence={
            "Material_Master":_records(mm, list(mm.columns), 5),
            "Inventory_Stock":_records(iv, ["Material","Plant","Storage Location","Batch","Qty On Hand","Blocked Qty","In-Transit Qty","Batch Expiry","Last Movement Date"], 20),
            "Warehouse_Bin":_records(bb, ["Bin","Storage Type","Assigned Material","Capacity","Occupied","Bin Status","Plant"], 20),
            "Deliveries_Dispatch":_records(dd, ["Delivery","Material","Plant","Order Qty","Ship-To","Route","Planned GI Date","Status"], 20),
            "Purchase_Replenish":_records(pp, ["Purchase Order","Material","Vendor","Plant","PO Qty","Expected Delivery","PO Status"], 20),
            "Vendor_Master":_records(vv, list(vv.columns), 10),
        }

        linked=[]
        for df in [dq,an]:
            if not df.empty:
                linked += df[df["entity"].astype(str).str.split("|").apply(lambda xs: mat in xs)]["issue_id"].tolist()

        action=[]
        if lifecycle in {"OBSOLETE","BLOCKED"}: action.append("stop further procurement/dispatch and quarantine existing references")
        if shortage: action.append("re-plan allocation and validate/expedite inbound replenishment")
        if expired_qty: action.append("quarantine expired batches")
        if overcap_qty: action.append("rebalance the affected warehouse bins and verify physical quantity")
        if overdue: action.append("prioritize overdue deliveries after supply is confirmed")
        if vendor_block: action.append("hold PO execution until vendor status is resolved")
        recommended="; ".join(action).capitalize()+"."

        cases.append({
            "case_id":f"CASE-{len(cases)+1:04d}",
            "material":mat,
            "plant":mm["Plant"].iloc[0] if not mm.empty else (dd["Plant"].iloc[0] if not dd.empty else None),
            "severity":sev,
            "impact_score":score,
            "signals":signals,
            "root_cause":"; ".join(reasons)+".",
            "recommended_action":recommended,
            "linked_issue_ids":linked,
            "counts":{"inventory":len(iv),"bins":len(bb),"deliveries":len(dd),"purchase_orders":len(pp),"vendors":len(vv)},
            "metrics":{"on_hand":oh,"blocked":blocked,"available":usable_available,
                       "raw_available":available,"blocked_excess":blocked_excess,
                       "usable_available":usable_available,"in_transit":in_transit,
                       "demand":demand,"shortage":shortage,
                       "projected_available_after_inbound":usable_available+in_transit,
                       "projected_shortage_after_inbound":max(0,demand-(usable_available+in_transit)),
                       "overdue_deliveries":overdue,"expired_qty":expired_qty,
                       "overcapacity_qty":overcap_qty},
            "evidence":evidence
        })
    return pd.DataFrame(cases).sort_values(["impact_score","severity"],ascending=[False,True]).reset_index(drop=True)

def build_case_context(case: dict) -> str:
    import json
    return json.dumps(case, indent=2, default=str)

def run_pipeline(data):
    data=clean_data(data)
    graph=relationship_graph(data)
    dq=data_quality_agent(data)
    an=anomaly_agent(data)
    cases=correlation_agent(data,dq,an)
    return data, graph, dq, an, cases
