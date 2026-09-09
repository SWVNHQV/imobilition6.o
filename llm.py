from __future__ import annotations

import os
import json
import re
import streamlit as st


def _secret(name: str, default=None):
    """Read Streamlit Cloud Secrets first, then local environment variables."""
    try:
        value = st.secrets.get(name)
        if value not in (None, ""):
            return value
    except Exception:
        pass
    return os.getenv(name, default)


SYSTEM_PROMPT = """
You are the Root-Cause Analyst and Warehouse Copilot for a warehouse AI control tower.

You receive structured evidence generated from an Excel/SAP-style warehouse dataset.

Rules:
1. Use ONLY the supplied evidence.
2. Never invent quantities, IDs, dates, vendors, relationships, or business events.
3. Explicitly connect evidence across systems only when the supplied workbook evidence supports the relationship.
4. Distinguish observed facts from inference.
5. When explaining a finding, explain the exact finding first, then direct evidence, then related/correlated risks.
6. Keep exact workbook values, IDs, dates, quantities, and field names.
7. Treat the connected workbook records as the primary source of truth. Pre-computed metrics and root-cause text are supporting summaries, not substitutes for the records.
8. Separate: (a) confirmed facts directly observed in records, (b) deterministic calculations, (c) inferred root cause, and (d) contributing factors/symptoms.
9. Do not call a calculated negative "available stock" a physical stock quantity. If blocked quantity exceeds on-hand, describe the inconsistency and usable available stock separately.
10. Recommendations are proposals only. Never claim an action was executed.
11. If evidence is insufficient, say so.
12. Be concise but useful for an operations user.
"""


def enabled():
    return bool(_secret("OPENAI_API_KEY"))


def _client():
    from openai import OpenAI
    return OpenAI(api_key=_secret("OPENAI_API_KEY"))


def generate_root_cause(case: dict, model: str | None = None) -> str:
    if not enabled():
        return fallback_root_cause(case)

    model = model or _secret("OPENAI_MODEL", "gpt-4.1-mini")
    client = _client()

    prompt = f"""
Analyze this correlated warehouse case as a senior warehouse root-cause analyst.

The JSON contains both deterministic calculations and the underlying connected workbook records.
The six source sheets in `evidence` are the source of truth: Material_Master, Inventory_Stock,
Warehouse_Bin, Deliveries_Dispatch, Purchase_Replenish, and Vendor_Master.

{json.dumps(case, indent=2, default=str)}

Reasoning requirements:
1. Read the connected records across all available sheets before forming the root cause.
2. Reconcile the material, plant, vendor, delivery, PO and inventory relationships using only supplied keys.
3. Use deterministic metrics for arithmetic, but verify the meaning against the underlying records.
4. Do not simply repeat `root_cause`; independently explain why the evidence supports that conclusion.
5. Identify the primary root cause first, then contributing factors, then symptoms.
6. Never invent a record. If a sheet has zero linked records, say that it has no linked evidence.
7. Preserve exact IDs, quantities, dates, statuses, field names and values.
8. For inventory, distinguish physical on-hand, blocked quantity, usable available quantity, inbound quantity and shortage.

Write exactly these sections:
### Root Cause
### Evidence Chain
### Business Impact
### Recommended Action
### Confidence

In Evidence Chain, explicitly name the source sheet and the exact record/field values supporting each important conclusion.
"""

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=prompt
    )

    return response.output_text.strip()


def _load_copilot_workbook():
    """Load the complete six-sheet workbook so Copilot is never limited to a correlated case."""
    import pandas as pd

    candidates = [
        Path(__file__).with_name("Warehouse_AI_Hackathon_Synthetic_Dataset_FINAL 2.xlsx"),
        Path(__file__).with_name("Warehouse_AI_Hackathon_Synthetic_Dataset_FINAL_2.xlsx"),
    ]
    workbook = next((p for p in candidates if p.exists()), None)
    if workbook is None:
        return {}

    try:
        sheets = pd.read_excel(workbook, sheet_name=None)
        wanted = {
            "Material_Master", "Inventory_Stock", "Warehouse_Bin",
            "Deliveries_Dispatch", "Purchase_Replenish", "Vendor_Master"
        }
        return {k: v for k, v in sheets.items() if k in wanted}
    except Exception:
        return {}


