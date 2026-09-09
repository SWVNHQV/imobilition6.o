
from __future__ import annotations
import os, json
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st

from agents import load_workbook, run_pipeline, SNAPSHOT_DATE
from llm import generate_root_cause, copilot_answer, copilot_workbook_answer, enabled

st.set_page_config(page_title="IntelliWarehouse AI Control Tower", page_icon="◈", layout="wide")

st.markdown("""
<style>
.stApp{background:#f5f7fb}
.block-container{max-width:1500px;padding-top:1.2rem}
.hero{background:linear-gradient(135deg,#0b1f44,#234a91);color:white;border-radius:24px;padding:28px 32px;margin-bottom:18px}
.hero h1{font-size:2.3rem;margin:0}.hero p{opacity:.85;margin:.35rem 0 0}
.card{background:white;border:1px solid #e4e8ef;border-radius:18px;padding:18px;box-shadow:0 5px 20px rgba(15,30,60,.05)}
.kpi{font-size:1.75rem;font-weight:800}.muted{color:#697386;font-size:.86rem}
.chain{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:12px 0}
.node{background:white;border:1px solid #dfe4ec;border-radius:10px;padding:9px 12px;font-weight:700}
.arrow{color:#8290a5}
.ai{background:#f5f1ff;border:1px solid #ddd2ff;border-radius:16px;padding:18px}
.good{background:#eefaf2;border:1px solid #ccebd7;border-radius:14px;padding:14px}
.warn{background:#fff8e8;border:1px solid #f2dfae;border-radius:14px;padding:14px}
</style>
""", unsafe_allow_html=True)

if "actions" not in st.session_state: st.session_state.actions={}
if "audit" not in st.session_state: st.session_state.audit=[]
if "ai_cache" not in st.session_state: st.session_state.ai_cache={}

