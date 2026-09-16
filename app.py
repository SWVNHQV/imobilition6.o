
from __future__ import annotations
import os, json
import base64
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st

from agents import load_workbook, run_pipeline, SNAPSHOT_DATE
from llm import generate_root_cause, copilot_answer, copilot_workbook_answer, enabled

st.set_page_config(page_title="IntelliWarehouse AI", page_icon="◈", layout="wide")

# Warehouse background image hosted on Vecteezy.
# Using the public image URL keeps the repository free of image assets.
BG_URL = "https://static.vecteezy.com/system/resources/previews/030/592/227/large_2x/retail-warehouse-full-of-shelves-with-goods-in-cardboard-boxes-and-packages-logistics-sorting-and-distribution-facility-for-product-delivery-generative-ai-photo.jpeg"

bg_layer = (
    "linear-gradient(rgba(238,244,250,.76),rgba(238,244,250,.76)), "
    f"url('{BG_URL}')"
)

# -------------------------------------------------------------------
# HCI-first visual system
# - Visibility: high contrast and clear hierarchy
# - Recognition: icons + labels in navigation
# - Consistency: reusable card/pill/button patterns
# - Feedback: clear active/hover states
# - Aesthetics: soft warehouse background with readable surfaces
# -------------------------------------------------------------------
st.markdown("""
<style>
:root{
    --navy:#14395f;
    --blue:#1769b0;
    --ink:#233952;
    --muted:#66788f;
    --line:#d8e2ed;
    --panel:rgba(255,255,255,.94);
    --panel-soft:rgba(248,251,255,.90);
}

html, body, [class*="css"]{
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

/* Background: visible, but subordinate to information */
.stApp{
    background:
        linear-gradient(rgba(238,244,249,.86),rgba(238,244,249,.86)),
        url('https://static.vecteezy.com/system/resources/previews/030/592/227/large_2x/retail-warehouse-full-of-shelves-with-goods-in-cardboard-boxes-and-packages-logistics-sorting-and-distribution-facility-for-product-delivery-generative-ai-photo.jpeg')
        center center / cover fixed no-repeat !important;
}
[data-testid="stAppViewContainer"]{
    background:transparent !important;
}
[data-testid="stHeader"]{
    background:rgba(255,255,255,.88) !important;
}
.block-container{
    max-width:1320px !important;
    padding-top:1.15rem !important;
    padding-bottom:2.4rem !important;
}

/* Sidebar */
section[data-testid="stSidebar"]{
    background:rgba(241,246,251,.97) !important;
    border-right:1px solid #d6e1ec !important;
}
section[data-testid="stSidebar"] .block-container{
    padding:1.2rem 1rem 1.5rem !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3{
    color:var(--navy) !important;
    font-weight:800 !important;
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] .stCaption{
    color:#5e728a !important;
}
section[data-testid="stSidebar"] .stDivider{
    border-color:#ccd9e6 !important;
}

/* Hero */
.hero{
    background:linear-gradient(135deg,#0b2a50 0%,#174a86 58%,#2a67ad 100%);
    color:#fff !important;
    border-radius:24px;
    padding:28px 34px 24px;
    margin:0 0 14px;
    box-shadow:0 16px 34px rgba(20,52,88,.18);
}
.hero h1{
    color:#fff !important;
    font-size:2.35rem !important;
    line-height:1.08 !important;
    margin:0 !important;
    font-weight:850 !important;
    letter-spacing:-.035em !important;
}
.hero p{
    color:#e8f1fb !important;
    font-size:1rem !important;
    line-height:1.45 !important;
    margin:.65rem 0 0 !important;
    font-weight:600 !important;
}


.sidebar-group{
    color:#74869b;
    font-size:.67rem;
    letter-spacing:.09em;
    font-weight:850;
    margin:.05rem 0 .35rem;
}
.sidebar-group-label{
    color:#4f6f92;
    font-size:.64rem;
    letter-spacing:.10em;
    font-weight:850;
    margin:.6rem 0 .35rem .15rem;
}

/* ===== Sidebar workspace navigation ===== */
.page-kicker{
    font-size:.72rem;
    font-weight:850;
    letter-spacing:.08em;
    color:#70839a;
    text-transform:uppercase;
    margin:.2rem 0 .15rem;
}
.page-hint{
    color:#6e8096;
    font-size:.86rem;
    margin:0 0 10px;
}
.brand{
    display:flex;
    align-items:center;
    gap:10px;
    padding:2px 0 16px;
}
.brand-mark{
    width:38px;
    height:38px;
    border-radius:11px;
    display:flex;
    align-items:center;
    justify-content:center;
    color:#fff;
    background:linear-gradient(135deg,#1c72c3,#3da9dc);
    font-size:22px;
    box-shadow:0 5px 14px rgba(22,91,145,.18);
}
.brand-title{
    color:#12365f;
    font-weight:850;
    font-size:1rem;
}
.brand-subtitle{
    color:#72849a;
    font-size:.69rem;
    margin-top:2px;
}
.sidebar-section-title{
    color:#74869b;
    font-size:.68rem;
    letter-spacing:.09em;
    font-weight:850;
    margin:.85rem 0 .45rem;
}
section[data-testid="stSidebar"] [data-testid="stRadio"]{
    background:rgba(255,255,255,.58);
    border:1px solid #d9e4ee;
    border-radius:14px;
    padding:6px;
    box-shadow:0 4px 12px rgba(20,52,88,.05);
}
section[data-testid="stSidebar"] [data-testid="stRadio"] > label{
    display:none !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"]{
    gap:2px !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label{
    min-height:40px !important;
    padding:8px 9px !important;
    margin:0 !important;
    border-radius:9px !important;
    color:#2d4661 !important;
    font-size:.84rem !important;
    font-weight:720 !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:hover{
    background:#edf5fc !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked){
    background:#e4f1fc !important;
    color:#07599e !important;
    box-shadow:inset 3px 0 0 #1c74bd !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] input{
    accent-color:#1c74bd !important;
}




.subsection-title{
    margin:15px 0 8px;
    color:#173f67;
    font-size:.84rem;
    font-weight:850;
    letter-spacing:.04em;
}

/* ===== Operations summary cards ===== */
.ops-summary-card{
    position:relative;
    min-height:116px;
    padding:15px 17px 14px 19px;
    border-radius:15px;
    background:rgba(255,255,255,.96);
    border:1px solid #d6e1ec;
    box-shadow:0 6px 17px rgba(19,52,85,.08);
    overflow:hidden;
}
.ops-summary-card::before{
    content:"";
    position:absolute;
    left:0; top:0; bottom:0;
    width:5px;
}
.ops-summary-card.dq::before{background:#d84b45;}
.ops-summary-card.process::before{background:#dc941f;}
.ops-summary-card.rca::before{background:#7448c6;}
.ops-summary-card.approval::before{background:#2b73ba;}

.ops-summary-top{
    display:flex;
    align-items:center;
    gap:9px;
}
.ops-summary-step{
    display:inline-flex;
    align-items:center;
    justify-content:center;
    width:27px;
    height:27px;
    border-radius:8px;
    background:#edf3f9;
    color:#67809a;
    font-size:.68rem;
    font-weight:850;
}
.ops-summary-card.dq .ops-summary-step{background:#fdeceb;color:#bd3e39;}
.ops-summary-card.process .ops-summary-step{background:#fff2dd;color:#b9780d;}
.ops-summary-card.rca .ops-summary-step{background:#f0eaff;color:#6740b4;}
.ops-summary-card.approval .ops-summary-step{background:#e8f2fb;color:#2465a2;}

.ops-summary-title{
    color:#3d536d;
    font-size:.82rem;
    font-weight:800;
}
.ops-summary-value{
    color:#153b64;
    font-size:2.15rem;
    font-weight:850;
    line-height:1;
    letter-spacing:-.8px;
    margin-top:12px;
}
.ops-summary-subtitle{
    color:#7a899b;
    font-size:.73rem;
    margin-top:7px;
}

/* ===== Findings workspace ===== */
.findings-header{
    display:flex;
    justify-content:space-between;
    align-items:end;
    margin:14px 0 8px;
}
.findings-kicker{
    color:#7b4bc4;
    font-size:.68rem;
    font-weight:850;
    letter-spacing:.10em;
}
.findings-title{
    color:#163f6a;
    font-size:1.28rem;
    font-weight:850;
    margin-top:2px;
}
.findings-subtitle{
    color:#71829a;
    font-size:.82rem;
    margin-top:3px;
}
.finding-severity{
    position:relative;
    min-height:82px;
    padding:13px 15px;
    border-radius:13px;
    background:rgba(255,255,255,.96);
    border:1px solid #d9e3ed;
    box-shadow:0 4px 12px rgba(22,54,88,.06);
    overflow:hidden;
}
.finding-severity::before{
    content:"";
    position:absolute;
    left:0; top:0; bottom:0; width:4px;
}
.finding-severity.critical::before{background:#d64545;}
.finding-severity.high::before{background:#e39a20;}
.finding-severity.medium::before{background:#4679be;}
.finding-severity.low::before{background:#6e7f92;}
.finding-severity-label{
    color:#6d7d92;
    font-size:.76rem;
    font-weight:750;
}
.finding-severity-value{
    color:#173b63;
    font-size:1.65rem;
    font-weight:850;
    line-height:1.05;
    margin-top:6px;
}


/* Sidebar operation sub-navigation */
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(2),
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(3),
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(4){
    margin-left:8px !important;
    padding-left:14px !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(5),
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(6),
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(7),
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(8),
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(9),
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:nth-child(10){
    margin-top:1px !important;
}

/* Typography / page hierarchy */
h1,h2,h3,h4{
    color:var(--navy) !important;
    font-weight:800 !important;
}
h2{font-size:1.55rem !important;}
h3{font-size:1.16rem !important;}
.stCaption, .muted{color:var(--muted) !important;}
.section-subtitle{color:#6b7c92 !important;}
.section-title{color:var(--navy) !important;font-size:1.45rem !important;font-weight:820 !important;}

/* Surface components */
.card,.overview-card,.health-card{
    background:var(--panel) !important;
    border:1px solid var(--line) !important;
    box-shadow:0 6px 18px rgba(20,52,88,.07) !important;
}
.overview-card{
    border-radius:16px !important;
    padding:15px 16px 14px !important;
    min-height:134px !important;
}
.overview-card .label{
    color:#61738a !important;
    font-size:.87rem !important;
    font-weight:700 !important;
}
.overview-card .value{
    color:#172c46 !important;
    font-size:1.9rem !important;
    font-weight:850 !important;
}
.overview-card .desc{
    color:#738399 !important;
    font-size:.78rem !important;
}
.priority-strip{
    background:rgba(255,255,255,.94) !important;
    border:1px solid var(--line) !important;
    border-radius:13px !important;
    box-shadow:0 3px 12px rgba(20,52,88,.06) !important;
}
.overview-note{
    background:rgba(235,243,252,.94) !important;
    border:1px solid #d1e0ef !important;
    color:#506783 !important;
    border-radius:13px !important;
}

/* Inputs, buttons and expanders */
.stButton > button{
    border-radius:9px !important;
    font-weight:750 !important;
    color:#123b66 !important;
    background:#fff !important;
    border:1px solid #b9cbdd !important;
}
.stButton > button[kind="primary"]{
    color:#fff !important;
    background:#1769b0 !important;
    border-color:#1769b0 !important;
}
.stButton > button:hover{
    border-color:#2d72af !important;
    box-shadow:0 3px 9px rgba(20,52,88,.10) !important;
}
div[data-testid="stExpander"]{
    background:rgba(255,255,255,.84) !important;
    border:1px solid #cedbe8 !important;
    border-radius:12px !important;
}

/* Data tables */
div[data-testid="stDataFrame"]{
    border:1px solid #d3dfeb !important;
    border-radius:12px !important;
    overflow:hidden !important;
    background:rgba(255,255,255,.95) !important;
}
div[data-testid="stDataFrame"] *{
    font-size:13px !important;
}

/* RCA */
.rca-header{
    background:rgba(255,255,255,.96) !important;
    border:1px solid #d8e2ed !important;
    box-shadow:0 6px 18px rgba(20,52,88,.07) !important;
}
.ai{
    background:rgba(246,242,255,.95) !important;
    border:1px solid #ddd2f7 !important;
}
.good{
    background:rgba(237,250,242,.95) !important;
    border:1px solid #c9ead5 !important;
}

/* Responsive */
@media (max-width: 1100px){
    .hero{padding:23px 24px 20px !important;}
    .hero h1{font-size:1.9rem !important;}
    div[data-baseweb="tab-list"] button[data-baseweb="tab"]{
        font-size:13px !important;
        padding-left:32px !important;
        padding-right:9px !important;
    }
    div[data-baseweb="tab-list"] button[data-baseweb="tab"] > div,
    div[data-baseweb="tab-list"] button[data-baseweb="tab"] p{
        font-size:13px !important;
    }
    div[data-baseweb="tab-list"] button[data-baseweb="tab"]::before{
        left:9px !important;
        font-size:16px !important;
    }
}

.ai-output-title{
    color:#7044c5;
    font-size:.66rem;
    font-weight:850;
    letter-spacing:.10em;
    margin:12px 0 5px;
}
.ai-brief-title-row{
    display:flex;
    align-items:center;
    gap:8px;
    margin:10px 0 2px;
    padding:7px 10px;
    border-radius:9px;
    background:rgba(255,255,255,.90);
    border:1px solid #dce5ed;
    color:#183d64;
    font-size:.80rem;
    font-weight:850;
}
.ai-brief-title-row.cause{border-left:4px solid #7448c6;}
.ai-brief-title-row.factors{border-left:4px solid #2f73b7;}
.ai-brief-title-row.impact{border-left:4px solid #d48b1b;}
.ai-brief-title-row.action{border-left:4px solid #15986f;}
.ai-brief-title-row.confidence{border-left:4px solid #62778d;}
.ai-brief-icon{font-size:15px;}

</style>
""", unsafe_allow_html=True)