def _is_general_copilot_question(question: str) -> bool:
    """Return True unless the operator explicitly asks for RCA/explanation of a finding/case."""
    qn = _norm(question)
    rca_terms = [
        "rootcause", "root cause", "whyisthisfinding", "explainthisfinding",
        "explainfinding", "explainanomaly", "explaincase", "explainthiscase",
        "whyisthisanomaly", "whyisthiscase", "whyflagged", "whywasthisflagged",
    ]
    return not any(term.replace(" ", "") in qn for term in rca_terms)


def copilot_answer(question: str, case: dict | None = None, model: str | None = None) -> str:
    """General-purpose Copilot entry point.

    IMPORTANT: this function intentionally loads the complete workbook.  The
    `case` argument is optional supporting context for an explicit RCA/finding
    question; it is NOT the primary evidence source for normal Copilot queries.
    This keeps questions like "how many expired inventory?" workbook-wide even
    when the UI happens to pass a selected finding/case.
    """
    workbook = _load_copilot_workbook()
    case = case or {}

    if not enabled():
        # Delegate to the workbook-aware deterministic engine whenever possible.
        try:
            import pandas as pd
            dq = pd.DataFrame(case.get("related_data_quality_findings", []))
            anomalies = pd.DataFrame(case.get("related_anomaly_findings", []))
            if workbook:
                return copilot_workbook_answer(question, dq, anomalies, workbook, model)
        except Exception:
            pass
        return fallback_copilot(question, case)

    model = model or _secret("OPENAI_MODEL", "gpt-4.1-mini")
    client = _client()

    workbook_records = {
        sheet: df.to_dict("records")
        for sheet, df in workbook.items()
    }

    explicit_rca = not _is_general_copilot_question(question)
    context = {
        "operator_question": question,
        "snapshot_date": "2026-09-05",
        "complete_workbook": workbook_records,
    }

    if explicit_rca and case:
        context["selected_case_or_finding_supporting_context"] = case

    prompt = f"""
You are the general-purpose Warehouse Control Tower Copilot.

Operator question:
{question}

Evidence:
{json.dumps(context, indent=2, default=str)}

PRIMARY RULE:
Answer the operator's actual question using the COMPLETE SIX-SHEET WORKBOOK
above. Never assume that the currently selected finding, anomaly, material, or
correlated case defines the scope of the question.

For normal/general questions, the workbook is the primary and authoritative
scope. The selected case/finding is only supporting context and must NOT narrow
the answer.

For an explicit RCA/finding/case explanation, you may use the selected case as
supporting context, but verify it against the complete workbook records.

You can answer questions about:
- Material_Master
- Inventory_Stock
- Warehouse_Bin
- Deliveries_Dispatch
- Purchase_Replenish
- Vendor_Master

Rules:
1. For counts, totals, averages, comparisons, rankings and date logic, calculate
   from the supplied workbook records.
2. For lists, show actual IDs/materials/vendors and exact workbook values.
3. Understand natural-language synonyms and case-insensitive field names.
4. If the question is workbook-wide, inspect ALL relevant rows.
5. If the question names a material/vendor/PO/delivery, find it in the workbook
   and connect related records across sheets using actual keys.
6. Do not use correlated-case evidence as a substitute for the workbook.
7. Never invent quantities, IDs, dates, statuses, relationships or events.
8. Preserve exact workbook values.
9. Distinguish confirmed facts, deterministic calculations and inference.
10. If a requested value is unavailable, say so rather than substituting a
    selected case's value.
11. Start with a direct answer. Use a compact table/list when useful.

Example:
If the operator asks "How many expired inventory?", calculate expiration across
ALL Inventory_Stock rows using Batch Expiry relative to the 2026-09-05 snapshot.
Do not answer from a selected material such as MAT-100056.
"""

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=prompt,
    )
    return response.output_text.strip()


# -------------------------------------------------------------------
# Generic helpers for workbook-aware Copilot
# -------------------------------------------------------------------

def _norm(value) -> str:
    """Case-insensitive, punctuation-insensitive matching."""
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _display(value):
    if value is None:
        return "blank"
    try:
        import pandas as pd
        if pd.isna(value):
            return "blank"
    except Exception:
        pass
    return str(value)