st.markdown("""
<div class="hero">
<h1>◈ IntelliWarehouse AI Control Tower</h1>
<p>Detect → Correlate → Explain → Impact → Approve</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Control Center")
    default_path = Path(__file__).parent / "Warehouse_AI_Hackathon_Synthetic_Dataset_FINAL_2.xlsx"
    uploaded=st.file_uploader("Upload warehouse workbook",type=["xlsx"])
    path=uploaded if uploaded is not None else default_path
    st.caption("Snapshot: 05 Sep 2026")
    model_name = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
    if enabled():
        st.success(f"LLM enabled · {model_name}")
    else:
        st.warning("LLM not enabled — deterministic evidence-grounded fallback is active.")
        st.caption("Create a file named .env beside app.py with OPENAI_API_KEY=your_key, then restart Streamlit.")
    st.divider()
    st.caption("Governance")
    st.caption("Human approval required · Simulated actions · Audit retained")

try:
    raw=load_workbook(path)
    data, graph, dq, anomalies, cases=run_pipeline(raw)# Initialize approval queue from current RCA cases
    current_case_ids = set(cases["case_id"].astype(str)) if not cases.empty else set()

    # Remove approval states for cases no longer in the current workbook
    for cid in list(st.session_state.actions.keys()):
      if cid not in current_case_ids:
        del st.session_state.actions[cid]

    # Add every RCA case as Pending unless a human already decided
    for _, case in cases.iterrows():
      cid = str(case["case_id"])
      if cid not in st.session_state.actions:
        st.session_state.actions[cid] = {
            "status": "Pending",
            "approver": "",
            "note": "",
            "action": case["recommended_action"],
        }
except Exception as e:
    st.error(f"Could not load workbook: {e}")
    st.stop()

def evidence_text(e):
    if not isinstance(e, dict):
        return str(e)
    parts=[]
    for k,v in e.items():
        if isinstance(v, (list,tuple)):
            val=", ".join(map(str,v))
        elif v is None or (not isinstance(v, dict) and pd.isna(v)):
            val="blank"
        else:
            val=str(v)
        parts.append(f"{k}={val}")
    return " · ".join(parts)

def build_finding_context(finding, data, dq, anomalies):
    """Build exact evidence for one DQ/anomaly finding for Copilot."""
    f = finding.to_dict() if hasattr(finding, "to_dict") else dict(finding)
    entity = str(f.get("entity", "")).strip()
    evidence = f.get("evidence", {}) if isinstance(f.get("evidence"), dict) else {}
    import re

    material = None
    if entity.upper().startswith("MAT-"):
        material = entity.split("|")[0].strip()
    elif evidence.get("Material"):
        material = str(evidence["Material"]).strip()
    else:
        ids = re.findall(r"MAT-\d+[A-Z]?", entity.upper())
        if ids:
            material = ids[0]

    connected = {}
    if material:
        for sheet, col in [
            ("Material_Master", "Material"),
            ("Inventory_Stock", "Material"),
            ("Warehouse_Bin", "Assigned Material"),
            ("Deliveries_Dispatch", "Material"),
            ("Purchase_Replenish", "Material"),
        ]:
            df = data.get(sheet, pd.DataFrame())
            if not df.empty and col in df.columns:
                connected[sheet] = df[df[col].astype(str).eq(material)].head(25).to_dict("records")
            else:
                connected[sheet] = []

        po_rows = pd.DataFrame(connected["Purchase_Replenish"])
        vdf = data.get("Vendor_Master", pd.DataFrame())
        if not po_rows.empty and "Vendor" in po_rows.columns and not vdf.empty and "Vendor" in vdf.columns:
            vendors = set(po_rows["Vendor"].astype(str))
            connected["Vendor_Master"] = vdf[vdf["Vendor"].astype(str).isin(vendors)].head(10).to_dict("records")
        else:
            connected["Vendor_Master"] = []
    else:
        connected["Direct Evidence"] = [evidence]

    related = []
    for df in [dq, anomalies]:
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                if str(r.get("issue_id", "")) == str(f.get("issue_id", "")):
                    continue
                if material and material in str(r.get("entity", "")).split("|"):
                    related.append({
                        "issue_id": r.get("issue_id"),
                        "severity": r.get("severity"),
                        "title": r.get("title"),
                        "detail": r.get("detail"),
                        "evidence": r.get("evidence"),
                    })

    return {
        "finding_type": "Data Quality" if str(f.get("issue_id", "")).startswith("DQ-") else "Anomaly",
        "issue_id": f.get("issue_id"),
        "severity": f.get("severity"),
        "entity": entity,
        "title": f.get("title"),
        "detail": f.get("detail"),
        "exact_finding_evidence": evidence,
        "material": material,
        "connected_workbook_records": connected,
        "related_findings": related[:30],
        "root_cause": f.get("detail"),
        "impact_score": 0,
        "recommended_action": "Review the exact finding and connected operational records before corrective action.",
    }

# KPI bar
k=st.columns(6)
k[0].metric("Materials",len(data["Material_Master"]))
k[1].metric("Inventory",len(data["Inventory_Stock"]))
k[2].metric("Deliveries",len(data["Deliveries_Dispatch"]))
k[3].metric("POs",len(data["Purchase_Replenish"]))
k[4].metric("Findings",len(dq)+len(anomalies))
k[5].metric("Correlated cases",len(cases))

tabs=st.tabs(["Control Tower","Root Cause AI","Trace Graph","Approvals","Copilot","Data Explorer","Audit"])

with tabs[0]:
    st.subheader("Prioritized operational worklist")
    st.caption("Start here: review Critical/High findings, open Root Cause AI, then approve the proposed fix.")

    # Fixed-scope coverage: bad/missing master data and inventory/process anomalies.
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Data quality", len(dq))
    c2.metric("Process anomalies", len(anomalies))
    c3.metric("Root-cause cases", len(cases))
    pending = sum(1 for v in st.session_state.actions.values() if v.get("status") == "Pending")
    c4.metric("Pending approval", pending)

    st.markdown("### Data Quality")
    if dq.empty:
        st.success("No data-quality findings.")
    else:
        dq_view = dq[["issue_id","severity","entity","title","detail","evidence"]].copy()
        dq_view["evidence"] = dq_view["evidence"].apply(evidence_text)
        dq_view.columns = ["ID","Severity","Record","Issue","Explanation","Actual values"]
        st.dataframe(dq_view, width="stretch", hide_index=True)
        st.download_button(
            "Export data-quality findings",
            dq.to_csv(index=False).encode("utf-8"),
            "nexuschain_data_quality_findings.csv",
            "text/csv"
        )

    st.markdown("### Explain a Data Quality Finding")
    dq_ids = dq["issue_id"].astype(str).tolist()
    dq_choice = st.selectbox(
        "Select a finding to investigate",
        dq_ids,
        format_func=lambda x: (
            f"{x} · "
            f"{dq.loc[dq['issue_id'].astype(str).eq(x), 'severity'].iloc[0]} · "
            f"{dq.loc[dq['issue_id'].astype(str).eq(x), 'entity'].iloc[0]} · "
            f"{dq.loc[dq['issue_id'].astype(str).eq(x), 'title'].iloc[0]}"
        ),
        key="dq_explain_choice"
    )
    if st.button("🔎 Explain selected finding with Copilot", type="primary", key="explain_dq"):
        selected_finding = dq[dq["issue_id"].astype(str).eq(str(dq_choice))].iloc[0]
        finding_case = build_finding_context(selected_finding, data, dq, anomalies)
        with st.spinner("Copilot is checking the exact finding and connected workbook records..."):
            st.markdown(copilot_answer(
                f"Explain {dq_choice} in detail. Start with the exact finding, then explain the direct evidence, why it matters, related findings, and the safest next step. Do not mix related findings into the exact finding.",
                finding_case
            ))

    st.markdown("### Inventory & Process Anomalies")
    if anomalies.empty:
        st.success("No inventory/process anomalies.")
    else:
        an_view = anomalies[["issue_id","severity","entity","title","detail","evidence"]].copy()
        an_view["evidence"] = an_view["evidence"].apply(evidence_text)
        an_view.columns = ["ID","Severity","Record","Issue","Explanation","Actual values"]
        st.dataframe(an_view,width="stretch", hide_index=True)
        st.download_button(
            "Export anomaly findings",
            anomalies.to_csv(index=False).encode("utf-8"),
            "nexuschain_anomaly_findings.csv",
            "text/csv"
        )

    st.markdown("### Correlated root causes")
    if cases.empty:
        st.info("No cross-system root-cause cases detected.")
    else:
        df=cases[["case_id","material","severity","impact_score","signals","root_cause","recommended_action"]].copy()
        df["signals"]=df["signals"].apply(lambda x:", ".join(x))
        df.columns=["Case","Material","Severity","Impact","Signals","Root cause","Recommended fix"]
        st.dataframe(df,width="stretch",hide_index=True)
        st.download_button(
            "Export detected issues + proposed fixes",
            df.to_csv(index=False).encode("utf-8"),
            "nexuschain_detected_issues_and_fixes.csv",
            "text/csv"
        )

with tabs[1]:
    st.subheader("AI Root Cause Analysis")
    st.caption("Cross-system evidence → root cause → impact → recommended corrective action")
    if cases.empty:
        st.info("No cases available.")
    else:
        labels=[f"{r.case_id} · {r.material} · {r.severity} · {r.impact_score}/100" for _,r in cases.iterrows()]
        idx=st.selectbox("Choose a correlated case",range(len(labels)),format_func=lambda i:labels[i])
        case=cases.iloc[idx].to_dict()
        st.markdown(f"### {case['case_id']} — {case['material']}")
        st.markdown(f"**{case['severity']} · Impact {case['impact_score']}/100**")
        st.markdown("<div class='chain'>"+
                    "<span class='node'>Material Master</span><span class='arrow'>→</span>"+
                    "<span class='node'>Inventory</span><span class='arrow'>→</span>"+
                    "<span class='node'>Warehouse Bin</span><span class='arrow'>→</span>"+
                    "<span class='node'>Delivery</span><span class='arrow'>→</span>"+
                    "<span class='node'>Purchase Order</span><span class='arrow'>→</span>"+
                    "<span class='node'>Vendor</span><span class='arrow'>→</span>"+
                    "<span class='node'>Root Cause</span></div>",unsafe_allow_html=True)

        st.markdown(f"<div class='ai'><b>Evidence-grounded finding</b><br>{case['root_cause']}</div>",unsafe_allow_html=True)
        if st.button("Generate AI Root Cause Explanation",type="primary"):
            with st.spinner("AI is synthesizing the correlated evidence..."):
                st.session_state.ai_cache[case["case_id"]]=generate_root_cause(case)
        if case["case_id"] in st.session_state.ai_cache:
            st.markdown(st.session_state.ai_cache[case["case_id"]])
        else:
            st.caption("Click the button to have the LLM write the operator-facing explanation from the structured evidence.")

        st.subheader("Evidence from every connected sheet")
        for sheet, records in case["evidence"].items():
            with st.expander(f"{sheet} · {len(records)} linked records"):
                st.dataframe(pd.DataFrame(records),width="stretch",hide_index=True)

        st.markdown(f"<div class='good'><b>Proposed action:</b> {case['recommended_action']}</div>",unsafe_allow_html=True)

with tabs[2]:
    st.subheader("Relationship Trace Graph")
    st.caption("Follow one material across the six operational sheets. Relationships are built from workbook keys.")
    if cases.empty:
        st.info("No correlated cases available.")
    else:
        mat_options=cases["material"].tolist()
        selected=st.selectbox("Material to trace",mat_options,format_func=lambda x: f"{x} · {next((r.severity for _,r in cases.iterrows() if r.material==x), '')}")
        mm=data["Material_Master"]; iv=data["Inventory_Stock"]; bb=data["Warehouse_Bin"]; dd=data["Deliveries_Dispatch"]; pp=data["Purchase_Replenish"]; vv=data["Vendor_Master"]
        mm1 = mm[mm["Material"].astype(str) == str(selected)]
        iv1=iv[iv["Material"].astype(str)==str(selected)]
        bb1=bb[bb["Assigned Material"].astype(str)==str(selected)]
        dd1=dd[dd["Material"].astype(str)==str(selected)]
        pp1=pp[pp["Material"].astype(str)==str(selected)]
        vendors=set(pp1["Vendor"].astype(str)) if not pp1.empty else set()
        vv1=vv[vv["Vendor"].astype(str).isin(vendors)]
        st.markdown(f"<div class='chain'><span class='node'>Material Master<br><small>{len(mm1)} row</small></span><span class='arrow'>→</span><span class='node'>Inventory<br><small>{len(iv1)} rows</small></span><span class='arrow'>→</span><span class='node'>Warehouse Bin<br><small>{len(bb1)} rows</small></span><span class='arrow'>→</span><span class='node'>Deliveries<br><small>{len(dd1)} rows</small></span><span class='arrow'>→</span><span class='node'>Purchase Orders<br><small>{len(pp1)} rows</small></span><span class='arrow'>→</span><span class='node'>Vendor<br><small>{len(vv1)} rows</small></span></div>",unsafe_allow_html=True)
        st.markdown("### How the records are joined")
        join_df=pd.DataFrame([
            ["Material_Master ↔ Inventory_Stock","Material + Plant","Compare lifecycle/master data with stock"],
            ["Material_Master ↔ Deliveries_Dispatch","Material + Plant","Compare demand with available stock"],
            ["Material_Master ↔ Purchase_Replenish","Material + Plant","Check replenishment and PO status"],
            ["Material_Master ↔ Warehouse_Bin","Assigned Material + Plant/location","Check storage and capacity"],
            ["Purchase_Replenish ↔ Vendor_Master","Vendor","Check supplier governance"],
            ["Inventory_Stock ↔ Deliveries_Dispatch","Material + Plant","Demand vs available stock"],
        ],columns=["Sheets","Business key","Why it is correlated"])
        st.dataframe(join_df,width="stretch",hide_index=True)
        st.markdown("### Connected evidence for this material")
        for title,df,cols in [
            ("Material Master",mm1,list(mm.columns)),
            ("Inventory",iv1,["Material","Plant","Storage Location","Batch","Qty On Hand","Blocked Qty","In-Transit Qty","Batch Expiry","Last Movement Date"]),
            ("Warehouse Bins",bb1,["Bin","Plant","Storage Type","Capacity","Occupied","Bin Status"]),
            ("Deliveries",dd1,["Delivery","Plant","Order Qty","Ship-To","Route","Planned GI Date","Status"]),
            ("Purchase Orders",pp1,["Purchase Order","Plant","Vendor","PO Qty","Expected Delivery","PO Status"]),
            ("Vendor Master",vv1,list(vv.columns)),
        ]:
            cols=[c for c in cols if c in df.columns]
            with st.expander(f"{title} · {len(df)} linked rows"):
                st.dataframe(df[cols],width="stretch",hide_index=True)

with tabs[3]:
    st.subheader("Human approval gate")
    st.caption("The Action Agent proposes. A human decides. The app only simulates execution.")
    if cases.empty: st.info("No actions.")
    for _,case in cases.iterrows():
        cid=case["case_id"]
        state=st.session_state.actions.get(cid,{"status":"Pending","approver":"","note":"","action":case["recommended_action"]})
        with st.expander(f"{cid} · {case['material']} · {case['severity']} · {case['impact_score']}/100"):
            st.write(case["root_cause"])
            action=st.text_area("Proposed action",state["action"],key=f"action_{cid}")
            approver=st.text_input("Approver name / role",state["approver"],key=f"approver_{cid}")
            note=st.text_area("Decision note",state["note"],key=f"note_{cid}")
            x,y,z=st.columns(3)
            if x.button("Approve",key=f"approve_{cid}"):
                if not approver.strip():
                    st.error("Approver is required.")
                else:
                    now=datetime.now().isoformat(timespec="seconds")
                    st.session_state.actions[cid]={"status":"Approved","approver":approver,"note":note,"action":action}
                    st.session_state.audit.append({"timestamp":now,"case":cid,"status":"Approved","agent":"Action Agent","approver":approver,"what":action,"why":case["root_cause"]})
                    st.rerun()
            if y.button("Simulate Execute",key=f"simulate_{cid}"):
                if not approver.strip():
                    st.error("Approver is required for simulation.")
                else:
                    now=datetime.now().isoformat(timespec="seconds")
                    st.session_state.actions[cid]={"status":"Simulated","approver":approver,"note":note,"action":action}
                    st.session_state.audit.append({"timestamp":now,"case":cid,"status":"Simulated","agent":"Action Agent","approver":approver,"what":action,"why":case["root_cause"]})
                    st.rerun()
            if z.button("Reject",key=f"reject_{cid}"):
                now=datetime.now().isoformat(timespec="seconds")
                st.session_state.actions[cid]={"status":"Rejected","approver":approver or "Operator","note":note,"action":action}
                st.session_state.audit.append({"timestamp":now,"case":cid,"status":"Rejected","agent":"Action Agent","approver":approver or "Operator","what":action,"why":case["root_cause"]})
                st.rerun()
            st.write(f"**Current status:** {state['status']}")

with tabs[4]:
    st.subheader("AI Warehouse Copilot")
    st.caption("Ask about any finding, material, delivery, PO, vendor, or workbook-wide issue.")
    q=st.text_input(
        "Ask the control tower",
        placeholder="Explain DQ-0102 in detail  •  Why is MAT-100030 blocked?  •  Why is DLV-800011 overdue?"
    )
    if q:
        import re
        broad_terms = [
            "missing", "data quality", "expired", "stale", "overdue", "shortage",
            "anomal", "issue", "problem", "blocked", "obsolete", "capacity", "vendor"
        ]
        ids=set(re.findall(r"[A-Z]{2,12}-\d{4,8}[A-Z]?",q.upper()))

        # Case-insensitive field/column understanding. The operator can type
        # "Base UoM", "base uom", "BASE UOM", etc. and Copilot will find
        # the matching workbook column/findings without requiring an issue ID.
        def _norm(s):
            return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()

        q_norm = _norm(q)
        column_matches = []
        for sheet_name, df in data.items():
            if df is None or df.empty:
                continue
            for col in df.columns:
                cn = _norm(col)
                if cn and (cn == q_norm or cn in q_norm or q_norm in cn):
                    column_matches.append((sheet_name, col))

        # If the question names a known column/field, focus on that field first.
        # This works even when the wording differs only by capitalization.
        field_findings = []
        for df_name, df in [("Data Quality", dq), ("Anomalies", anomalies)]:
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                hay = " ".join([
                    str(r.get("title", "")),
                    str(r.get("detail", "")),
                    str(r.get("evidence", "")),
                ])
                if any(_norm(col) and _norm(col) in _norm(hay) for _, col in column_matches):
                    field_findings.append(r)

        field_handled = False
        if not ids and field_findings:
            field_handled = True
            # Build an evidence-grounded answer from the exact matching field.
            rows = []
            for r in field_findings[:50]:
                rows.append({
                    "ID": r.get("issue_id"),
                    "Severity": r.get("severity"),
                    "Record": r.get("entity"),
                    "Issue": r.get("title"),
                    "Explanation": r.get("detail"),
                    "Actual values": r.get("evidence"),
                })

            matched_fields = ", ".join(f"{sheet}.{col}" for sheet, col in column_matches[:10])
            st.markdown(f"### Field investigation: {matched_fields}")
            st.caption("Case-insensitive match — capitalization does not matter.")
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            if st.button("🤖 Explain these findings with Copilot", key="explain_field_findings"):
                synthetic = {
                    "finding_type": "Field investigation",
                    "issue_id": ", ".join(str(r.get("issue_id")) for r in field_findings[:20]),
                    "severity": ", ".join(sorted(set(str(r.get("severity")) for r in field_findings[:20]))),
                    "entity": ", ".join(str(r.get("entity")) for r in field_findings[:20]),
                    "title": f"Findings related to field(s): {matched_fields}",
                    "detail": "The operator asked about a workbook field without specifying an issue ID.",
                    "exact_finding_evidence": rows,
                    "material": None,
                    "connected_workbook_records": {
                        sheet: data[sheet][[col]].head(100).to_dict("records")
                        for sheet, col in column_matches[:10]
                        if sheet in data and col in data[sheet].columns
                    },
                    "related_findings": rows,
                }
                with st.spinner("Copilot is explaining the matching field findings..."):
                    st.markdown(copilot_answer(q, synthetic))
        # Exact DQ-/AN- finding IDs and case/material questions are handled
        # only when a field-specific query was not already handled above.
        if not field_handled:
            finding_hit = None
            for df in [dq, anomalies]:
                if df is not None and not df.empty:
                    for ident in ids:
                        rows = df[df["issue_id"].astype(str).str.upper().eq(ident)]
                        if not rows.empty:
                            finding_hit = rows.iloc[0]
                            break
                if finding_hit is not None:
                    break

            if finding_hit is not None:
                finding_case = build_finding_context(finding_hit, data, dq, anomalies)
                with st.spinner("Copilot is checking the exact finding and connected workbook records..."):
                    st.markdown(copilot_answer(q, finding_case))
            else:
                hit = None
                for _, r in cases.iterrows():
                    hay = json.dumps(r.to_dict(), default=str).upper()
                    if any(i in hay for i in ids):
                        hit = r.to_dict()
                        break
                if hit is None and cases.shape[0]:
                    words = [w for w in re.findall(r"[A-Z0-9-]{5,}", q.upper())]
                    for _, r in cases.iterrows():
                        if any(w in json.dumps(r.to_dict(), default=str).upper() for w in words):
                            hit = r.to_dict()
                            break
                if hit:
                    with st.spinner("Analyzing correlated evidence..."):
                        st.markdown(copilot_answer(q, hit))
                else:
                    with st.spinner("Checking the entire workbook..."):
                        st.markdown(copilot_workbook_answer(q, dq, anomalies, data))

with tabs[5]:
    st.subheader("Data Explorer")
    visible_sheets=[s for s in data.keys() if s not in {"README","Data_Dictionary"}]
    sheet=st.selectbox("Sheet",visible_sheets)
    st.dataframe(data[sheet],width="stretch",hide_index=True)

with tabs[6]:
    st.subheader("Audit Trail")
    if st.session_state.audit:
        st.dataframe(pd.DataFrame(st.session_state.audit),width="stretch",hide_index=True)
    else:
        st.info("No human decisions recorded in this session.")