if "actions" not in st.session_state: st.session_state.actions={}
if "audit" not in st.session_state: st.session_state.audit=[]
if "ai_cache" not in st.session_state: st.session_state.ai_cache={}


st.markdown("""
<div class="hero">
<h1>◈IntelliWarehouse AI</h1>
<p>Detect → Correlate → Explain → Impact → Approve</p>
</div>
""", unsafe_allow_html=True)


with st.sidebar:
    st.markdown(
        "<div class='brand'><div class='brand-mark'>◈</div>"
        "<div><div class='brand-title'>IntelliWarehouse AI</div>"
        "<div class='brand-subtitle'>Warehouse intelligence workspace</div></div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='sidebar-section-title'>WORKSPACE</div>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-group'>CORE</div>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-group-label'>OPERATIONS</div>", unsafe_allow_html=True)
    nav_options = [
        "🏠  Overview",
        "🔎  Data Quality",
        "⚙️  Inventory & Process",
        "🧠  Correlated Cases",
        "🧩  Root Cause AI",
        "🔗  Trace Graph",
        "✅  Approvals",
        "💬  Copilot",
        "🗄️  Data Explorer",
        "🧾  Audit",
    ]
    selected_nav = st.radio(
        "Workspace",
        nav_options,
        index=0,
        key="workspace_navigation",
        label_visibility="collapsed",
    )

    st.markdown("<div class='sidebar-section-title'>DATA SOURCE</div>", unsafe_allow_html=True)
    default_path = Path(__file__).parent / "Warehouse_AI_Hackathon_Synthetic_Dataset_FINAL_2.xlsx"
    uploaded = st.file_uploader("Upload warehouse workbook", type=["xlsx"])
    path = uploaded if uploaded is not None else default_path
    st.caption("Snapshot: 05 Sep 2026")

    model_name = st.secrets.get('OPENAI_MODEL', os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'))
    if enabled():
        st.success(f"LLM enabled · {model_name}")
    else:
        st.warning("LLM not enabled — deterministic evidence-grounded fallback is active.")
        st.caption("Configure VW Group LLMaaS secrets in Streamlit Cloud → Settings → Secrets.")

    st.markdown("<div class='sidebar-section-title'>GOVERNANCE</div>", unsafe_allow_html=True)
    st.caption("Human approval required · Simulated actions · Audit retained")


st.markdown(
    f"<div class='page-kicker'>WORKSPACE / {str(selected_nav).replace('🏠','').replace('🔎','').replace('⚙️','').replace('🧠','').replace('🧩','').replace('🔗','').replace('✅','').replace('💬','').replace('🗄️','').replace('🧾','').strip()}</div>",
    unsafe_allow_html=True,
)

try:
    raw=load_workbook(path)
    data, graph, dq, anomalies, cases=run_pipeline(raw)
except Exception as e:
    st.error(f"Could not load workbook: {e}")
    st.stop()

# Keep every current RCA case in the human approval queue.
# The default status is Pending; approval/rejection is persisted in session state
# and therefore survives Streamlit reruns. No action is executed automatically.
if cases is not None and not cases.empty:
    current_case_ids = set()
    for _, _case in cases.iterrows():
        _cid = str(_case.get("case_id", "")).strip()
        if not _cid:
            continue
        current_case_ids.add(_cid)
        if _cid not in st.session_state.actions:
            st.session_state.actions[_cid] = {
                "status": "Pending",
                "approver": "",
                "note": "",
                "action": _case.get("recommended_action", "Review the linked records before corrective action."),
            }

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

# Overview attention metrics are computed once after the workbook pipeline.
critical_count = 0
high_count = 0
if cases is not None and not cases.empty and "severity" in cases.columns:
    severity = cases["severity"].astype(str).str.lower()
    critical_count = int((severity == "critical").sum())
    high_count = int((severity == "high").sum())

pending = sum(
    1 for _, _case in cases.iterrows()
    if st.session_state.actions.get(
        str(_case.get("case_id", "")).strip(), {}
    ).get("status") == "Pending"
) if cases is not None and not cases.empty else 0

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

# Navigation is rendered directly below the hero for immediate visibility.



def render_rca_ai_output(raw_text: str):
    """Render the RCA model response as clean sections instead of raw markdown artifacts."""
    text = str(raw_text or "").strip()
    if not text:
        st.info("No AI explanation was returned.")
        return

    # Remove common artifacts from model output.
    text = text.replace("\\###", "###")
    text = re.sub(r"\[svg\]\([^)]*\)", "", text, flags=re.I)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<svg[\s\S]*?</svg>", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)

    sections = {}
    current = None
    buffer = []

    for line in text.splitlines():
        match = re.match(r"^\s*#{2,3}\s*(.+?)\s*$", line)
        if match:
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = match.group(1).strip()
            buffer = []
        elif current:
            buffer.append(line)

    if current:
        sections[current] = "\n".join(buffer).strip()

    wanted = [
        ("Primary Root Cause", "cause", "🧠"),
        ("Contributing Factors", "factors", "🔎"),
        ("Evidence", "factors", "🔎"),
        ("Operational Impact", "impact", "📊"),
        ("Recommended Action", "action", "✅"),
        ("Confidence", "confidence", "✓"),
    ]

    rendered = False
    for title, tone, icon in wanted:
        body = sections.get(title)
        if not body:
            continue

        rendered = True
        st.markdown(
            f"""
            <div class="ai-brief-title-row {tone}">
                <span class="ai-brief-icon">{icon}</span>
                <span>{title}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Native markdown rendering preserves bullets/headings correctly.
        st.markdown(body)

    if not rendered:
        st.markdown(text)


if 'Overview' in str(selected_nav):
    st.markdown("<div class='section-title'>Operations overview</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-subtitle'>Start with the warehouse health picture, then move into the investigation workflow.</div>",
        unsafe_allow_html=True,
    )

    overview_cols = st.columns(6)
    overview_cards = [
        ("blue", "▦", "Materials", len(data["Material_Master"]), "Master-data records in scope"),
        ("teal", "◫", "Inventory", len(data["Inventory_Stock"]), "Stock records monitored"),
        ("amber", "↗", "Deliveries", len(data["Deliveries_Dispatch"]), "Inbound / outbound records"),
        ("purple", "▤", "Purchase Orders", len(data["Purchase_Replenish"]), "Replenishment records"),
        ("red", "!", "Findings", len(dq) + len(anomalies), "Data-quality + process issues"),
        ("green", "⌁", "RCA Cases", len(cases), "Cross-system cases correlated"),
    ]
    for col, (tone, icon, label, value, desc) in zip(overview_cols, overview_cards):
        with col:
            st.markdown(
                f"""
                <div class="overview-card {tone}">
                    <div class="icon">{icon}</div>
                    <div class="label">{label}</div>
                    <div class="value">{value:,}</div>
                    <div class="desc">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown('<div class="subsection-title">Investigation status</div>', unsafe_allow_html=True)
    overview_status = [
        ("dq", "Data quality", len(dq), "Findings requiring review", "01"),
        ("process", "Process anomalies", len(anomalies), "Operational exceptions", "02"),
        ("rca", "Root-cause cases", len(cases), "Correlated investigations", "03"),
        ("approval", "Pending approval", pending, "Awaiting human decision", "04"),
    ]
    status_cols = st.columns(4)
    for col, (tone, title, value, subtitle, step) in zip(status_cols, overview_status):
        with col:
            st.markdown(
                f"""
                <div class="ops-summary-card {tone}">
                    <div class="ops-summary-top">
                        <span class="ops-summary-step">{step}</span>
                        <span class="ops-summary-title">{title}</span>
                    </div>
                    <div class="ops-summary-value">{value:,}</div>
                    <div class="ops-summary-subtitle">{subtitle}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    priority_items = []
    if critical_count:
        priority_items.append(f"<span class='priority-dot red'></span><b>{critical_count}</b> Critical")
    if high_count:
        priority_items.append(f"<span class='priority-dot amber'></span><b>{high_count}</b> High")
    if pending:
        priority_items.append(f"<span class='priority-dot blue'></span><b>{pending}</b> Pending approval")
    if priority_items:
        st.markdown(
            f"<div class='priority-strip'><span class='priority-label'>Needs attention</span>{'<span class=\"priority-sep\"> · </span>'.join(priority_items)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='priority-strip ok'><span class='priority-label'>Status</span><b>All clear</b> · No critical/high RCA cases or pending approvals</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""<div class="card">
                <div style="font-size:.76rem;color:#6a7b90;font-weight:800;letter-spacing:.04em">01 · FIND</div>
                <div style="font-size:1.12rem;font-weight:820;color:#203b5e;margin:5px 0">What needs attention?</div>
                <div style="color:#687b92;font-size:.84rem;line-height:1.45">
                    Review <b>{len(dq)}</b> data-quality findings and <b>{len(anomalies)}</b> process/inventory anomalies.
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="card">
                <div style="font-size:.76rem;color:#6a7b90;font-weight:800;letter-spacing:.04em">02 · UNDERSTAND</div>
                <div style="font-size:1.12rem;font-weight:820;color:#203b5e;margin:5px 0">Why is it happening?</div>
                <div style="color:#687b92;font-size:.84rem;line-height:1.45">
                    Trace <b>{len(cases)}</b> cross-system cases across materials, inventory, deliveries, POs and vendors.
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""<div class="card">
                <div style="font-size:.76rem;color:#6a7b90;font-weight:800;letter-spacing:.04em">03 · DECIDE</div>
                <div style="font-size:1.12rem;font-weight:820;color:#203b5e;margin:5px 0">What should happen next?</div>
                <div style="color:#687b92;font-size:.84rem;line-height:1.45">
                    <b>{pending}</b> cases await human approval. Proposed actions remain simulated until approved.
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='overview-note'><b>Recommended path:</b> Operations → Root Cause AI → Trace Graph → Approvals → Audit</div>",
        unsafe_allow_html=True,
    )
    st.info(
        "Use Copilot for natural-language questions such as \"Why is this material short?\" or \"Explain DQ-0102\". "
        "Use Data Explorer when you need the underlying workbook records."
    )

if 'Data Quality' in str(selected_nav):
    st.markdown(
        "<div class='findings-header'><div>"
        "<div class='findings-kicker'>FINDINGS</div>"
        "<div class='findings-title'>Data-quality findings</div>"
        "<div class='findings-subtitle'>Prioritize the records that need investigation, then open one finding for evidence.</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    if dq.empty:
        st.success("No data-quality findings.")
    else:
        sev = dq["severity"].astype(str).str.strip().str.title()
        severity_counts = {level: int((sev == level).sum()) for level in ["Critical", "High", "Medium", "Low"]}

        q1, q2, q3, q4 = st.columns(4)
        severity_cards = [
            ("Critical", severity_counts["Critical"], "critical"),
            ("High", severity_counts["High"], "high"),
            ("Medium", severity_counts["Medium"], "medium"),
            ("Low", severity_counts["Low"], "low"),
        ]
        for col, (label, count, tone) in zip([q1, q2, q3, q4], severity_cards):
            with col:
                st.markdown(
                    f"<div class='finding-severity {tone}'>"
                    f"<div class='finding-severity-label'>{label}</div>"
                    f"<div class='finding-severity-value'>{count:,}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        f1, f2, f3 = st.columns([1.0, 1.0, 1.8])
        with f1:
            severity_filter = st.selectbox(
                "Severity",
                ["All", "Critical", "High", "Medium", "Low"],
                key="finding_severity_filter",
            )
        with f2:
            entity_options = ["All"] + sorted(dq["entity"].astype(str).dropna().unique().tolist())
            entity_filter = st.selectbox(
                "Record",
                entity_options,
                key="finding_entity_filter",
            )
        with f3:
            search_filter = st.text_input(
                "Search finding",
                placeholder="ID, issue, record, or explanation",
                key="finding_search_filter",
            )

        filtered = dq.copy()
        if severity_filter != "All":
            filtered = filtered[filtered["severity"].astype(str).str.title() == severity_filter]
        if entity_filter != "All":
            filtered = filtered[filtered["entity"].astype(str) == entity_filter]
        if search_filter.strip():
            q = search_filter.strip().lower()
            mask = (
                filtered["issue_id"].astype(str).str.lower().str.contains(q, na=False)
                | filtered["entity"].astype(str).str.lower().str.contains(q, na=False)
                | filtered["title"].astype(str).str.lower().str.contains(q, na=False)
                | filtered["detail"].astype(str).str.lower().str.contains(q, na=False)
            )
            filtered = filtered[mask]

        st.caption(f"Showing {len(filtered):,} of {len(dq):,} data-quality findings")

        preview = filtered[["issue_id", "severity", "entity", "title", "detail"]].copy()
        preview.columns = ["ID", "Severity", "Record", "Issue", "Explanation"]
        preview["Explanation"] = preview["Explanation"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 145)
        st.dataframe(
            preview,
            width="stretch",
            hide_index=True,
            height=330,
            column_config={
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Severity": st.column_config.TextColumn("Severity", width="small"),
                "Record": st.column_config.TextColumn("Record", width="medium"),
                "Issue": st.column_config.TextColumn("Issue", width="medium"),
                "Explanation": st.column_config.TextColumn("Explanation", width="large"),
            },
        )

        e1, e2 = st.columns([1, 4])
        with e1:
            st.download_button(
                "Export findings",
                filtered.to_csv(index=False).encode("utf-8"),
                "intelliwarehouse_data_quality_findings.csv",
                "text/csv",
                use_container_width=True,
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


if 'Inventory & Process' in str(selected_nav):
    st.markdown(
        "<div class='findings-header'><div>"
        "<div class='findings-kicker process-kicker'>OPERATIONS</div>"
        "<div class='findings-title'>Inventory & process anomalies</div>"
        "<div class='findings-subtitle'>Review operational exceptions, identify high-impact issues, and inspect the records behind them.</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    if anomalies.empty:
        st.success("No inventory/process anomalies.")
    else:
        sev = anomalies["severity"].astype(str).str.strip().str.title()
        severity_counts = {level: int((sev == level).sum()) for level in ["Critical", "High", "Medium", "Low"]}

        a1, a2, a3, a4 = st.columns(4)
        for col, (label, count, tone) in zip(
            [a1, a2, a3, a4],
            [
                ("Critical", severity_counts["Critical"], "critical"),
                ("High", severity_counts["High"], "high"),
                ("Medium", severity_counts["Medium"], "medium"),
                ("Low", severity_counts["Low"], "low"),
            ],
        ):
            with col:
                st.markdown(
                    f"<div class='finding-severity {tone}'>"
                    f"<div class='finding-severity-label'>{label}</div>"
                    f"<div class='finding-severity-value'>{count:,}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        i1, i2, i3 = st.columns([1.0, 1.0, 1.8])
        with i1:
            anomaly_severity = st.selectbox(
                "Severity",
                ["All", "Critical", "High", "Medium", "Low"],
                key="anomaly_severity_filter",
            )
        with i2:
            anomaly_entities = ["All"] + sorted(anomalies["entity"].astype(str).dropna().unique().tolist())
            anomaly_entity = st.selectbox(
                "Record",
                anomaly_entities,
                key="anomaly_entity_filter",
            )
        with i3:
            anomaly_search = st.text_input(
                "Search anomaly",
                placeholder="ID, issue, record, or explanation",
                key="anomaly_search_filter",
            )

        filtered_anomalies = anomalies.copy()
        if anomaly_severity != "All":
            filtered_anomalies = filtered_anomalies[
                filtered_anomalies["severity"].astype(str).str.title() == anomaly_severity
            ]
        if anomaly_entity != "All":
            filtered_anomalies = filtered_anomalies[
                filtered_anomalies["entity"].astype(str) == anomaly_entity
            ]
        if anomaly_search.strip():
            q = anomaly_search.strip().lower()
            mask = (
                filtered_anomalies["issue_id"].astype(str).str.lower().str.contains(q, na=False)
                | filtered_anomalies["entity"].astype(str).str.lower().str.contains(q, na=False)
                | filtered_anomalies["title"].astype(str).str.lower().str.contains(q, na=False)
                | filtered_anomalies["detail"].astype(str).str.lower().str.contains(q, na=False)
            )
            filtered_anomalies = filtered_anomalies[mask]

        st.caption(f"Showing {len(filtered_anomalies):,} of {len(anomalies):,} inventory/process anomalies")

        an_view = filtered_anomalies[["issue_id","severity","entity","title","detail"]].copy()
        an_view.columns = ["ID","Severity","Record","Issue","Explanation"]
        an_view["Explanation"] = (
            an_view["Explanation"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 145)
        )
        st.dataframe(
            an_view,
            width="stretch",
            hide_index=True,
            height=340,
            column_config={
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Severity": st.column_config.TextColumn("Severity", width="small"),
                "Record": st.column_config.TextColumn("Record", width="medium"),
                "Issue": st.column_config.TextColumn("Issue", width="medium"),
                "Explanation": st.column_config.TextColumn("Explanation", width="large"),
            },
        )

        st.download_button(
            "Export anomalies",
            filtered_anomalies.to_csv(index=False).encode("utf-8"),
            "intelliwarehouse_inventory_process_anomalies.csv",
            "text/csv",
            use_container_width=False,
        )

if 'Correlated Cases' in str(selected_nav):
    st.markdown(
        "<div class='findings-header'><div>"
        "<div class='findings-kicker rca-kicker'>OPERATIONS</div>"
        "<div class='findings-title'>Correlated root-cause cases</div>"
        "<div class='findings-subtitle'>Prioritize cross-system cases by severity and impact before opening Root Cause AI.</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    if cases.empty:
        st.info("No cross-system root-cause cases detected.")
    else:
        case_sev = cases["severity"].astype(str).str.strip().str.title()
        c_counts = {level: int((case_sev == level).sum()) for level in ["Critical", "High", "Medium", "Low"]}

        c1, c2, c3, c4 = st.columns(4)
        for col, (label, count, tone) in zip(
            [c1, c2, c3, c4],
            [
                ("Critical", c_counts["Critical"], "critical"),
                ("High", c_counts["High"], "high"),
                ("Medium", c_counts["Medium"], "medium"),
                ("Low", c_counts["Low"], "low"),
            ],
        ):
            with col:
                st.markdown(
                    f"<div class='finding-severity {tone}'>"
                    f"<div class='finding-severity-label'>{label}</div>"
                    f"<div class='finding-severity-value'>{count:,}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        r1, r2, r3 = st.columns([1.0, 1.0, 1.8])
        with r1:
            case_filter = st.selectbox(
                "Severity",
                ["All", "Critical", "High", "Medium", "Low"],
                key="case_severity_filter",
            )
        with r2:
            material_options = ["All"] + sorted(cases["material"].astype(str).dropna().unique().tolist())
            material_filter = st.selectbox(
                "Material",
                material_options,
                key="case_material_filter",
            )
        with r3:
            case_search = st.text_input(
                "Search case",
                placeholder="Case ID, material, signal, or root cause",
                key="case_search_filter",
            )

        filtered_cases = cases.copy()
        if case_filter != "All":
            filtered_cases = filtered_cases[
                filtered_cases["severity"].astype(str).str.title() == case_filter
            ]
        if material_filter != "All":
            filtered_cases = filtered_cases[
                filtered_cases["material"].astype(str) == material_filter
            ]
        if case_search.strip():
            q = case_search.strip().lower()
            mask = (
                filtered_cases["case_id"].astype(str).str.lower().str.contains(q, na=False)
                | filtered_cases["material"].astype(str).str.lower().str.contains(q, na=False)
                | filtered_cases["signals"].astype(str).str.lower().str.contains(q, na=False)
                | filtered_cases["root_cause"].astype(str).str.lower().str.contains(q, na=False)
            )
            filtered_cases = filtered_cases[mask]

        st.caption(f"Showing {len(filtered_cases):,} of {len(cases):,} correlated cases")

        case_view = filtered_cases[
            ["case_id","material","severity","impact_score","signals","root_cause","recommended_action"]
        ].copy()
        case_view["signals"] = case_view["signals"].apply(lambda x: ", ".join(x) if isinstance(x, (list, tuple)) else str(x))
        case_view["root_cause"] = case_view["root_cause"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 125)
        case_view["recommended_action"] = case_view["recommended_action"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 110)
        case_view.columns = ["Case","Material","Severity","Impact","Signals","Root cause","Recommended fix"]
        st.dataframe(
            case_view,
            width="stretch",
            hide_index=True,
            height=360,
            column_config={
                "Case": st.column_config.TextColumn("Case", width="small"),
                "Material": st.column_config.TextColumn("Material", width="small"),
                "Severity": st.column_config.TextColumn("Severity", width="small"),
                "Impact": st.column_config.NumberColumn("Impact", format="%d"),
                "Signals": st.column_config.TextColumn("Signals", width="medium"),
                "Root cause": st.column_config.TextColumn("Root cause", width="large"),
                "Recommended fix": st.column_config.TextColumn("Recommended fix", width="large"),
            },
        )
        st.download_button(
            "Export correlated cases",
            filtered_cases.to_csv(index=False).encode("utf-8"),
            "intelliwarehouse_correlated_cases.csv",
            "text/csv",
        )


if 'Root Cause AI' in str(selected_nav):
    st.markdown(
        """
        <div class="rca-page-head">
            <div class="rca-page-kicker">AI INVESTIGATION</div>
            <div class="rca-page-title">Root Cause AI</div>
            <div class="rca-page-subtitle">Cause → evidence → impact → action for one correlated case at a time.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if cases.empty:
        st.info("No correlated cases available.")
    else:
        labels = [
            f"{r.case_id} · {r.material} · {r.severity} · {r.impact_score}/100"
            for _, r in cases.iterrows()
        ]

        idx = st.selectbox(
            "Case",
            range(len(labels)),
            format_func=lambda i: labels[i],
            key="rca_case_select",
        )
        case = cases.iloc[idx].to_dict()
        cid = str(case.get("case_id", ""))
        material = str(case.get("material", ""))
        severity = str(case.get("severity", "Unknown")).title()
        impact = int(case.get("impact_score", 0) or 0)
        sev_class = "critical" if severity.lower() == "critical" else "high" if severity.lower() == "high" else "medium"

        st.markdown(
            f"""
            <div class="rca-case-strip">
                <div>
                    <div class="rca-label">SELECTED CASE</div>
                    <div class="rca-case-id">{cid}</div>
                    <div class="rca-material">Material · {material}</div>
                </div>
                <div class="rca-case-right">
                    <span class="rca-severity {sev_class}">{severity}</span>
                    <span class="rca-impact">Impact <b>{impact}/100</b></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        signals = case.get("signals", [])
        if isinstance(signals, (list, tuple)):
            signals = [str(x).strip() for x in signals if str(x).strip()]
        elif str(signals).strip():
            signals = [str(signals).strip()]
        else:
            signals = []

        left, right = st.columns([1.5, 1], gap="medium")

        with left:
            st.markdown(
                f"""
                <div class="rca-panel rca-cause">
                    <div class="rca-panel-head"><span class="rca-panel-icon">🧠</span><div>
                    <div class="rca-panel-kicker">EXPLAIN</div><div class="rca-panel-title">Root cause</div></div></div>
                    <div class="rca-cause-copy">{case.get("root_cause","No root-cause explanation available.")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                """
                <div class="rca-panel rca-evidence">
                    <div class="rca-panel-head"><span class="rca-panel-icon">🔎</span><div>
                    <div class="rca-panel-kicker">EVIDENCE</div><div class="rca-panel-title">Key evidence signals</div></div></div>
                """,
                unsafe_allow_html=True,
            )
            if signals:
                for signal in signals[:6]:
                    st.markdown(
                        f"<div class='rca-evidence-row'><span class='rca-check'>✓</span><span>{signal}</span></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No evidence signals recorded.")
            st.markdown("</div>", unsafe_allow_html=True)

        with right:
            st.markdown(
                f"""
                <div class="rca-panel rca-action">
                    <div class="rca-panel-head"><span class="rca-panel-icon">✅</span><div>
                    <div class="rca-panel-kicker">DECIDE</div><div class="rca-panel-title">Recommended action</div></div></div>
                    <div class="rca-action-copy">{case.get("recommended_action","Review the linked records before corrective action.")}</div>
                </div>

                <div class="rca-panel rca-impact-panel">
                    <div class="rca-panel-head"><span class="rca-panel-icon">📊</span><div>
                    <div class="rca-panel-kicker">IMPACT</div><div class="rca-panel-title">Decision context</div></div></div>
                    <div class="rca-impact-score">{impact}<span>/100</span></div>
                    <div class="rca-impact-track"><div class="rca-impact-fill" style="width:{max(0,min(100,impact))}%"></div></div>
                    <div class="rca-impact-note">Higher score means greater operational attention.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            """
            <div class="rca-ai-box">
                <div class="rca-ai-kicker">GENERATIVE EXPLANATION</div>
                <div class="rca-ai-title">Create a concise AI decision brief</div>
                <div class="rca-ai-copy">The model rewrites the evidence into a short causal story instead of repeating the raw case description.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Generate AI explanation", type="primary", key=f"generate_rca_{cid}"):
            with st.spinner("Generating the Root Cause AI brief..."):
                try:
                    st.session_state.ai_cache[cid] = generate_root_cause(case)
                    st.session_state.ai_error = None
                except Exception as exc:
                    st.session_state.ai_cache.pop(cid, None)
                    st.session_state.ai_error = str(exc)

        if st.session_state.get("ai_error"):
            st.error(
                "AI generation failed. Check the VW Group LLMaaS credentials in Streamlit Secrets. "
                f"Details: {st.session_state.ai_error}"
            )

        if cid in st.session_state.ai_cache:
            st.markdown(
                '<div class="ai-output-title">AI EXPLANATION</div>',
                unsafe_allow_html=True,
            )
            render_rca_ai_output(st.session_state.ai_cache[cid])

        evidence = case.get("evidence", {}) or {}
        nonempty_evidence = [(sheet, records) for sheet, records in evidence.items() if records]
        if nonempty_evidence:
            total_rows = sum(len(records) for _, records in nonempty_evidence)
            with st.expander(f"Supporting records · {total_rows} linked rows"):
                for sheet, records in nonempty_evidence:
                    st.markdown(f"**{sheet}** · {len(records)} rows")
                    st.dataframe(pd.DataFrame(records), width="stretch", hide_index=True)


if 'Trace Graph' in str(selected_nav):
    st.subheader("Relationship trace")
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

if 'Approvals' in str(selected_nav):
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

if 'Copilot' in str(selected_nav):
    st.subheader("Warehouse Copilot")
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

if 'Data Explorer' in str(selected_nav):
    st.subheader("Data Explorer")
    visible_sheets=[s for s in data.keys() if s not in {"README","Data_Dictionary"}]
    sheet=st.selectbox("Sheet",visible_sheets)
    st.dataframe(data[sheet],width="stretch",hide_index=True)

if 'Audit' in str(selected_nav):
    st.subheader("Audit trail")
    if st.session_state.audit:
        st.dataframe(pd.DataFrame(st.session_state.audit),width="stretch",hide_index=True)
    else:
        st.info("No human decisions recorded in this session.")


# Defensive fallback: never leave the main canvas empty if a future nav label
# is changed without updating the router.
known_pages = [
    "Overview", "Data Quality", "Inventory & Process", "Correlated Cases",
    "Root Cause AI", "Trace Graph", "Approvals", "Copilot", "Data Explorer", "Audit"
]
if not any(p in str(selected_nav) for p in known_pages):
    st.info("Select a workspace from the sidebar to continue.")