def _find_column(df, user_text):
    """Find a dataframe column regardless of capitalization/spaces/punctuation."""
    if df is None or getattr(df, "empty", False) and len(getattr(df, "columns", [])) == 0:
        return None

    target = _norm(user_text)

    for col in df.columns:
        if _norm(col) == target:
            return col

    # Partial matching for phrases such as 'base uom field'.
    for col in df.columns:
        ncol = _norm(col)
        if target and (target in ncol or ncol in target):
            return col

    return None


def _question_column_candidates(question, data):
    """
    Return actual workbook columns that appear relevant to the user's question.
    Matching is case-insensitive.
    """
    qn = _norm(question)
    matches = []

    for sheet, df in data.items():
        if df is None or not hasattr(df, "columns"):
            continue

        for col in df.columns:
            cn = _norm(col)
            if not cn:
                continue

            if cn in qn or cn.replace(" ", "") in qn:
                matches.append((sheet, col))

    # Common operator synonyms.
    synonyms = {
        "uom": ["Base UoM", "UoM"],
        "unit": ["Base UoM", "UoM", "Unit Price"],
        "group": ["Material Group"],
        "materialgroup": ["Material Group"],
        "type": ["Material Type"],
        "materialtype": ["Material Type"],
        "supplier": ["Vendor", "Vendor Name"],
        "vendor": ["Vendor", "Vendor Name"],
        "po": ["Purchase Order", "PO Status", "PO Qty"],
        "purchaseorder": ["Purchase Order"],
        "delivery": ["Delivery", "Order Qty", "Planned GI Date", "Status"],
        "route": ["Route"],
        "plant": ["Plant"],
        "country": ["Country"],
        "safetystock": ["Safety Stock"],
        "reorderpoint": ["Reorder Point"],
        "rop": ["Reorder Point"],
        "hazmat": ["Hazmat Flag"],
        "lifecycle": ["Lifecycle Status"],
    }

    for key, possible_cols in synonyms.items():
        if key in qn:
            for sheet, df in data.items():
                if df is None or not hasattr(df, "columns"):
                    continue
                for col in possible_cols:
                    actual = _find_column(df, col)
                    if actual is not None:
                        pair = (sheet, actual)
                        if pair not in matches:
                            matches.append(pair)

    return matches


def _extract_ids(question):
    return set(
        re.findall(
            r"\b[A-Z]{2,10}-\d{3,10}[A-Z]?\b",
            str(question).upper()
        )
    )


def _finding_evidence(row):
    ev = row.get("evidence", {})
    return ev if isinstance(ev, dict) else {}


def _finding_text(row):
    parts = [
        f"ID={row.get('issue_id', '')}",
        f"Severity={row.get('severity', '')}",
        f"Record={row.get('entity', '')}",
        f"Issue={row.get('title', '')}",
        f"Explanation={row.get('detail', '')}",
    ]

    ev = _finding_evidence(row)
    if ev:
        parts.append(
            "Actual values: " +
            " · ".join(
                f"{k}={_display(v)}"
                for k, v in ev.items()
            )
        )

    return "\n".join(parts)


def _rows_for_entity(data, entity):
    """Get connected workbook records for one or more material/vendor/delivery/PO IDs."""
    result = {}
    if not entity:
        return result

    entities = [x.strip() for x in str(entity).split("|") if x.strip()]
    for sheet, df in data.items():
        if df is None or not hasattr(df, "columns") or df.empty:
            continue

        masks = []
        if "Material" in df.columns:
            col = df["Material"].astype(str).str.strip().str.upper()
            wanted = {x.upper() for x in entities}
            masks.append(col.isin(wanted))
        if "Assigned Material" in df.columns:
            col = df["Assigned Material"].astype(str).str.strip().str.upper()
            wanted = {x.upper() for x in entities}
            masks.append(col.isin(wanted))
        if "Vendor" in df.columns:
            col = df["Vendor"].astype(str).str.strip().str.upper()
            wanted = {x.upper() for x in entities}
            masks.append(col.isin(wanted))
        if "Delivery" in df.columns:
            col = df["Delivery"].astype(str).str.strip().str.upper()
            wanted = {x.upper() for x in entities}
            masks.append(col.isin(wanted))
        if "Purchase Order" in df.columns:
            col = df["Purchase Order"].astype(str).str.strip().str.upper()
            wanted = {x.upper() for x in entities}
            masks.append(col.isin(wanted))

        if masks:
            mask = masks[0]
            for m in masks[1:]:
                mask = mask | m
            matched = df[mask]
            if not matched.empty:
                result[sheet] = matched.to_dict("records")

    return result


def _field_missing_findings(question, dq, data=None):
    """
    Find DQ findings related to a field, case-insensitively.
    Handles Base UoM, base uom, BASE UOM, etc.
    """
    if dq is None or dq.empty:
        return []

    qn = _norm(question)
    matches = []

    # Exact/semantic field aliases.
    aliases = {
        "baseuom": ["baseuom", "uom", "unitofmeasure"],
        "uom": ["baseuom", "uom", "unitofmeasure"],
        "materialgroup": ["materialgroup", "group"],
        "group": ["materialgroup"],
        "materialtype": ["materialtype", "type"],
        "type": ["materialtype"],
        "safetystock": ["safetystock"],
        "reorderpoint": ["reorderpoint", "rop"],
        "rop": ["reorderpoint", "rop"],
        "country": ["country", "vendorcountry"],
        "plant": ["plant"],
        "hazmat": ["hazmat", "hazmatflag"],
        "lifecycle": ["lifecycle", "lifecyclestatus"],
        "route": ["route"],
        "unitprice": ["unitprice"],
    }

    wanted = set()

    for key, vals in aliases.items():
        if key in qn:
            wanted.update(vals)

    # Future-proof behavior: if the workbook gains a new column that is not
    # in the alias dictionary, match the actual column name from the workbook.
    # Example: a future column named "Storage Zone" will work automatically.
    if data:
        for sheet, col in _question_column_candidates(question, data):
            wanted.add(_norm(col))

    for _, row in dq.iterrows():
        hay = _norm(
            " ".join(
                [
                    str(row.get("title", "")),
                    str(row.get("detail", "")),
                    json.dumps(row.get("evidence", {}), default=str),
                ]
            )
        )

        if wanted and any(w in hay for w in wanted):
            matches.append(row.to_dict())

    return matches


def _specific_finding(question, dq):
    """Find an exact DQ/AN ID from the user's question."""
    ids = _extract_ids(question)

    if not ids:
        return None

    # Search DQ first because DQ-xxxx should resolve to the DQ finding.
    if dq is not None and not dq.empty:
        for _, row in dq.iterrows():
            if str(row.get("issue_id", "")).upper() in ids:
                return row.to_dict()

    return None


def _format_workbook_records(records, max_rows=10):
    lines = []

    for sheet, rows in records.items():
        lines.append(f"### {sheet} ({len(rows)} linked rows)")

        for row in rows[:max_rows]:
            compact = " · ".join(
                f"{k}={_display(v)}"
                for k, v in row.items()
            )
            lines.append(f"- {compact}")

        if len(rows) > max_rows:
            lines.append(f"- ... {len(rows) - max_rows} more rows")

        lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------
# Workbook Copilot
# -------------------------------------------------------------------

def copilot_workbook_answer(question: str, dq, anomalies, data, model: str | None = None) -> str:
    """
    Workbook-aware Copilot.

    Supports:
    - exact DQ IDs such as DQ-0102
    - case-insensitive field questions such as Base UoM/base uom/BASE UOM
    - material/vendor/delivery/PO questions
    - broad workbook questions
    """

    import pandas as pd

    dq = dq.copy() if dq is not None else pd.DataFrame()
    anomalies = anomalies.copy() if anomalies is not None else pd.DataFrame()
    data = data or {}

    q = str(question).strip()
    qn = _norm(q)

    # ---------------------------------------------------------------
    # 1. Exact Data Quality finding: "Explain DQ-0102"
    # ---------------------------------------------------------------
    finding = _specific_finding(q, dq)

    if finding is not None:
        entity = str(finding.get("entity", ""))

        direct_records = _rows_for_entity(data, entity)

        # Related DQ findings for the same entity.
        related_dq = []
        if not dq.empty:
            for _, row in dq.iterrows():
                if (
                    str(row.get("issue_id", "")) != str(finding.get("issue_id", ""))
                    and entity
                    and entity in str(row.get("entity", ""))
                ):
                    related_dq.append(row.to_dict())

        # Related anomaly findings for the same entity.
        related_an = []
        if not anomalies.empty:
            for _, row in anomalies.iterrows():
                if entity and entity in str(row.get("entity", "")):
                    related_an.append(row.to_dict())

        context = {
            "question": q,
            "exact_finding": finding,
            "direct_workbook_records": direct_records,
            "related_data_quality_findings": related_dq,
            "related_anomaly_findings": related_an,
        }

        if not enabled():
            lines = [
                f"### {finding.get('issue_id')} — Detailed Explanation",
                "",
                f"**Severity:** {finding.get('severity')}",
                f"**Record:** {finding.get('entity')}",
                f"**Issue:** {finding.get('title')}",
                "",
                "### What the finding means",
                str(finding.get("detail", "")),
                "",
                "### Exact evidence",
            ]

            ev = _finding_evidence(finding)
            for k, v in ev.items():
                lines.append(f"- **{k}:** {_display(v)}")

            if direct_records:
                lines.extend(["", "### Direct workbook records"])
                lines.append(_format_workbook_records(direct_records, max_rows=5))

            if related_dq or related_an:
                lines.extend(["", "### Related findings"])
                for r in related_dq[:10]:
                    lines.append(
                        f"- {r.get('issue_id')} · {r.get('severity')} · "
                        f"{r.get('title')}"
                    )
                for r in related_an[:10]:
                    lines.append(
                        f"- {r.get('issue_id')} · {r.get('severity')} · "
                        f"{r.get('title')}"
                    )

            lines.extend(
                [
                    "",
                    "### Recommended next step",
                    "Review the direct workbook records above and resolve the exact data-quality condition before taking corrective action.",
                ]
            )

            return "\n".join(lines)

        model = model or _secret("OPENAI_MODEL", "gpt-4.1-mini")
        client = _client()

        prompt = f"""
Operator question:
{q}

The operator is asking about ONE SPECIFIC DATA QUALITY FINDING.

Evidence:
{json.dumps(context, indent=2, default=str)}

Answer with exactly these sections:

### What the finding means
Explain the exact DQ finding in plain operational language.

### Exact evidence
Use the exact values from the finding and workbook records.

### Why it matters
Explain the operational/business risk. Clearly distinguish confirmed facts from inference.

### Related findings
Only include related findings that are actually supplied. Do not mix them into the root cause of the exact DQ finding.

### Recommended next step
Give a practical review/remediation proposal. Do not claim execution.

Do not invent any information.
"""

        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=prompt
        )
        return response.output_text.strip()

    # ---------------------------------------------------------------
    # 2. Field-level question: "Base UoM", "base uom", "BASE UOM"
    # ---------------------------------------------------------------
    field_findings = _field_missing_findings(q, dq, data)

    if field_findings:
        context = {
            "question": q,
            "matched_field_findings": field_findings,
            "relevant_columns": _question_column_candidates(q, data),
        }

        if not enabled():
            lines = [
                "### Data Quality Field Investigation",
                "",
                f"**Question:** {q}",
                "",
                f"I found **{len(field_findings)}** data-quality finding(s) related to this field/topic.",
                "",
                "### Findings",
            ]

            for row in field_findings[:50]:
                lines.append(f"- **{row.get('issue_id')}** · {row.get('severity')} · {row.get('entity')} · {row.get('title')}")
                lines.append(f"  {row.get('detail')}")
                ev = _finding_evidence(row)
                if ev:
                    lines.append(
                        "  Actual: " +
                        " · ".join(
                            f"{k}={_display(v)}"
                            for k, v in ev.items()
                        )
                    )

            return "\n".join(lines)

        model = model or _secret("OPENAI_MODEL", "gpt-4.1-mini")
        client = _client()

        prompt = f"""
Operator question:
{q}

The operator is asking about a workbook field/topic.

Evidence:
{json.dumps(context, indent=2, default=str)}

Explain the field/topic using ONLY the evidence.

Treat field names case-insensitively and ignore spaces, punctuation and capitalization.
For example Base UoM, base uom and BASE UOM are the same field.
If the field exists in the workbook but is not in the built-in synonym list, use the actual workbook column name as the authority.

Show:
### Answer
### Actual findings
### What the field means operationally
### Recommended next step

Keep exact issue IDs, records and actual values.
Do not invent missing records.
"""

        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=prompt
        )
        return response.output_text.strip()

    # ---------------------------------------------------------------
    # 3. Material/entity investigation
    # ---------------------------------------------------------------
    ids = _extract_ids(q)

    material_id = None
    for identifier in ids:
        if identifier.startswith("MAT-"):
            material_id = identifier
            break

    if material_id:
        records = _rows_for_entity(data, material_id)

        related_dq = []
        related_an = []

        if not dq.empty:
            related_dq = [
                r.to_dict()
                for _, r in dq.iterrows()
                if material_id in str(r.get("entity", ""))
            ]

        if not anomalies.empty:
            related_an = [
                r.to_dict()
                for _, r in anomalies.iterrows()
                if material_id in str(r.get("entity", ""))
            ]

        context = {
            "question": q,
            "material": material_id,
            "workbook_records": records,
            "data_quality_findings": related_dq,
            "anomaly_findings": related_an,
        }

        if not enabled():
            lines = [
                f"### {material_id}",
                "",
                "### Connected workbook records",
                _format_workbook_records(records, max_rows=10)
                if records
                else "No connected workbook records found.",
                "",
                "### Data Quality findings",
            ]

            if related_dq:
                for r in related_dq:
                    lines.append(
                        f"- {r.get('issue_id')} · {r.get('severity')} · "
                        f"{r.get('title')} · {r.get('detail')}"
                    )
            else:
                lines.append("- No related Data Quality findings.")

            lines.extend(["", "### Anomaly findings"])

            if related_an:
                for r in related_an:
                    lines.append(
                        f"- {r.get('issue_id')} · {r.get('severity')} · "
                        f"{r.get('title')} · {r.get('detail')}"
                    )
            else:
                lines.append("- No related anomaly findings.")

            return "\n".join(lines)

        model = model or _secret("OPENAI_MODEL", "gpt-4.1-mini")
        client = _client()

        prompt = f"""
Operator question:
{q}

Material investigation:
{json.dumps(context, indent=2, default=str)}

Answer the operator using only the workbook evidence.

If they ask "what is this material?", provide a concise profile and connected operational records.
If they ask "what is the issue?", summarize all supplied DQ and anomaly findings.
If they ask "why is it short?", connect inventory, delivery demand and inbound evidence.
If they ask what to do, provide a recommendation based on the evidence.

Use exact values and IDs.
Do not invent information.
"""

        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=prompt
        )
        return response.output_text.strip()

    # ---------------------------------------------------------------
    # 4. Broad workbook question
    # ---------------------------------------------------------------

    dq_counts = {}
    if not dq.empty and "title" in dq.columns:
        dq_counts = dq["title"].value_counts().to_dict()

    an_counts = {}
    if not anomalies.empty and "title" in anomalies.columns:
        an_counts = anomalies["title"].value_counts().to_dict()

    missing_rows = []

    if not dq.empty and "title" in dq.columns:
        mask = dq["title"].astype(str).str.contains(
            "missing|orphan",
            case=False,
            regex=True,
            na=False
        )
        missing_rows = dq.loc[mask].to_dict("records")

    # ---------------------------------------------------------------
    # Deterministic workbook-wide inventory questions
    # ---------------------------------------------------------------
    # Counts/quantities must come from the workbook, not from an LLM
    # interpretation.  This prevents a broad question such as
    # "How many expired inventory?" from being answered using the
    # currently selected material/finding only.
    asks_expired = (
        "expired" in qn
        and any(term in qn for term in [
            "inventory", "stock", "quantity", "qty", "units",
            "howmany", "howmuch", "total", "list", "which"
        ])
    )

    if asks_expired and "expiry" not in qn:
        inv = data.get("Inventory_Stock")
        if inv is not None and not inv.empty and {"Material", "Plant", "Qty On Hand", "Batch Expiry"}.issubset(inv.columns):
            snapshot = pd.Timestamp("2026-09-05")
            expiry = pd.to_datetime(inv["Batch Expiry"], errors="coerce")
            qty = pd.to_numeric(inv["Qty On Hand"], errors="coerce").fillna(0)
            mask = expiry < snapshot
            # Match the anomaly rule: only expired stock with positive on-hand quantity.
            expired = inv.loc[mask & (qty > 0), ["Material", "Plant", "Qty On Hand", "Batch Expiry"]].copy()
            expired["Qty On Hand"] = pd.to_numeric(expired["Qty On Hand"], errors="coerce").fillna(0)
            expired = expired.sort_values("Batch Expiry")
            total_qty = int(expired["Qty On Hand"].sum())

            lines = [
                "### Answer",
                f"There are **{len(expired)} expired inventory records**, totaling **{total_qty:,} units** as of the **2026-09-05 snapshot**.",
                "",
                "### Expired inventory",
            ]
            for _, r in expired.iterrows():
                exp = pd.Timestamp(r["Batch Expiry"]).strftime("%Y-%m-%d")
                lines.append(
                    f"- **{r['Material']}** · Plant **{r['Plant']}** · **{int(r['Qty On Hand']):,} units** · expired **{exp}**"
                )
            lines.extend([
                "",
                "### Important",
                "This is a workbook-wide Copilot answer. It is not limited to the material or finding currently selected elsewhere in the app.",
            ])
            return "\n".join(lines)

    asks_missing = any(
        term in qn
        for term in [
            "missingdata",
            "missingfield",
            "missingfields",
            "blankdata",
            "incompletedata",
            "datamissing",
            "missinginformation",
        ]
    )

    if asks_missing:
        lines = [
            "### Answer",
            f"The Data Quality Agent found **{len(missing_rows)}** missing/orphan findings under the current validation rules.",
            "",
            "### Findings",
        ]

        for title, count in dq_counts.items():
            if "missing" in str(title).lower() or "orphan" in str(title).lower():
                lines.append(f"- **{title}: {count}**")

        lines.extend(["", "### Affected records"])

        for r in missing_rows[:50]:
            lines.append(
                f"- **{r.get('issue_id')}** · **{r.get('entity')}** · "
                f"{r.get('title')}"
            )

        return "\n".join(lines)

    # For a genuinely general Copilot question, provide the LLM with the
    # complete loaded workbook, not only the current selection or finding
    # summaries.  This lets Copilot answer questions such as:
    # - How many materials/vendors/deliveries/POs are there?
    # - Which vendors are blocked?
    # - What is the total stock?
    # - Which deliveries are overdue?
    # - Show records matching a material/plant/status/value.
    # - What are the biggest operational risks?
    # The deterministic agents still establish DQ/anomaly facts; the LLM
    # explains and answers the operator's natural-language question.
    full_workbook = {}
    for sheet_name, df in data.items():
        if df is None:
            continue
        full_workbook[sheet_name] = df.to_dict("records")

    context = {
        "question": q,
        "snapshot_date": "2026-09-05",
        "data_row_counts": {
            k: len(v) for k, v in data.items()
        },
        "data_quality_findings": dq.to_dict("records") if not dq.empty else [],
        "anomaly_summary": an_counts,
        "data_quality_summary": dq_counts,
        "full_workbook_records": full_workbook,
    }

    if not enabled():
        # Give a useful deterministic answer for common general questions
        # even when the OpenAI key is unavailable.  More complex natural
        # language questions still need the LLM.
        inventory = data.get("Inventory_Stock")
        deliveries = data.get("Deliveries_Dispatch")
        pos = data.get("Purchase_Replenish")
        materials = data.get("Material_Master")
        vendors = data.get("Vendor_Master")

        if any(term in qn for term in ["how many materials", "number of materials", "count of materials"]):
            return f"### Answer\nThere are **{len(materials) if materials is not None else 0} material master records** in the workbook."
        if any(term in qn for term in ["how many vendors", "number of vendors", "count of vendors"]):
            return f"### Answer\nThere are **{len(vendors) if vendors is not None else 0} vendor master records** in the workbook."
        if any(term in qn for term in ["how many deliveries", "number of deliveries", "count of deliveries"]):
            return f"### Answer\nThere are **{len(deliveries) if deliveries is not None else 0} delivery records** in the workbook."
        if any(term in qn for term in ["how many purchase orders", "how many pos", "number of purchase orders", "count of purchase orders"]):
            return f"### Answer\nThere are **{len(pos) if pos is not None else 0} purchase-order records** in the workbook."

        return (
            "### Answer\n"
            f"I checked the loaded workbook. The Data Quality Agent found **{len(dq)}** findings and the Anomaly Agent found **{len(anomalies)}** findings.\n\n"
            "For general natural-language questions, Copilot uses the complete six-sheet workbook as its evidence source. "
            "The OpenAI connection is currently unavailable, so I cannot generate the full natural-language answer for this question yet."
        )

    model = model or _secret("OPENAI_MODEL", "gpt-4.1-mini")
    client = _client()

    prompt = f"""
Operator question:
{q}

Complete workbook and control-tower evidence:
{json.dumps(context, indent=2, default=str)}

You are answering a general-purpose warehouse control-tower Copilot question.
Use the COMPLETE workbook records above as the primary source. Do not limit the
answer to the currently selected finding, material, case, or UI element.

You can answer questions about ANY of these six operational sheets:
Material_Master, Inventory_Stock, Warehouse_Bin, Deliveries_Dispatch,
Purchase_Replenish, Vendor_Master. Data_Dictionary may be used to explain fields.

Rules:
- Answer the actual question directly first.
- Treat field names case-insensitively and understand natural-language synonyms.
- For counts, totals, averages, comparisons, rankings, or date logic, calculate from the supplied workbook records.
- For lists, show actual record IDs/materials/vendors and actual values from the workbook.
- For questions about DQ/anomalies, use the deterministic findings supplied and distinguish confirmed facts from inference.
- If the operator asks a workbook-wide question, consider ALL relevant rows, not only the selected record.
- If the operator asks about a specific entity, connect relevant records across sheets when supported by keys.
- Preserve exact IDs, quantities, statuses, dates and field values.
- Never invent a record, value, date, relationship, or business rule.
- If the workbook does not contain enough evidence, say exactly what is missing.
- Keep the answer concise but useful, with a small table/list when that makes the answer clearer.
"""

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=prompt
    )

    return response.output_text.strip()


# -------------------------------------------------------------------
# Fallbacks
# -------------------------------------------------------------------

def fallback_root_cause(case):
    m = case.get("metrics", {})

    return f"""### Root Cause
{case.get("root_cause", "The correlated evidence indicates a cross-system operational issue.")}

### Evidence Chain
The case links Material Master, Inventory_Stock, Warehouse_Bin, Deliveries_Dispatch, Purchase_Replenish, and Vendor_Master using the material/plant/vendor relationships present in the workbook.

### Business Impact
Impact score: {case.get("impact_score", 0)}/100 ({case.get("severity", "Unknown")}). Usable available stock: {m.get("usable_available", m.get("available", 0)):,.0f}; physical on-hand: {m.get("on_hand", 0):,.0f}; blocked: {m.get("blocked", 0):,.0f}; active demand: {m.get("demand", 0):,.0f}; shortage: {m.get("shortage", 0):,.0f}; overdue deliveries: {m.get("overdue_deliveries", 0)}.

### Recommended Action
{case.get("recommended_action", "Review the linked records and correct the underlying issue.")}

### Confidence
High for the observed data relationships; narrative generation is using the deterministic evidence summary because no OpenAI API key is configured."""


def fallback_copilot(question, case):
    return f"""### Answer
{case.get("root_cause", "No correlated root cause was found.")}

### Why
The control tower linked evidence for material **{case.get("material")}** across Material Master, Inventory, Warehouse Bin, Deliveries, Purchase Replenishment and Vendor Master.

### Impact
**{case.get("severity")} — {case.get("impact_score")}/100**

### Next Step
{case.get("recommended_action", "Review the linked records before taking action.")}

*LLM is not enabled in this run; this is the evidence-grounded deterministic fallback.*"""
