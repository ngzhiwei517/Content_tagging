import io
import csv
import re
import html
import hashlib
import zipfile
import os
import json
import tempfile
import time
import random
import requests
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from final_update2_adapter import (
    MARKETING_EXPORT_COLUMNS,
    QA_AUDIT_COLUMNS,
    normalize_url as final_update2_normalize_url,
    review_audit_update as final_update2_review_audit_update,
    review_cache as final_update2_review_cache,
    scrape_links as final_update2_scrape_links,
    tag_candidates as final_update2_tag_candidates,
)

try:
    import plotly.express as px
except Exception:
    px = None

st.set_page_config(page_title="TikTok Post Tagging", page_icon="", layout="wide")

MARKETS = ["PH", "MY", "KR", "SG", "VN", "TH"]
MARKET_OPTIONS = ["Other / no market"] + MARKETS
DATE_SCOPE_SHARED = "Same date for all tracks"
DATE_SCOPE_PER_TRACK = "Different date by track"
CREATIVE_TYPES = [
    "Dance", "Lip Sync", "Lyrics", "Lyrics Translation", "Carousel", "Quotes",
    "Relationship", "POV", "Slice of Life", "Reflection", "Comedy", "Beauty",
    "Fashion", "Travel", "Fitness", "Gaming", "Media/Infotainment",
    "Movie/Tv/Drama Edits", "Celebrity Edits", "Cover", "Remix", "Others",
]

# -----------------------------
# CSS
# -----------------------------
st.markdown(
    """
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #eef4ff 0%, #e7eef9 60%, #edf3fb 100%);
}
[data-testid="stSidebar"], [data-testid="stToolbar"], header { display:none !important; }
.block-container { padding-top: 1.2rem !important; padding-bottom: 2.4rem !important; max-width: 1180px; }
html, body, p, span, label, div { color:#0f172a; }
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label,
div[class*="stRadio"] label,
div[class*="stCheckbox"] label,
div[class*="stSelectbox"] label,
div[class*="stNumberInput"] label,
div[class*="stTextInput"] label,
div[class*="stTextArea"] label,
div[class*="stDateInput"] label {
    color:#0f172a !important;
    font-weight: 760 !important;
}
input, textarea, [data-baseweb="select"] > div {
    background:#ffffff !important;
    color:#111827 !important;
    border-color:#cbd5e1 !important;
}
[data-baseweb="select"] * { color:#111827 !important; }
div[data-baseweb="popover"] {
    background:#ffffff !important;
    color:#111827 !important;
}
div[data-baseweb="popover"] * { color:#111827 !important; }
div[data-baseweb="popover"] [role="option"] { background:#fff !important; color:#111827 !important; }
div[data-baseweb="popover"] [role="option"]:hover { background:#eef2ff !important; }
[data-baseweb="popover"] > div,
[data-baseweb="popover"] > div > div,
[data-baseweb="popover"] > div > div > div,
[data-baseweb="popover"] [role="dialog"],
[data-baseweb="popover"] [role="dialog"] > div,
[data-baseweb="popover"] [role="dialog"] > div > div,
[data-baseweb="calendar"],
[data-baseweb="calendar"] > div {
    background:#ffffff !important;
}
[data-baseweb="popover"] [role="dialog"] button,
[data-baseweb="calendar"] * {
    color:#111827 !important;
    text-shadow:none !important;
}
[data-baseweb="popover"] [role="dialog"] button,
[data-baseweb="calendar"] button {
    background:#ffffff !important;
    color:#111827 !important;
}
[data-baseweb="popover"] [role="dialog"] [aria-selected="true"],
[data-baseweb="popover"] [role="dialog"] [aria-selected="true"] *,
[data-baseweb="calendar"] [aria-selected="true"] {
    background:#6254e8 !important;
    color:#ffffff !important;
}
[data-baseweb="calendar"] [aria-selected="true"] * { color:#ffffff !important; }
[data-baseweb="calendar"] [aria-disabled="true"],
[data-baseweb="calendar"] [aria-disabled="true"] * { color:#94a3b8 !important; }
[data-baseweb="tag"] { background:#eef2ff !important; color:#111827 !important; border:1px solid #c7d2fe !important; }
[data-baseweb="tag"] span { color:#111827 !important; }
.selection-filter-card { background:#ffffff; border:1px solid #d8e0ec; border-radius:16px; padding:16px 18px; margin:12px 0 16px; box-shadow:0 8px 18px rgba(15,23,42,.04); }
.selection-filter-card h3 { margin:0 0 10px; font-size:16px; color:#111827; font-weight:950; }
.selection-filter-card .hint { color:#64748b !important; font-size:12px; margin-top:6px; }
.group-helper-grid { display:grid; grid-template-columns: 1fr 1fr 1fr; gap:12px; margin:12px 0 6px; }
.group-helper-card { background:#f8fafc; border:1px solid #d8e0ec; border-radius:14px; padding:13px 14px; }
.group-helper-card strong { display:block; color:#111827 !important; font-size:13px; margin-bottom:5px; }
.group-helper-card span { color:#64748b !important; font-size:12px; line-height:1.4; }
.group-blue { border-left:5px solid #6254e8; }
.group-green { border-left:5px solid #10b981; }
.group-orange { border-left:5px solid #f97316; }
.group-summary-note { background:#eef2ff; border:1px solid #c7d2fe; border-left:6px solid #6254e8; border-radius:14px; padding:13px 15px; color:#312e81 !important; font-size:13px; font-weight:800; margin:10px 0 4px; }
.group-summary-note b { color:#312e81 !important; }
@media (max-width: 900px) { .group-helper-grid { grid-template-columns:1fr; } }

/* v45: make backend progress logs readable */
[data-testid="stCodeBlock"] pre,
[data-testid="stCodeBlock"] code,
pre code {
    background:#101828 !important;
    color:#f8fafc !important;
    text-shadow:none !important;
}
.v45-run-log {
    background:#101828;
    color:#f8fafc !important;
    border:1px solid #263244;
    border-radius:18px;
    padding:18px 22px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size:14px;
    line-height:1.75;
    box-shadow:0 14px 28px rgba(15,23,42,.16);
    white-space:pre-wrap;
}
.v45-run-log span { color:#f8fafc !important; }
.v45-run-log .idx { color:#2dd4bf !important; font-weight:900; }
.v45-run-log .arrow { color:#f97316 !important; font-weight:900; }
.v45-run-log .label { color:#c7d2fe !important; font-weight:800; }


.app-title { display:flex; justify-content:space-between; align-items:flex-end; gap:18px; margin-bottom:14px; }
.app-title h1 { margin:0; font-size:28px; font-weight:950; color:#111827; letter-spacing:-.02em; }
.app-title p { margin:6px 0 0; color:#475569; font-size:14px; }
.mode-pill { background:#eef2ff; color:#3730a3 !important; border:1px solid #c7d2fe; border-radius:999px; padding:8px 14px; font-size:12px; font-weight:900; white-space:nowrap; }

.step-strip { display:grid; grid-template-columns: repeat(6, 1fr); gap:10px; margin:14px 0 20px; }
.step-card { background:rgba(255,255,255,.66); border:1px solid #d6deeb; border-radius:15px; padding:13px 13px; min-height:85px; }
.step-card.active { border:2px solid #6254e8; background:#f3f5ff; box-shadow:0 8px 20px rgba(98,84,232,.12); }
.step-card.done { background:#edfdf4; border-color:#b8eacb; }
.step-small { font-size:11px; color:#6254e8 !important; font-weight:950; letter-spacing:.06em; text-transform:uppercase; }
.step-title { font-size:15px; color:#111827 !important; font-weight:950; margin-top:7px; }
.step-desc { font-size:12px; color:#64748b !important; margin-top:6px; }

.card { background:rgba(255,255,255,.82); border:1px solid #d7e0ee; border-radius:18px; padding:22px; margin-bottom:18px; box-shadow:0 8px 24px rgba(15,23,42,.055); }
.card.compact { padding:16px 18px; }
.card h2 { margin:0 0 8px; font-size:22px; font-weight:950; color:#111827; }
.card h3 { margin:0 0 10px; font-size:17px; font-weight:900; color:#111827; }
.card p.sub { margin:0; font-size:13px; color:#64748b; }

.mode-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:10px; }
.mode-card { border:1px solid #d8e0ec; background:rgba(255,255,255,.74); border-radius:16px; padding:17px 19px; }
.mode-card.selected { border:2px solid #6254e8; background:#f3f5ff; }
.mode-card strong { display:block; font-size:16px; color:#111827; margin-bottom:7px; }
.mode-card span { color:#475569; font-size:13px; line-height:1.45; }

.stButton button, .stDownloadButton button { border-radius:12px !important; min-height:44px !important; font-weight:850 !important; }
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] { background:#5145e5 !important; border-color:#5145e5 !important; color:white !important; }
.stButton button[kind="secondary"], .stDownloadButton button[kind="secondary"] { background:#ffffff !important; color:#111827 !important; border:1px solid #cfd8e6 !important; }
.stButton button p, .stDownloadButton button p { color:inherit !important; }

[data-testid="stFileUploaderDropzone"] { background:rgba(255,255,255,.72) !important; border:1.5px dashed #94a3b8 !important; border-radius:15px !important; }
[data-testid="stFileUploaderDropzone"] *, [data-testid="stFileUploaderFile"] * { color:#111827 !important; }

.table-wrap { overflow-x:auto; border:1px solid #d7dfed; border-radius:14px; background:#fff; margin-top:10px; }
table.clean-table { width:100%; border-collapse:collapse; font-size:13px; }
table.clean-table th { background:#111827; color:#fff !important; text-align:left; padding:11px 12px; font-weight:850; white-space:nowrap; }
table.clean-table td { padding:10px 12px; border-top:1px solid #e5eaf3; color:#111827 !important; vertical-align:top; max-width:520px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
table.clean-table th:nth-child(n+3), table.clean-table td:nth-child(n+3) { font-variant-numeric: tabular-nums; }
table.clean-table tr:nth-child(even) td { background:#f8fafc; }

.metric-row { display:grid; grid-template-columns: repeat(5, 1fr); gap:12px; margin:12px 0 16px; }
.metric-card { background:#fff; border:1px solid #d8e0ec; border-radius:16px; padding:16px; }
.metric-card .val { font-size:28px; font-weight:950; color:#111827; line-height:1; }
.metric-card .lbl { font-size:11px; font-weight:900; color:#64748b; text-transform:uppercase; letter-spacing:.06em; margin-top:7px; }
.metric-card .hint { color:#64748b !important; font-size:12px; margin-top:6px; }

.good-note { background:#ecfdf5; border:1px solid #a7f3d0; border-radius:14px; padding:13px 15px; color:#065f46 !important; font-size:13px; font-weight:750; margin:10px 0; }
.warn-note { background:#fffbeb; border:1px solid #fde68a; border-radius:14px; padding:13px 15px; color:#92400e !important; font-size:13px; font-weight:750; margin:10px 0; }
.soft-note { background:#eef2ff; border:1px solid #c7d2fe; border-radius:14px; padding:13px 15px; color:#312e81 !important; font-size:13px; font-weight:750; margin:10px 0; }

.review-layout { display:grid; grid-template-columns: 1fr 1.25fr; gap:16px; align-items:start; }
.review-post { background:#ffffff; border:1px solid #d8e0ec; border-radius:18px; padding:18px; box-shadow:0 8px 18px rgba(15,23,42,.045); }
.review-post h3 { margin:0 0 8px; color:#111827 !important; font-size:19px; font-weight:950; }
.review-meta { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0 12px; }
.review-pill { background:#f3f5ff; color:#3730a3 !important; border:1px solid #d8dcff; border-radius:999px; padding:6px 10px; font-size:12px; font-weight:850; }
.review-link { color:#4f46e5 !important; font-weight:900; text-decoration:none; }
.suggested-box { background:#eef2ff; border:1px solid #c7d2fe; color:#312e81 !important; border-radius:12px; padding:12px 14px; font-size:15px; font-weight:900; margin:10px 0; }
.detail-text { color:#334155 !important; font-size:13px; line-height:1.55; }

.insight-grid { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin: 12px 0 18px; }
.insight-card { background:#ffffff; border:1px solid #d8e0ec; border-radius:16px; padding:16px; }
.insight-card strong { display:block; color:#111827 !important; font-size:15px; margin-bottom:6px; }
.insight-card span { color:#475569 !important; font-size:13px; line-height:1.45; }

.download-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:14px; margin-top:8px; }
.download-card { background:#ffffff; border:1px solid #d8e0ec; border-radius:16px; padding:16px; }
.download-card strong { display:block; color:#111827 !important; font-size:15px; margin-bottom:6px; }
.download-card span { display:block; color:#64748b !important; font-size:12px; min-height:34px; }

/* Summary page: make marketing focus obvious */
.summary-kpi-grid { display:grid; grid-template-columns: repeat(5, 1fr); gap:12px; margin:12px 0 18px; }
.summary-kpi { background:#fff; border:1px solid #d8e0ec; border-radius:18px; padding:18px 18px; box-shadow:0 8px 18px rgba(15,23,42,.045); position:relative; overflow:hidden; }
.summary-kpi:before { content:""; position:absolute; left:0; top:0; bottom:0; width:6px; background:var(--accent); }
.summary-kpi .value { color:#111827 !important; font-size:30px; font-weight:950; line-height:1; }
.summary-kpi .label { color:#111827 !important; font-size:12px; font-weight:950; text-transform:uppercase; letter-spacing:.06em; margin-top:9px; }
.summary-kpi .hint { color:#64748b !important; font-size:12px; margin-top:6px; line-height:1.35; }
.kpi-purple { --accent:#6254e8; background:linear-gradient(180deg,#ffffff 0%,#f3f5ff 100%); }
.kpi-blue { --accent:#0ea5e9; background:linear-gradient(180deg,#ffffff 0%,#eff8ff 100%); }
.kpi-orange { --accent:#f97316; background:linear-gradient(180deg,#ffffff 0%,#fff7ed 100%); }
.kpi-green { --accent:#10b981; background:linear-gradient(180deg,#ffffff 0%,#ecfdf5 100%); }
.kpi-pink { --accent:#ec4899; background:linear-gradient(180deg,#ffffff 0%,#fdf2f8 100%); }

.focus-grid { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin:12px 0 20px; }
.focus-card { border-radius:18px; padding:17px 18px; border:1px solid #d8e0ec; box-shadow:0 8px 18px rgba(15,23,42,.04); min-height:108px; }
.focus-card .eyebrow { font-size:11px; font-weight:950; text-transform:uppercase; letter-spacing:.07em; margin-bottom:9px; opacity:.78; }
.focus-card .main { font-size:20px; font-weight:950; color:#111827 !important; line-height:1.15; margin-bottom:8px; }
.focus-card .sub { font-size:12.5px; color:#475569 !important; line-height:1.4; }
.focus-purple { background:linear-gradient(135deg,#eef2ff,#ffffff); border-color:#c7d2fe; }
.focus-blue { background:linear-gradient(135deg,#e0f2fe,#ffffff); border-color:#bae6fd; }
.focus-green { background:linear-gradient(135deg,#dcfce7,#ffffff); border-color:#bbf7d0; }
.focus-orange { background:linear-gradient(135deg,#ffedd5,#ffffff); border-color:#fed7aa; }

.summary-section-title {
    display:flex;
    align-items:center;
    gap:12px;
    margin:-6px -6px 16px -6px;
    padding:14px 16px;
    border-radius:15px;
    background:linear-gradient(135deg, color-mix(in srgb, var(--accent) 18%, #ffffff), #ffffff 78%);
    border:1px solid color-mix(in srgb, var(--accent) 34%, #d8e0ec);
    border-left:7px solid var(--accent);
}
.summary-section-title .dot { display:none; }
.summary-section-title h3 { margin:0 !important; color:#111827 !important; }
.summary-section-title span { color:#475569 !important; font-size:12px; font-weight:800; }
.summary-section-title .section-icon {
    width:34px;height:34px;border-radius:12px;background:var(--accent);color:white !important;
    display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:950;box-shadow:0 6px 14px rgba(15,23,42,.12);
}
.filter-card { background:#ffffff; border:1px solid #d8e0ec; border-radius:18px; padding:18px; margin-bottom:18px; }
.filter-card h3 { margin:0 0 12px; color:#111827; font-size:17px; font-weight:950; }
.bar-list { display:flex; flex-direction:column; gap:12px; }
.bar-row { display:grid; grid-template-columns:minmax(120px, 220px) 1fr minmax(70px, auto); gap:12px; align-items:center; }
.bar-label { color:#111827 !important; font-weight:850; font-size:13px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.bar-track { height:16px; background:#e8eef8; border-radius:999px; overflow:hidden; border:1px solid #dbe4f0; }
.bar-fill { height:100%; border-radius:999px; min-width:8px; }
.bar-value { color:#111827 !important; font-weight:900; font-size:13px; text-align:right; white-space:nowrap; }
.empty-panel { background:#f8fafc; border:1px dashed #cbd5e1; border-radius:16px; padding:28px 20px; color:#64748b !important; text-align:center; font-weight:750; }
.download-card:nth-child(1){border-left:5px solid #6254e8;}
.download-card:nth-child(2){border-left:5px solid #0ea5e9;}
.download-card:nth-child(3){border-left:5px solid #10b981;}
@media (max-width: 900px) { .summary-kpi-grid, .focus-grid { grid-template-columns:1fr; } }




/* Review page: original-app inspired, clean and direct */
.review-kpi-row { display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin:10px 0 16px; }
.review-kpi { background:#fff; border:1px solid #d8e0ec; border-radius:16px; padding:15px 17px; }
.review-kpi .big { font-size:28px; font-weight:950; color:#111827; line-height:1; }
.review-kpi .label { font-size:11px; font-weight:900; color:#64748b; text-transform:uppercase; letter-spacing:.06em; margin-top:8px; }
.review-grid-main { display:grid; grid-template-columns: 240px 1fr 1.2fr; gap:22px; align-items:start; }
.review-media-card { background:#fff; border:1px solid #d8e0ec; border-radius:18px; padding:14px; box-shadow:0 8px 22px rgba(15,23,42,.055); }
.review-placeholder { height:360px; border-radius:14px; background:linear-gradient(160deg,#e2e8f0,#f8fafc); border:1px dashed #b7c3d4; display:flex; align-items:center; justify-content:center; text-align:center; color:#64748b !important; font-size:13px; font-weight:800; }
.review-tiktok-btn { display:block; text-align:center; background:#111827; color:#fff !important; text-decoration:none; border-radius:12px; padding:12px 14px; margin-top:12px; font-weight:900; }
.review-info-card { background:#fff; border:1px solid #d8e0ec; border-radius:18px; padding:18px 20px; box-shadow:0 8px 22px rgba(15,23,42,.045); min-height:360px; }
.review-label { color:#64748b !important; font-size:11px; font-weight:950; text-transform:uppercase; letter-spacing:.07em; margin:0 0 4px; }
.review-value { color:#111827 !important; font-size:14px; line-height:1.45; margin:0 0 15px; font-weight:720; word-break:break-word; }
.review-stats { display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; margin:22px 0 16px; }
.review-stat .num { color:#111827; font-size:20px; font-weight:950; }
.review-stat .lbl { color:#64748b; font-size:10px; font-weight:900; text-transform:uppercase; letter-spacing:.06em; }
.review-reason { color:#b45309 !important; font-size:13px; font-weight:850; line-height:1.4; }
.review-panel-card { background:#fff; border:1px solid #d8e0ec; border-radius:18px; padding:18px 20px; box-shadow:0 8px 22px rgba(15,23,42,.045); margin-bottom:14px; }
.review-panel-card h3 { margin:0 0 12px; font-size:18px; font-weight:950; color:#111827; }
.review-action-title { color:#64748b !important; font-size:11px; font-weight:950; text-transform:uppercase; letter-spacing:.07em; margin:10px 0; }
.review-note-info { background:#eef2ff; border-left:4px solid #6254e8; border-radius:10px; padding:12px 14px; color:#312e81 !important; font-size:13px; font-weight:750; margin:14px 0; }
.review-note-warn { background:#fffbeb; border-left:4px solid #f59e0b; border-radius:10px; padding:12px 14px; color:#92400e !important; font-size:13px; font-weight:750; margin:14px 0; }
@media (max-width: 1000px) { .review-grid-main, .review-kpi-row { grid-template-columns:1fr; } .review-placeholder { height:260px; } }

@media (max-width: 900px) { .step-strip, .metric-row, .mode-grid, .review-layout, .insight-grid, .download-grid { grid-template-columns:1fr; } }
</style>
""",
    unsafe_allow_html=True,
)

# ---- Visual polish overlay: keep v34 flow/logic, only improve look ----
st.markdown(
    """
<style>
:root{
  --ink:#0f172a; --muted:#64748b; --line:#dbe4f0; --surface:#ffffff;
  --violet:#6254e8; --violet2:#7c3aed; --sky:#0ea5e9; --green:#10b981;
  --orange:#f97316; --pink:#ec4899;
}
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(circle at 5% 0%, rgba(124,58,237,.16) 0%, rgba(124,58,237,0) 34%),
    radial-gradient(circle at 96% 12%, rgba(14,165,233,.16) 0%, rgba(14,165,233,0) 30%),
    linear-gradient(180deg,#eef4ff 0%,#edf4fb 55%,#f7fbff 100%) !important;
}
.block-container{max-width:1220px !important; padding-top:1.35rem !important;}
.app-title{
  background:linear-gradient(135deg, rgba(255,255,255,.96), rgba(242,246,255,.86));
  border:1px solid rgba(199,210,254,.9);
  box-shadow:0 18px 42px rgba(79,70,229,.10), inset 0 1px 0 rgba(255,255,255,.8);
  border-radius:24px; padding:24px 28px; margin-bottom:18px;
  align-items:center !important;
}
.app-title h1{font-size:33px !important; letter-spacing:-.035em !important;}
.app-title p{font-size:15px !important; color:#475569 !important;}
.mode-pill{
  background:linear-gradient(135deg,#eef2ff,#ffffff) !important; color:#4f46e5 !important;
  border:1px solid #c7d2fe !important; box-shadow:0 6px 16px rgba(79,70,229,.10);
  padding:9px 18px !important;
}
.step-strip{gap:14px !important; margin:16px 0 24px !important;}
.step-card{
  background:rgba(255,255,255,.78) !important; border:1px solid rgba(203,213,225,.92) !important;
  box-shadow:0 8px 20px rgba(15,23,42,.045); border-radius:18px !important;
  transition:transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}
.step-card:hover{transform:translateY(-1px); box-shadow:0 14px 30px rgba(15,23,42,.075);}
.step-card.active{
  background:linear-gradient(180deg,#f6f7ff 0%,#ffffff 100%) !important;
  border:2px solid #6254e8 !important; box-shadow:0 14px 34px rgba(98,84,232,.16) !important;
}
.step-card.done{background:linear-gradient(180deg,#effdf5 0%,#ffffff 100%) !important; border-color:#a7f3d0 !important;}
.step-small{color:#6254e8 !important;}
.step-title{font-size:16px !important;}
.card,.selection-filter-card,.filter-card,.review-post,.review-info-card,.review-panel-card,.metric-card,.insight-card,.download-card{
  background:rgba(255,255,255,.90) !important;
  border:1px solid rgba(211,222,236,.96) !important;
  box-shadow:0 14px 34px rgba(15,23,42,.060) !important;
}
.card{border-radius:22px !important;}
.card h2{font-size:24px !important; letter-spacing:-.02em;}
.card h3{letter-spacing:-.01em;}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"]{
  background:linear-gradient(135deg,#6254e8,#5145e5) !important;
  border:0 !important; color:white !important; box-shadow:0 10px 22px rgba(81,69,229,.20) !important;
}
.stButton button[kind="secondary"], .stDownloadButton button[kind="secondary"]{
  background:rgba(255,255,255,.92) !important; border:1px solid #cbd5e1 !important;
}
input, textarea, [data-baseweb="select"] > div{
  border-radius:13px !important; border-color:#cbd5e1 !important; box-shadow:0 2px 10px rgba(15,23,42,.035) !important;
}
[data-testid="stFileUploaderDropzone"]{
  background:linear-gradient(180deg, rgba(255,255,255,.80), rgba(248,250,252,.92)) !important;
  border:1.5px dashed #94a3b8 !important; border-radius:18px !important;
}
.good-note,.soft-note,.warn-note,.group-summary-note{border-radius:16px !important; box-shadow:0 8px 18px rgba(15,23,42,.035);}
.summary-kpi{box-shadow:0 12px 28px rgba(15,23,42,.06) !important;}
.focus-card,.summary-section-title{box-shadow:0 12px 28px rgba(15,23,42,.055) !important;}
.bar-track{height:18px !important; background:#e6edf7 !important;}
.table-wrap{box-shadow:0 12px 28px rgba(15,23,42,.055) !important; border-radius:18px !important;}
table.clean-table th{background:#111827 !important;}
table.clean-table td{font-size:13.2px !important;}
.review-grid-main{gap:24px !important;}
.review-media-card,.review-info-card,.review-panel-card{border-radius:22px !important;}
.review-tiktok-btn{box-shadow:0 10px 22px rgba(15,23,42,.18);}
@media (max-width:900px){.app-title{display:block !important}.mode-pill{display:inline-block;margin-top:12px}.step-strip{grid-template-columns:1fr 1fr !important}}
</style>
""",
    unsafe_allow_html=True,
)




# ---- V37 mature professional refresh: visual only, keeps v35 flow/logic ----
st.markdown(
    """
<style>
/* Mature professional hero, visual but not playful */
.hero-v37{
  position:relative;
  overflow:hidden;
  min-height:148px;
  background:
    linear-gradient(135deg, rgba(255,255,255,.98) 0%, rgba(244,247,255,.98) 55%, rgba(237,242,255,.96) 100%) !important;
  border:1px solid rgba(203,213,225,.95) !important;
  box-shadow:0 18px 42px rgba(15,23,42,.08), 0 8px 18px rgba(79,70,229,.07) !important;
}
.hero-v37:before{
  content:"";
  position:absolute;
  left:0; top:0; bottom:0;
  width:8px;
  background:linear-gradient(180deg,#312e81,#4f46e5,#0f766e);
}
.hero-v37:after{
  content:"";
  position:absolute;
  right:-110px; top:-120px;
  width:320px; height:320px;
  border-radius:999px;
  background:radial-gradient(circle, rgba(79,70,229,.10), rgba(79,70,229,0) 62%);
}
.hero-copy,.hero-badge{position:relative; z-index:1;}
.hero-eyebrow{
  display:inline-flex; align-items:center; gap:8px;
  color:#4f46e5 !important;
  background:#eef2ff;
  border:1px solid #c7d2fe;
  padding:6px 10px;
  border-radius:999px;
  font-size:11px;
  font-weight:950;
  text-transform:uppercase;
  letter-spacing:.08em;
  margin-bottom:10px;
}
.hero-eyebrow:before{content:""; display:none;}
.hero-chips{display:flex; gap:8px; flex-wrap:wrap; margin-top:14px;}
.hero-chips span{
  display:inline-flex;
  background:rgba(255,255,255,.76);
  border:1px solid rgba(203,213,225,.92);
  color:#334155 !important;
  border-radius:999px;
  padding:7px 11px;
  font-size:12px;
  font-weight:850;
  box-shadow:0 6px 14px rgba(15,23,42,.045);
}
.hero-badge{
  width:156px;
  min-height:120px;
  background:#111827;
  border-radius:18px;
  padding:17px 15px;
  color:#fff !important;
  text-align:center;
  box-shadow:0 16px 34px rgba(17,24,39,.16);
  border:1px solid rgba(15,23,42,.10);
}
.hero-badge *{color:#fff !important;}
.hero-badge-icon{display:none;}
.hero-badge-title{font-weight:950; font-size:13px; letter-spacing:.03em; text-transform:uppercase;}
.hero-badge-sub{font-size:11px; color:#cbd5e1 !important; margin-top:6px;}

/* Step navigation with icons and clearer progress */
.step-strip{position:relative;}
.step-card{
  position:relative;
  overflow:hidden;
  min-height:98px !important;
}
.step-card:before{
  content:"";
  position:absolute; left:0; top:0; bottom:0; width:5px;
  background:#cbd5e1;
}
.step-card.active:before{background:linear-gradient(180deg,#6254e8,#0ea5e9);}
.step-card.done:before{background:linear-gradient(180deg,#10b981,#22c55e);}
.step-head{display:flex; align-items:center; justify-content:space-between; gap:8px;}
.step-icon{
  width:34px; height:34px;
  display:inline-flex; align-items:center; justify-content:center;
  border-radius:11px;
  background:#f1f5f9;
  box-shadow:inset 0 0 0 1px #e2e8f0;
  font-size:11px;
  font-weight:950;
  letter-spacing:.04em;
}
.step-card.active .step-icon{background:#eef2ff; box-shadow:inset 0 0 0 1px #c7d2fe, 0 8px 18px rgba(98,84,232,.16);}
.step-card.done .step-icon{background:#ecfdf5; box-shadow:inset 0 0 0 1px #a7f3d0;}

/* Make major sections less flat */
.card,.selection-filter-card,.filter-card,.review-post,.review-info-card,.review-panel-card,.download-card,.insight-card{
  position:relative;
  overflow:hidden;
}
.card:before,.selection-filter-card:before,.filter-card:before,.review-post:before,.review-info-card:before,.review-panel-card:before,.download-card:before,.insight-card:before{
  content:"";
  position:absolute; top:0; left:0; right:0; height:4px;
  background:linear-gradient(90deg,#6254e8,#0ea5e9,#10b981);
  opacity:.80;
}
.card.compact:before{height:3px; opacity:.55;}
.mode-card{
  min-height:118px;
  transition:transform .12s ease, box-shadow .12s ease;
}
.mode-card:hover{transform:translateY(-1px); box-shadow:0 14px 28px rgba(15,23,42,.07);}
.mode-card.selected{box-shadow:0 14px 30px rgba(98,84,232,.16) !important;}
.mode-card strong:before{display:inline-block; margin-right:8px;}
.mode-card.selected strong:before{content:"●"; color:#6254e8;}
.mode-card:not(.selected) strong:before{content:"○"; color:#94a3b8;}

/* More interesting metric cards */
.metric-card{
  background:linear-gradient(180deg,#ffffff 0%,#f8fbff 100%) !important;
  border-radius:18px !important;
}
.metric-card:nth-child(1){border-left:6px solid #6254e8 !important;}
.metric-card:nth-child(2){border-left:6px solid #0ea5e9 !important;}
.metric-card:nth-child(3){border-left:6px solid #10b981 !important;}
.metric-card:nth-child(4){border-left:6px solid #f97316 !important;}
.metric-card:nth-child(5){border-left:6px solid #ec4899 !important;}

/* Tables: softer, modern, readable */
table.clean-table th{
  background:linear-gradient(180deg,#111827,#1e293b) !important;
}
table.clean-table tr:hover td{background:#eef6ff !important;}
.table-wrap{background:#ffffff !important;}

/* Summary bar lists */
.bar-fill{background:linear-gradient(90deg,#6254e8,#0ea5e9) !important;}
.bar-row:nth-child(2n) .bar-fill{background:linear-gradient(90deg,#10b981,#0ea5e9) !important;}
.bar-row:nth-child(3n) .bar-fill{background:linear-gradient(90deg,#f97316,#ec4899) !important;}

/* Small polish */
.good-note{background:linear-gradient(135deg,#ecfdf5,#ffffff) !important;}
.soft-note{background:linear-gradient(135deg,#eef2ff,#ffffff) !important;}
.warn-note{background:linear-gradient(135deg,#fffbeb,#ffffff) !important;}
@media (max-width:900px){.hero-badge{margin-top:14px;width:100%;}.hero-v37{display:block !important}.hero-chips{margin-bottom:10px}}
</style>
""",
    unsafe_allow_html=True,
)



# -----------------------------
# V38 visual override: refined marketing/SaaS look
# -----------------------------
st.markdown(
    """
<style>
:root{
  --ink:#111827;
  --muted:#5b6577;
  --line:#dbe4f0;
  --panel:#ffffff;
  --soft:#f6f8fc;
  --indigo:#5b50e8;
  --blue:#0ea5e9;
  --green:#10b981;
  --orange:#f97316;
}
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(circle at 10% 0%, rgba(91,80,232,.10) 0, rgba(91,80,232,0) 32%),
    radial-gradient(circle at 88% 6%, rgba(14,165,233,.10) 0, rgba(14,165,233,0) 28%),
    linear-gradient(180deg,#eef4ff 0%,#eaf1fb 48%,#edf4fb 100%) !important;
}
.block-container{max-width:1210px !important; padding-top:1.05rem !important;}

/* Hero: cleaner, less textbook, still mature */
.hero-v37{
  position:relative !important;
  overflow:hidden !important;
  min-height:158px !important;
  display:flex !important;
  align-items:center !important;
  justify-content:space-between !important;
  gap:28px !important;
  padding:30px 34px !important;
  margin-bottom:18px !important;
  border-radius:28px !important;
  border:1px solid rgba(203,213,225,.72) !important;
  background:
    linear-gradient(135deg,rgba(255,255,255,.94) 0%,rgba(247,249,255,.96) 55%,rgba(238,243,255,.96) 100%) !important;
  box-shadow:0 24px 62px rgba(15,23,42,.10), inset 0 1px 0 rgba(255,255,255,.9) !important;
}
.hero-v37:before{
  content:"" !important;
  position:absolute !important;
  left:auto !important;
  right:-78px !important;
  top:-98px !important;
  width:320px !important;
  height:320px !important;
  border-radius:999px !important;
  background:radial-gradient(circle,rgba(91,80,232,.18),rgba(91,80,232,0) 62%) !important;
}
.hero-v37:after{
  content:"" !important;
  position:absolute !important;
  right:110px !important;
  bottom:-96px !important;
  width:260px !important;
  height:260px !important;
  border-radius:999px !important;
  background:radial-gradient(circle,rgba(14,165,233,.14),rgba(14,165,233,0) 65%) !important;
}
.hero-eyebrow{
  background:transparent !important;
  border:none !important;
  padding:0 !important;
  margin-bottom:10px !important;
  color:#5b50e8 !important;
  font-size:11px !important;
  font-weight:950 !important;
  letter-spacing:.12em !important;
}
.hero-v37 h1{
  font-size:34px !important;
  letter-spacing:-.045em !important;
  line-height:1.05 !important;
  color:var(--ink) !important;
}
.hero-v37 p{max-width:670px !important; color:#475569 !important; font-size:15px !important; line-height:1.65 !important;}
.hero-chips span{
  background:#fff !important;
  border:1px solid rgba(203,213,225,.82) !important;
  color:#334155 !important;
  border-radius:12px !important;
  padding:8px 12px !important;
  box-shadow:0 8px 18px rgba(15,23,42,.045) !important;
}
.hero-badge{
  width:170px !important;
  min-height:118px !important;
  background:linear-gradient(180deg,#111827 0%,#20263a 100%) !important;
  border:1px solid rgba(255,255,255,.15) !important;
  border-radius:24px !important;
  box-shadow:0 20px 42px rgba(17,24,39,.22) !important;
  display:flex !important;
  flex-direction:column !important;
  align-items:flex-start !important;
  justify-content:center !important;
  text-align:left !important;
  padding:20px !important;
}
.hero-badge-title{font-size:15px !important; text-transform:none !important; letter-spacing:-.01em !important;}
.hero-badge-sub{font-size:12px !important; color:#cbd5e1 !important; line-height:1.45 !important;}
.hero-title-only{
  min-height:0 !important;
  justify-content:flex-start !important;
  padding:26px 34px !important;
}
.hero-title-only h1{margin:0 !important;}

/* Step navigation: more product-like, not textbook */
.step-strip{
  display:grid !important;
  grid-template-columns:repeat(6,1fr) !important;
  gap:12px !important;
  margin:18px 0 22px !important;
}
.step-card{
  min-height:92px !important;
  border-radius:20px !important;
  background:rgba(255,255,255,.73) !important;
  border:1px solid rgba(203,213,225,.75) !important;
  box-shadow:0 12px 26px rgba(15,23,42,.055) !important;
  padding:14px 15px !important;
}
.step-card:before{display:none !important;}
.step-card.active{
  background:linear-gradient(180deg,#ffffff 0%,#f3f5ff 100%) !important;
  border:1.5px solid rgba(91,80,232,.78) !important;
  box-shadow:0 16px 34px rgba(91,80,232,.14) !important;
}
.step-card.done{
  background:linear-gradient(180deg,#f5fffa 0%,#ffffff 100%) !important;
  border-color:rgba(16,185,129,.32) !important;
}
.step-head{align-items:flex-start !important;}
.step-icon{
  width:30px !important;
  height:30px !important;
  border-radius:999px !important;
  background:#f8fafc !important;
  border:1px solid #dbe4f0 !important;
  box-shadow:none !important;
  color:#334155 !important;
}
.step-card.active .step-icon{background:#5b50e8 !important; color:#fff !important; border-color:#5b50e8 !important; box-shadow:0 10px 20px rgba(91,80,232,.22) !important;}
.step-card.done .step-icon{background:#10b981 !important; color:#fff !important; border-color:#10b981 !important;}
.step-small{color:#64748b !important; font-size:10px !important; letter-spacing:.11em !important;}
.step-title{color:#111827 !important; font-size:15px !important; letter-spacing:-.01em !important;}
.step-desc{color:#64748b !important; font-size:12px !important;}

/* Cards: polished but calmer */
.card,.compact,.selection-filter-card,.filter-card,.review-post,.review-info-card,.review-panel-card,.download-card,.insight-card,.mode-card{
  border-radius:22px !important;
  border:1px solid rgba(203,213,225,.72) !important;
  background:rgba(255,255,255,.82) !important;
  box-shadow:0 16px 38px rgba(15,23,42,.065) !important;
}
.card:before,.selection-filter-card:before,.filter-card:before,.review-post:before,.review-info-card:before,.review-panel-card:before,.download-card:before,.insight-card:before{height:0 !important; display:none !important;}
.mode-card.selected{background:linear-gradient(180deg,#ffffff 0%,#f3f5ff 100%) !important; border-color:rgba(91,80,232,.86) !important;}
.mode-card.selected strong:before,.mode-card:not(.selected) strong:before{display:none !important; content:"" !important;}
.good-note,.soft-note,.warn-note{border-radius:16px !important; box-shadow:0 10px 24px rgba(15,23,42,.045) !important;}

/* Metrics and summary visual hierarchy */
.metric-card{
  border-radius:22px !important;
  background:#ffffff !important;
  border:1px solid rgba(203,213,225,.72) !important;
  box-shadow:0 14px 30px rgba(15,23,42,.06) !important;
  border-left:none !important;
  position:relative !important;
}
.metric-card:after{
  content:""; position:absolute; left:18px; right:18px; bottom:0; height:4px; border-radius:999px 999px 0 0;
  background:linear-gradient(90deg,#5b50e8,#0ea5e9);
}
.metric-card:nth-child(2):after{background:linear-gradient(90deg,#0ea5e9,#10b981);}
.metric-card:nth-child(3):after{background:linear-gradient(90deg,#10b981,#22c55e);}
.metric-card:nth-child(4):after{background:linear-gradient(90deg,#f97316,#ec4899);}
.metric-card:nth-child(5):after{background:linear-gradient(90deg,#64748b,#94a3b8);}

/* Buttons: slightly more refined */
.stButton button{
  border-radius:14px !important;
  font-weight:850 !important;
  min-height:43px !important;
}
.stButton button[kind="primary"]{
  background:linear-gradient(135deg,#5b50e8,#6d5df6) !important;
  border:1px solid rgba(91,80,232,.85) !important;
  box-shadow:0 12px 24px rgba(91,80,232,.20) !important;
}

/* Tables and bar lists */
.table-wrap{
  border-radius:18px !important;
  overflow-x:auto !important;
  overflow-y:hidden !important;
  -webkit-overflow-scrolling:touch;
  scrollbar-gutter:stable;
  border:1px solid rgba(203,213,225,.72) !important;
  box-shadow:0 16px 34px rgba(15,23,42,.055) !important;
}
table.clean-table{width:max-content !important; min-width:100% !important;}
.table-wrap::-webkit-scrollbar{height:11px;}
.table-wrap::-webkit-scrollbar-track{background:#eef2f7;}
.table-wrap::-webkit-scrollbar-thumb{background:#94a3b8; border-radius:999px; border:2px solid #eef2f7;}
table.clean-table th{background:#111827 !important; color:#f8fafc !important;}
table.clean-table td{background:#fff !important;}
table.clean-table tr:nth-child(even) td{background:#f8fafc !important;}
table.clean-table tr:hover td{background:#eef4ff !important;}
.bar-track{background:#edf2f7 !important;}
.bar-fill{background:linear-gradient(90deg,#5b50e8,#0ea5e9) !important;}

@media (max-width:900px){.hero-v37{display:block !important}.hero-badge{width:100% !important;margin-top:16px}.step-strip{grid-template-columns:1fr 1fr !important}}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# State
# -----------------------------
DEFAULT_STATE = {
    "step": 1,
    "mode": "General UGC creative types",
    "gemini_key": "",
    "apify_token": "",
    "batch_df": pd.DataFrame(),
    "selected_df": pd.DataFrame(),
    "tagged_df": pd.DataFrame(),
    "last_message": "",
    "review_pointer": 0,
    "enable_full_video_fallback_v46": False,
    "apify_records_by_key": {},
    "date_filter_scope_v68": DATE_SCOPE_SHARED,
    "track_date_settings_v68": {},
}
for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v

# -----------------------------
# Helpers
# -----------------------------
def go(step: int):
    st.session_state.step = step
    st.rerun()


def safe_str(v) -> str:
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v).strip()


def clean_api_secret(v) -> str:
    """Clean pasted API keys/tokens before storing or using them.

    Users sometimes paste keys with spaces, quotes, or a leading "Bearer ".
    ApifyClient expects the raw token only.
    """
    s = safe_str(v)
    if not s:
        return ""
    s = s.strip().strip('\"').strip("'").strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    return s


def display_empty(v: str, fallback: str = "Not specified") -> str:
    s = safe_str(v)
    return s if s else fallback


def display_market(v: str) -> str:
    """Marketing-friendly market display. Blank market rows are grouped as Other."""
    s = safe_str(v).upper()
    return s if s else "Other"


def split_creative_labels(value) -> List[str]:
    """Split the stored 1-2 label output into clean individual labels."""
    labels = []
    for part in safe_str(value).split(","):
        label = re.sub(r"\s+", " ", part).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def primary_creative_type(value) -> str:
    """Use one stable category for marketing charts.

    The full 1-2 label output is preserved in exports and post tables. Summary
    charts use the first label only so combinations such as
    'Movie/Tv/Drama Edits, Relationship' do not become separate chart categories.
    """
    labels = split_creative_labels(value)
    return labels[0] if labels else "Others"


def calculate_engagement_rate(row) -> float:
    views = clean_num(row.get("Views", 0))
    total = clean_num(row.get("Total Engagement", 0))
    return (total / views) if views else 0.0


def rate_pct(numerator, denominator) -> float:
    denom = clean_num(denominator)
    if denom <= 0:
        return 0.0
    return round(clean_num(numerator) / denom * 100, 2)


def kol_size_for_market(followers, market) -> str:
    """Return market-specific KOL size bucket using follower thresholds.

    A market is required because the supplied thresholds differ by country.
    Followers are refreshed from Apify, but campaign Market must come from user
    input and must never be inferred from TikTok creator/post location.
    """
    f = clean_num(followers)
    if f <= 0:
        return "Unknown"
    m = display_market(market).upper()
    if m in {"ID", "INDONESIA"}:
        rules = [(1000, "Buzzer"), (10000, "Nano"), (50000, "Micro"), (200000, "Medium"), (1000000, "Macro"), (10**18, "Mega")]
    elif m in {"MY", "MALAYSIA"}:
        rules = [(10000, "Nano"), (100000, "Micro"), (1000000, "Macro"), (10**18, "Mega")]
    elif m in {"PH", "PHILIPPINES"}:
        rules = [(10000, "Nano"), (100000, "Micro"), (2000000, "Macro"), (10**18, "Mega")]
    elif m in {"SG", "SINGAPORE"}:
        rules = [(10000, "Nano"), (30000, "Micro"), (100000, "Medium"), (500000, "Macro"), (10**18, "Mega")]
    elif m in {"TH", "THAILAND"}:
        rules = [(1000, "Buzzer"), (10000, "Nano"), (100000, "Micro"), (500000, "Medium"), (1000000, "Macro"), (5000000, "Mega"), (10**18, "Super Mega")]
    elif m in {"VN", "VIETNAM", "VIET NAM"}:
        rules = [(1000, "Buzzer"), (10000, "Nano"), (100000, "Micro"), (500000, "Medium"), (1000000, "Macro"), (5000000, "Mega"), (10**18, "Super Mega")]
    else:
        return "Unknown"
    for threshold, label in rules:
        if f <= threshold:
            return label
    return "Mega"


def add_performance_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add fields expected in the marketing export: followers, KOL size and rate columns."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in ["Views", "Likes", "Comments", "Shares", "Saves", "Followers"]:
        if col not in out.columns:
            out[col] = 0
        out[col] = out[col].map(clean_num)
    if "Total Engagement" not in out.columns:
        out["Total Engagement"] = 0
    out["Total Engagement"] = out.apply(lambda r: clean_num(r.get("Total Engagement")) or clean_num(r.get("Likes")) + clean_num(r.get("Comments")) + clean_num(r.get("Shares")) + clean_num(r.get("Saves")), axis=1)
    out["Engagement Rate"] = out.apply(lambda r: rate_pct(r.get("Total Engagement"), r.get("Views")), axis=1)
    out["Likes Rate"] = out.apply(lambda r: rate_pct(r.get("Likes"), r.get("Views")), axis=1)
    out["Comments Rate"] = out.apply(lambda r: rate_pct(r.get("Comments"), r.get("Views")), axis=1)
    out["Shares Rate"] = out.apply(lambda r: rate_pct(r.get("Shares"), r.get("Views")), axis=1)
    out["Saves Rate"] = out.apply(lambda r: rate_pct(r.get("Saves"), r.get("Views")), axis=1)
    def resolved_kol_size(row) -> str:
        calculated = kol_size_for_market(row.get("Followers"), row.get("Market"))
        if calculated != "Unknown":
            return calculated
        existing = safe_str(row.get("KOL Size"))
        return existing if existing and existing.lower() != "unknown" else "Unknown"

    out["KOL Size"] = out.apply(resolved_kol_size, axis=1)
    return out


def format_display_value(col: str, val) -> str:
    if col in {"Engagement Rate", "Likes Rate", "Comments Rate", "Shares Rate", "Saves Rate"}:
        try:
            return f"{float(val):.2f}%"
        except Exception:
            return safe_str(val)
    if col in {"Posts", "Views", "Likes", "Comments", "Shares", "Saves", "Total Engagement", "Engagements", "Followers"}:
        return f"{clean_num(val):,}" if clean_num(val) else "0"
    return safe_str(val)


def clean_num(v) -> int:
    if v is None:
        return 0
    try:
        if pd.isna(v):
            return 0
    except Exception:
        pass
    s = str(v).replace(",", "").replace("%", "").strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def short_num(n: int) -> str:
    n = clean_num(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:,}"


def esc(v) -> str:
    return html.escape(display_empty(v, ""))


def is_tiktok_link(v) -> bool:
    return "tiktok.com" in safe_str(v).lower()


def extract_creator(url: str) -> str:
    m = re.search(r"tiktok\.com/@([^/\?]+)", safe_str(url))
    return m.group(1) if m else ""


def tiktok_post_date(url: str) -> pd.Timestamp:
    """Read the UTC creation date encoded in a full TikTok video ID."""
    match = re.search(r"/video/(\d{15,22})", safe_str(url))
    if not match:
        return pd.NaT
    try:
        created = datetime.fromtimestamp(int(match.group(1)) >> 32, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return pd.NaT
    if not 2016 <= created.year <= date.today().year + 1:
        return pd.NaT
    return pd.Timestamp(created.date())


def input_post_date(value) -> pd.Timestamp:
    """Parse a source date, including numeric Excel serial dates."""
    try:
        if pd.isna(value):
            return pd.NaT
    except Exception:
        pass
    if isinstance(value, (int, float)) and 20_000 <= float(value) <= 80_000:
        return pd.to_datetime(float(value), unit="D", origin="1899-12-30", errors="coerce")
    numeric_text = safe_str(value).replace(",", "")
    if re.fullmatch(r"\d+(?:\.0+)?", numeric_text):
        numeric_value = float(numeric_text)
        if 20_000 <= numeric_value <= 80_000:
            return pd.to_datetime(numeric_value, unit="D", origin="1899-12-30", errors="coerce")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", numeric_text):
        return pd.to_datetime(numeric_text, format="%Y-%m-%d", errors="coerce")
    return pd.to_datetime(value, errors="coerce", dayfirst=True)


def canonical_post_date(row: pd.Series) -> pd.Timestamp:
    """Prefer the date encoded by TikTok so locale-swapped Excel dates do not break filtering."""
    link_date = tiktok_post_date(row.get("Link", ""))
    if not pd.isna(link_date):
        return link_date
    return input_post_date(row.get("Date", ""))


def inferred_viral_date_for_track_v68(rows: pd.DataFrame, track_name: str):
    """Return one consistent uploaded viral date for a track, if available."""
    if rows is None or rows.empty or "Viral Date" not in rows.columns:
        return None
    track_col = "Track Display" if "Track Display" in rows.columns else "Track"
    if track_col not in rows.columns:
        return None
    matching = rows[rows[track_col].fillna("").astype(str).eq(str(track_name))]
    parsed_dates = [input_post_date(value) for value in matching["Viral Date"].tolist()]
    unique_dates = sorted({stamp.date() for stamp in parsed_dates if not pd.isna(stamp)})
    return unique_dates[0] if len(unique_dates) == 1 else None


def filter_posts_by_date_window_v68(
    rows: pd.DataFrame,
    parsed_dates: pd.Series,
    window_days: int,
    global_date=None,
    track_settings: Optional[Dict[str, Dict]] = None,
    track_col: str = "Track Display",
) -> pd.DataFrame:
    """Apply one shared date window or independent windows for selected tracks.

    In per-track mode, a track with ``enabled=False`` is intentionally left
    unfiltered because not every campaign track is viral. An enabled track with
    no usable post date is excluded because it cannot be confirmed in-window.
    """
    if rows is None or rows.empty:
        return rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame()

    out = rows.copy()
    parsed = pd.Series(parsed_dates, index=out.index)
    parsed = pd.to_datetime(parsed, errors="coerce")
    days = max(0, int(window_days or 0))

    if track_settings is None:
        center = pd.to_datetime(global_date, errors="coerce")
        if pd.isna(center):
            return out
        start = center - pd.Timedelta(days=days)
        end = center + pd.Timedelta(days=days)
        return out.loc[parsed.between(start, end).fillna(False)].copy()

    keep = pd.Series(True, index=out.index, dtype=bool)
    track_values = (
        out[track_col].fillna("").astype(str)
        if track_col in out.columns
        else pd.Series("", index=out.index, dtype=str)
    )
    for track_name, raw_setting in (track_settings or {}).items():
        setting = raw_setting if isinstance(raw_setting, dict) else {}
        if not bool(setting.get("enabled", False)):
            continue
        center = pd.to_datetime(setting.get("date"), errors="coerce")
        if pd.isna(center):
            continue
        track_mask = track_values.eq(str(track_name))
        start = center - pd.Timedelta(days=days)
        end = center + pd.Timedelta(days=days)
        keep.loc[track_mask] = parsed.loc[track_mask].between(start, end).fillna(False)
    return out.loc[keep].copy()


def track_date_widget_suffix_v68(track_name: str) -> str:
    """Return a stable, compact widget suffix without exposing the track name."""
    return hashlib.sha1(safe_str(track_name).encode("utf-8")).hexdigest()[:12]


def reset_date_filter_state_v68() -> None:
    """Remove date settings that must not carry into a new batch."""
    st.session_state.use_date_filter = False
    st.session_state.date_filter_scope_v68 = DATE_SCOPE_SHARED
    st.session_state.track_date_settings_v68 = {}
    for key in list(st.session_state.keys()):
        key_text = str(key)
        if key_text in {"date_filter_scope_widget_v68", "track_date_window_widget_v68"} or key_text.startswith((
            "track_date_enabled_v68_",
            "track_date_value_v68_",
        )):
            del st.session_state[key]


def set_date_filter_scope_v68(scope: str) -> None:
    """Persist the two-button date mode before Streamlit reruns the page."""
    st.session_state.date_filter_scope_v68 = (
        scope if scope in {DATE_SCOPE_SHARED, DATE_SCOPE_PER_TRACK} else DATE_SCOPE_SHARED
    )


def selection_rank_metric_label(selection_mode: str, rank_metrics) -> str:
    """Return the actual selection ranking recorded in the QA summary."""
    if selection_mode != "Top posts":
        return "Original batch order"
    metrics = [rank_metrics] if isinstance(rank_metrics, str) else list(rank_metrics or [])
    labels = [safe_str(metric) for metric in metrics if safe_str(metric)]
    return ", ".join(labels) or "Total Engagement"


def parse_links(text: str) -> List[str]:
    links = []
    for raw in re.split(r"[\n,\s]+", text or ""):
        s = raw.strip()
        if is_tiktok_link(s):
            links.append(s)
    seen = set()
    out = []
    for link in links:
        key = link.split("?")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(link)
    return out


def normalize_market(v: str) -> str:
    s = safe_str(v).upper()
    if s in MARKETS:
        return s
    mapping = {
        "PHILIPPINES": "PH", "PHILIPPINE": "PH", "MALAYSIA": "MY", "KOREA": "KR",
        "SOUTH KOREA": "KR", "SINGAPORE": "SG", "VIETNAM": "VN", "VIET NAM": "VN", "THAILAND": "TH",
    }
    return mapping.get(s, s if s else "")


def unique_columns(cols: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    out: List[str] = []
    for c in cols:
        base = str(c).replace("\ufeff", "").replace("\n", " ").strip() or "Column"
        if base not in seen:
            seen[base] = 0
            out.append(base)
        else:
            seen[base] += 1
            out.append(f"{base}.{seen[base]}")
    return out


def detect_csv_delimiter(text: str) -> str:
    """Detect common export delimiters without treating URL characters as separators."""
    sample = "\n".join((text or "").splitlines()[:20])[:65536]
    if not sample:
        return ","
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def read_any_table(uploaded_file) -> pd.DataFrame:
    raw = uploaded_file.getvalue()
    name = uploaded_file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
    else:
        last_err = None
        for enc in ["utf-8-sig", "utf-8", "utf-16", "cp1252", "latin1"]:
            try:
                text = raw.decode(enc).lstrip("\ufeff")
                delimiter = detect_csv_delimiter(text)
                df = pd.read_csv(io.StringIO(text), sep=delimiter)
                break
            except Exception as e:
                last_err = e
        else:
            raise last_err
    df = df.copy()
    df.columns = unique_columns(list(df.columns))
    return df


def norm_col(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(c).lower())


def detect_col(df: pd.DataFrame, candidates: List[str], contains: Optional[List[str]] = None) -> Optional[str]:
    if df is None or df.empty:
        return None
    lookup = {norm_col(c): c for c in df.columns}
    for cand in candidates:
        key = norm_col(cand)
        if key in lookup:
            return lookup[key]
    if contains:
        terms = [norm_col(x) for x in contains]
        for c in df.columns:
            lc = norm_col(c)
            if all(t in lc for t in terms):
                return c
    return None


def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    return {
        "link": detect_col(df, [
            "Link", "URL", "TikTok Link", "TikTok URL", "TikTok Post URL",
            "Post URL", "Post Link", "Video URL", "Video Link", "Permalink",
            "Share URL", "webVideoUrl", "submittedVideoUrl", "itemWebUrl",
            "item_web_url", "tiktok_url",
        ]),
        "market": detect_col(df, ["Country", "Country Code", "Market", "Market Code", "Region", "Locale"]),
        "track": detect_col(df, [
            "Artist - Sound", "Artist-Sound", "Artist / Sound", "Track", "Sound",
            "Song", "Music", "Track Name", "Track Title", "Song Name",
            "Song Title", "Music Name", "Sound Name", "Audio Name",
        ]),
        "viral_date": detect_col(df, ["Viral Date", "2026 Viral Date", "First Viral Date", "Track Viral Date"]),
        "date": detect_col(df, ["Date", "Post Date", "Created Date", "Create Time", "Created At", "Published Date", "createTimeISO"]),
        "creator": detect_col(df, ["Username", "Creator", "Creator Username", "Author", "Author Username", "Handle", "Account", "User"]),
        "followers": detect_col(df, ["Followers", "Follower Count", "Followers Count", "Fans", "Fans Count", "authorMeta.fans", "authorMeta.fansCount", "fansCount"]),
        "kol_size": detect_col(df, ["KOL Size", "KOL", "Creator Size", "Influencer Size"]),
        "views": detect_col(df, ["Views", "Post Views", "Video Views", "View Count", "Plays", "Play Count", "playCount"]),
        "likes": detect_col(df, ["Likes", "Post Likes", "Video Likes", "Like Count", "diggCount"]),
        "comments": detect_col(df, ["Comments", "Post Comments", "Video Comments", "Comment Count", "commentCount"]),
        "shares": detect_col(df, ["Shares", "Post Shares", "Video Shares", "Share Count", "shareCount"]),
        "saves": detect_col(df, ["Saves", "Post Saves", "Video Saves", "Save Count", "Bookmarks", "Favorites", "Download Count", "Collect Count", "collectCount"]),
        "total_engagement": detect_col(df, ["Total Engagement", "Engagement", "Total Likes, Comments & Shares", "Likes Comments Shares"]),
    }


def standardize_file_rows(df: pd.DataFrame, source_name: str) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    cols = detect_columns(df)
    link_col = cols.get("link")
    if not link_col:
        return pd.DataFrame(), cols
    rows = []
    for _, r in df.iterrows():
        link = safe_str(r.get(link_col))
        if not is_tiktok_link(link):
            continue
        likes = clean_num(r.get(cols["likes"])) if cols.get("likes") else 0
        comments = clean_num(r.get(cols["comments"])) if cols.get("comments") else 0
        shares = clean_num(r.get(cols["shares"])) if cols.get("shares") else 0
        saves = clean_num(r.get(cols["saves"])) if cols.get("saves") else 0
        total_eng = clean_num(r.get(cols["total_engagement"])) if cols.get("total_engagement") else likes + comments + shares + saves
        rows.append({
            "Source": source_name,
            "Input Type": "CSV/XLSX",
            "Link": link,
            "Market": normalize_market(r.get(cols["market"])) if cols.get("market") else "",
            "Track": safe_str(r.get(cols["track"])) if cols.get("track") else "",
            "Viral Date": safe_str(r.get(cols["viral_date"])) if cols.get("viral_date") else "",
            "Date": safe_str(r.get(cols["date"])) if cols.get("date") else "",
            "Creator": safe_str(r.get(cols["creator"])) if cols.get("creator") else extract_creator(link),
            "Followers": clean_num(r.get(cols["followers"])) if cols.get("followers") else 0,
            "KOL Size": safe_str(r.get(cols["kol_size"])) if cols.get("kol_size") else "",
            "Views": clean_num(r.get(cols["views"])) if cols.get("views") else 0,
            "Likes": likes,
            "Comments": comments,
            "Shares": shares,
            "Saves": saves,
            "Total Engagement": total_eng,
        })
    out_df = add_performance_fields(pd.DataFrame(rows))
    if "QA Priority" not in out_df.columns:
        out_df["QA Priority"] = out_df.get("Needs Review", False).map(lambda x: "High" if bool(x) else "Low") if "Needs Review" in out_df.columns else "Low"
    if "QA Reason" not in out_df.columns:
        out_df["QA Reason"] = ""
    return out_df, cols


def append_to_batch(new_df: pd.DataFrame) -> Tuple[int, int]:
    if new_df is None or new_df.empty:
        return 0, 0
    old = st.session_state.batch_df.copy()
    before = len(old)
    combined = pd.concat([old, new_df], ignore_index=True) if not old.empty else new_df.copy()
    combined["_link_key"] = combined["Link"].astype(str).str.split("?").str[0].str.rstrip("/")
    combined = combined.drop_duplicates("_link_key", keep="first").drop(columns=["_link_key"])
    combined = add_performance_fields(combined)
    st.session_state.batch_df = combined.reset_index(drop=True)
    added = len(st.session_state.batch_df) - before
    skipped = len(new_df) - added
    return added, max(skipped, 0)


def render_table(df: pd.DataFrame, max_rows: int = 10, cols: Optional[List[str]] = None) -> str:
    if df is None or df.empty:
        return "<p class='sub'>No rows to show.</p>"
    show = df.copy()
    if cols:
        show = show[[c for c in cols if c in show.columns]]
    show = show.head(max_rows).copy()
    for col in show.columns:
        if col == "Track":
            show[col] = show[col].map(lambda x: display_empty(x, "Not specified"))
        elif col == "Market":
            show[col] = show[col].map(display_market)
        else:
            show[col] = show[col].map(lambda x, col=col: format_display_value(col, x))
    return "<div class='table-wrap'>" + show.to_html(index=False, escape=True, classes="clean-table") + "</div>"


def metric_row(items: List[Tuple[str, str, str]]) -> str:
    cards = []
    for label, value, hint in items:
        cards.append(f"<div class='metric-card'><div class='val'>{esc(value)}</div><div class='lbl'>{esc(label)}</div><div class='hint'>{esc(hint)}</div></div>")
    return "<div class='metric-row'>" + "".join(cards) + "</div>"


def step_strip(active: int):
    steps = [
        (1, "01", "API Keys", "Setup"),
        (2, "02", "Add Posts", "Files or links"),
        (3, "03", "Select Posts", "Top or all"),
        (4, "04", "Run Tagging", "Preview run"),
        (5, "05", "Review", "Check posts"),
        (6, "06", "Summary", "Dashboard & export"),
    ]
    html_out = "<div class='step-strip'>"
    for num, icon, title, desc in steps:
        cls = "step-card active" if num == active else ("step-card done" if num < active else "step-card")
        html_out += (
            f"<div class='{cls}'>"
            f"<div class='step-head'><span class='step-icon'>{icon}</span><span class='step-small'>Step {num}</span></div>"
            f"<div class='step-title'>{title}</div><div class='step-desc'>{desc}</div></div>"
        )
    html_out += "</div>"
    st.markdown(html_out, unsafe_allow_html=True)


def selected_posts_preview(batch: pd.DataFrame) -> pd.DataFrame:
    if batch.empty:
        return batch
    out = add_performance_fields(batch.copy())

    # Create display/helper columns for filtering. Blank market is grouped as Other.
    out["Market Display"] = out.get("Market", "").map(display_market) if "Market" in out.columns else "Other"
    out["Track Display"] = out.get("Track", "").map(lambda x: display_empty(x, "Not specified")) if "Track" in out.columns else "Not specified"
    out["Source Display"] = out.get("Source", "").map(lambda x: display_empty(x, "Unknown source")) if "Source" in out.columns else "Unknown source"

    selected_markets = st.session_state.get("select_markets", ["All"])
    if selected_markets and "All" not in selected_markets:
        out = out[out["Market Display"].isin(selected_markets)]

    selected_tracks = st.session_state.get("select_tracks", ["All"])
    if selected_tracks and "All" not in selected_tracks:
        out = out[out["Track Display"].isin(selected_tracks)]

    selected_sources = st.session_state.get("select_sources", ["All"])
    if selected_sources and "All" not in selected_sources:
        out = out[out["Source Display"].isin(selected_sources)]

    if st.session_state.get("use_date_filter"):
        parsed = out.apply(canonical_post_date, axis=1)
        window_days = int(st.session_state.get("date_window", 7))
        date_scope = st.session_state.get("date_filter_scope_v68", DATE_SCOPE_SHARED)
        if date_scope == DATE_SCOPE_PER_TRACK:
            out = filter_posts_by_date_window_v68(
                out,
                parsed,
                window_days,
                track_settings=st.session_state.get("track_date_settings_v68", {}),
            )
        else:
            out = filter_posts_by_date_window_v68(
                out,
                parsed,
                window_days,
                global_date=st.session_state.get("viral_date"),
            )

    if out.empty:
        return out.reset_index(drop=True)

    if st.session_state.get("selection_mode", "Top posts") == "Tag every link":
        return out.reset_index(drop=True)

    n = int(st.session_state.get("top_n", min(20, len(out))))
    rank_metrics = st.session_state.get("rank_metrics", None)
    if not rank_metrics:
        # Backward compatible fallback if older state still has rank_by.
        rank_metrics = [st.session_state.get("rank_by", "Total Engagement")]
    if isinstance(rank_metrics, str):
        rank_metrics = [rank_metrics]

    valid_metrics = []
    for metric in rank_metrics:
        if metric == "Engagement Rate":
            out["Engagement Rate"] = out.apply(calculate_engagement_rate, axis=1)
            valid_metrics.append(metric)
        elif metric in out.columns:
            out[metric] = out[metric].map(clean_num)
            valid_metrics.append(metric)

    if not valid_metrics:
        valid_metrics = ["Total Engagement"]
        if "Total Engagement" not in out.columns:
            out["Total Engagement"] = 0
        out["Total Engagement"] = out["Total Engagement"].map(clean_num)

    def sort_and_take(df_part: pd.DataFrame) -> pd.DataFrame:
        return df_part.sort_values(valid_metrics, ascending=[False] * len(valid_metrics)).head(n)

    group_by = st.session_state.get("group_by", "No grouping")
    group_map = {
        "Market": ["Market Display"],
        "Track": ["Track Display"],
        "Source": ["Source Display"],
        "Market + Track": ["Market Display", "Track Display"],
    }
    group_cols = group_map.get(group_by, [])

    if group_cols:
        pieces = []
        for _, g in out.groupby(group_cols, dropna=False, sort=True):
            pieces.append(sort_and_take(g))
        if not pieces:
            return out.iloc[0:0].reset_index(drop=True)
        return pd.concat(pieces, ignore_index=True).reset_index(drop=True)

    return sort_and_take(out).reset_index(drop=True)


def _extract_tiktok_id_from_url(url: str) -> str:
    s = safe_str(url)
    m = re.search(r"/(?:video|photo)/(\d+)", s)
    return m.group(1) if m else ""


def _normalize_tiktok_url(url: str) -> str:
    s = safe_str(url).split("?")[0].rstrip("/")
    s = s.replace("http://", "https://").replace("https://m.tiktok.com/", "https://www.tiktok.com/")
    return s


def _apify_scrape_links_v43(links: List[str], apify_token: str) -> List[Dict]:
    try:
        from apify_client import ApifyClient
    except Exception as e:
        raise RuntimeError("Missing dependency: install with `pip install apify-client`.") from e
    apify_token = clean_api_secret(apify_token)
    if not apify_token:
        raise RuntimeError("Missing Apify token.")
    clean_links = [safe_str(x) for x in links if is_tiktok_link(x)]
    if not clean_links:
        return []
    client = ApifyClient(apify_token)
    run_input = {
        "postURLs": clean_links,
        "resultsPerPage": len(clean_links),
        "shouldDownloadVideos": True,
        "shouldDownloadCovers": True,
        "shouldDownloadSlideshowImages": True,
        "shouldDownloadAvatars": False,
        "shouldDownloadMusicCovers": False,
        "downloadSubtitlesOptions": "NEVER_DOWNLOAD_SUBTITLES",
        "commentsPerPost": 0,
        "topLevelCommentsPerPost": 0,
        "maxRepliesPerComment": 0,
        "excludePinnedPosts": False,
        "proxyCountryCode": "None",
    }
    run = client.actor("clockworks/tiktok-scraper").call(run_input=run_input)
    dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else getattr(run, "defaultDatasetId", None)
    if not dataset_id and not isinstance(run, dict):
        dataset_id = getattr(run, "default_dataset_id", None)
    if not dataset_id and isinstance(run, dict):
        dataset_id = run.get("default_dataset_id")
    if not dataset_id:
        raise RuntimeError("Apify run finished but no default dataset was returned.")
    return list(client.dataset(dataset_id).iterate_items())


def _nested_get(d: Dict, dotted: str, default=""):
    cur = d if isinstance(d, dict) else {}
    for part in dotted.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def _first_nonblank_v43(*vals):
    for v in vals:
        s = safe_str(v)
        if s and s.lower() not in {"nan", "none", "null"}:
            return s
    return ""


def _record_public_url(rec: Dict) -> str:
    return _first_nonblank_v43(rec.get("webVideoUrl"), rec.get("submittedVideoUrl"), rec.get("url"), rec.get("inputUrl"))


def _walk_urls_v48(obj):
    """Collect URL-like strings from nested Apify records without assuming schema."""
    urls = []
    if isinstance(obj, dict):
        for v in obj.values():
            urls.extend(_walk_urls_v48(v))
    elif isinstance(obj, list):
        for v in obj:
            urls.extend(_walk_urls_v48(v))
    else:
        s = safe_str(obj)
        if s.startswith("http://") or s.startswith("https://"):
            urls.append(s)
        elif s.startswith("//"):
            urls.append("https:" + s)
    return urls


def _looks_like_image_url_v48(url: str) -> bool:
    u = safe_str(url).lower()
    image_tokens = ["cover", "thumbnail", "thumb", "image", "photo", "jpg", "jpeg", "png", "webp", "heic", "jpeg"]
    video_tokens = [".mp4", "video/mp4", "downloadaddr", "playaddr"]
    return any(t in u for t in image_tokens) and not any(t in u for t in video_tokens)


def _looks_like_video_url_v48(url: str) -> bool:
    u = safe_str(url).lower()
    video_tokens = [".mp4", "video", "media", "downloadaddr", "playaddr", "playwm"]
    image_tokens = ["cover", "thumbnail", "thumb", "image", "photo", ".jpg", ".jpeg", ".png", ".webp"]
    return any(t in u for t in video_tokens) and not any(t in u for t in image_tokens)


def _record_cover_url(rec: Dict) -> str:
    """Best-effort cover/thumbnail URL from Apify result.

    Apify/TikTok schemas vary by post type and actor version. v48 checks the known
    fields first, then scans nested record values for image-like URLs. This fixes
    review previews for rows where the cover is returned under a different key.
    """
    image_candidates = []
    for key in [
        "videoMeta.originalCoverUrl", "videoMeta.coverUrl", "videoMeta.dynamicCoverUrl",
        "videoMeta.thumbnailUrl", "videoMeta.thumbnail", "videoMeta.imageUrl",
        "videoMeta.videoCover", "videoMeta.originCover", "videoMeta.cover",
        "itemStruct.video.cover", "itemStruct.video.originCover", "itemStruct.video.dynamicCover",
    ]:
        image_candidates.append(_nested_get(rec, key))
    for key in [
        "coverUrl", "thumbnailUrl", "thumbnail", "thumb", "image", "imageUrl",
        "displayUrl", "downloadedCoverUrl", "downloadedThumbnailUrl", "cover",
    ]:
        image_candidates.append(rec.get(key))
    for list_key in [
        "slideshowImageUrls", "imageUrls", "images", "photoUrls", "photos",
        "downloadedSlideshowImageUrls", "downloadedImages", "imagePost", "imagePost.images",
    ]:
        vals = _nested_get(rec, list_key) if "." in list_key else rec.get(list_key)
        if isinstance(vals, list) and vals:
            first = vals[0]
            if isinstance(first, dict):
                image_candidates.extend([first.get("url"), first.get("downloadUrl"), first.get("src"), first.get("imageUrl"), first.get("displayUrl")])
            else:
                image_candidates.append(first)
    direct = _first_nonblank_v43(*image_candidates)
    if direct:
        return direct
    for url in _walk_urls_v48(rec):
        if _looks_like_image_url_v48(url):
            return url
    return ""


def _record_video_url(rec: Dict) -> str:
    media = rec.get("mediaUrls") if isinstance(rec.get("mediaUrls"), list) else []
    candidates = [
        media[0] if media else "",
        _nested_get(rec, "videoMeta.downloadAddr"),
        _nested_get(rec, "videoMeta.playAddr"),
        _nested_get(rec, "videoMeta.videoUrl"),
        _nested_get(rec, "itemStruct.video.downloadAddr"),
        _nested_get(rec, "itemStruct.video.playAddr"),
        rec.get("videoUrl"),
        rec.get("downloadUrl"),
        rec.get("downloadedVideoUrl"),
        rec.get("mediaUrl"),
    ]
    direct = _first_nonblank_v43(*candidates)
    if direct:
        return direct
    for url in _walk_urls_v48(rec):
        if _looks_like_video_url_v48(url):
            return url
    return ""


def _apify_url_with_token_v48(url: str, apify_token: str = "") -> str:
    if not url or not apify_token or "api.apify.com" not in url or "token=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={apify_token}"


def _is_probably_image_bytes_v48(content: bytes, content_type: str = "") -> bool:
    if not content or len(content) < 100:
        return False
    ct = safe_str(content_type).lower()
    if "image" in ct:
        return True
    return (
        content.startswith(b"\xff\xd8\xff") or  # jpg
        content.startswith(b"\x89PNG") or
        content.startswith(b"RIFF") or            # webp
        content.startswith(b"GIF")
    )


@st.cache_data(show_spinner=False, ttl=3600)
def _download_image_for_display_v45(url: str, apify_token: str = "") -> bytes:
    """Download protected/public cover images for st.image display.

    v48 tries both Bearer auth and ?token= auth for Apify key-value-store URLs.
    """
    url = safe_str(url)
    if not url:
        return b""
    if url.startswith("//"):
        url = "https:" + url
    headers_list = [{}]
    urls = [url]
    if "api.apify.com" in url and apify_token:
        headers_list = [{"Authorization": f"Bearer {apify_token}"}, {}]
        urls = [url, _apify_url_with_token_v48(url, apify_token)]
    for u in urls:
        for headers in headers_list:
            try:
                r = requests.get(u, headers=headers, timeout=30)
                r.raise_for_status()
                content = r.content or b""
                if _is_probably_image_bytes_v48(content, r.headers.get("content-type", "")):
                    return content
            except Exception:
                continue
    return b""


@st.cache_data(show_spinner=False, ttl=3600)
def _tiktok_oembed_thumbnail_bytes_v48(link: str) -> bytes:
    """Last-resort public TikTok thumbnail via oEmbed.

    This is not used for tagging, only for review-page convenience when Apify does
    not return a displayable cover image.
    """
    link = safe_str(link)
    if not link:
        return b""
    try:
        r = requests.get("https://www.tiktok.com/oembed", params={"url": link}, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        thumb = safe_str((r.json() or {}).get("thumbnail_url"))
        if not thumb:
            return b""
        img = requests.get(thumb, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        img.raise_for_status()
        content = img.content or b""
        return content if _is_probably_image_bytes_v48(content, img.headers.get("content-type", "")) else b""
    except Exception:
        return b""


@st.cache_data(show_spinner=False, ttl=3600)
def _video_frame_preview_bytes_v45(video_url: str, apify_token: str = "") -> bytes:
    """Fallback: download the video and extract a middle frame for review preview."""
    video_url = safe_str(video_url)
    if not video_url:
        return b""
    try:
        import cv2
    except Exception:
        return b""
    if video_url.startswith("//"):
        video_url = "https:" + video_url
    urls = [video_url]
    headers_list = [{}]
    if "api.apify.com" in video_url and apify_token:
        urls = [video_url, _apify_url_with_token_v48(video_url, apify_token)]
        headers_list = [{"Authorization": f"Bearer {apify_token}"}, {}]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            vp = os.path.join(tmp, "video.mp4")
            downloaded = False
            for u in urls:
                for headers in headers_list:
                    try:
                        with requests.get(u, headers=headers, timeout=90, stream=True) as r:
                            r.raise_for_status()
                            with open(vp, "wb") as f:
                                for chunk in r.iter_content(chunk_size=1024 * 256):
                                    if chunk:
                                        f.write(chunk)
                        if os.path.getsize(vp) > 1000:
                            downloaded = True
                            break
                    except Exception:
                        continue
                if downloaded:
                    break
            if not downloaded:
                return b""
            cap = cv2.VideoCapture(vp)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total <= 0:
                cap.release()
                return b""
            # Try a few positions in case the selected frame is black/invalid.
            for pct in [0.25, 0.35, 0.50, 0.65]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(total - 1, int(total * pct))))
                ok, frame = cap.read()
                if ok:
                    ok2, buf = cv2.imencode(".jpg", frame)
                    cap.release()
                    return bytes(buf) if ok2 else b""
            cap.release()
            return b""
    except Exception:
        return b""


def _render_run_log_v45(placeholder, logs: List[str]) -> None:
    """Readable progress log; avoids Streamlit code block dark-on-dark issue."""
    shown = logs[-10:]
    lines = []
    for line in shown:
        safe = esc(line)
        safe = re.sub(r"^(\d+/\d+):", r"<span class='idx'>\1:</span>", safe)
        safe = safe.replace("→", "<span class='arrow'>→</span>")
        lines.append(safe)
    placeholder.markdown("<div class='v45-run-log'>" + "<br>".join(lines) + "</div>", unsafe_allow_html=True)


def _render_review_preview_v45(image_url: str, video_url: str, link: str, apify_token: str = "") -> None:
    """Render TikTok preview from cover, video frame, or public oEmbed thumbnail."""
    preview_bytes = _download_image_for_display_v45(image_url, apify_token) if image_url else b""
    if not preview_bytes and video_url:
        preview_bytes = _video_frame_preview_bytes_v45(video_url, apify_token)
    if not preview_bytes and link:
        preview_bytes = _tiktok_oembed_thumbnail_bytes_v48(link)
    st.markdown("<div class='review-media-card'>", unsafe_allow_html=True)
    if preview_bytes:
        st.image(preview_bytes, width="stretch")
    else:
        st.markdown("<div class='review-placeholder'>Preview unavailable<br><span style='font-size:12px;color:#64748b'>Open TikTok to review this post.</span></div>", unsafe_allow_html=True)
    if link:
        st.markdown(f"<a class='review-tiktok-btn' href='{esc(link)}' target='_blank'>▶ Watch on TikTok</a>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _record_to_metrics(rec: Dict) -> Dict:
    author = rec.get("authorMeta") if isinstance(rec.get("authorMeta"), dict) else {}
    music = rec.get("musicMeta") if isinstance(rec.get("musicMeta"), dict) else {}
    url = _record_public_url(rec)
    followers = clean_num(author.get("fans") or author.get("followers") or author.get("fansCount") or 0)
    market = _first_nonblank_v43(rec.get("locationCreated"), "")
    return {
        "Link": url,
        "Creator": _first_nonblank_v43(author.get("name"), author.get("nickName"), extract_creator(url)),
        "Caption": safe_str(rec.get("text") or rec.get("caption")),
        "Track From TikTok": _first_nonblank_v43(music.get("musicName"), rec.get("musicName")),
        "Artist From TikTok": _first_nonblank_v43(music.get("musicAuthor"), rec.get("musicAuthor")),
        "Views": clean_num(rec.get("playCount")),
        "Likes": clean_num(rec.get("diggCount")),
        "Comments": clean_num(rec.get("commentCount")),
        "Shares": clean_num(rec.get("shareCount")),
        "Saves": clean_num(rec.get("collectCount")),
        "Followers": followers,
        "KOL Size": kol_size_for_market(followers, market),
        "Is Slideshow": bool(rec.get("isSlideshow", False)),
        "Cover URL": _record_cover_url(rec),
        "Video URL": _record_video_url(rec),
        "Raw Apify Status": _first_nonblank_v43(rec.get("error"), rec.get("errorCode"), "OK"),
    }


def _build_prompt_v43(meta: Dict) -> str:
    labels = ", ".join(CREATIVE_TYPES)
    return f"""
You are classifying TikTok UGC creative type for music marketing.
Return ONLY valid JSON with these keys:
{{"narrative":"short phrase", "creative_type":["one or two labels"], "content_details":"one sentence", "confidence":0.0, "reasoning":"short reason"}}

Allowed Creative Type labels: {labels}

Rules:
- Use 1 or 2 labels only.
- If it is a slideshow/photo carousel, include Carousel.
- Dance requires choreography/body movement.
- Lip Sync is mouthing/singing to audio with little choreography.
- Lyrics requires visible lyric text as the main content.
- Beauty is makeup/skincare/hair/nails.
- Fashion is outfit/clothing styling.
- Relationship is romance/partner/love/heartbreak.
- Media/Infotainment is informative, news, tutorial, review, explainer.
- Movie/Tv/Drama Edits is fictional drama/movie/anime/series scenes.
- Celebrity Edits is real idol/celebrity/public figure edits.
- If unsure, use Others with low confidence.

Post metadata:
Historical KB hint: {', '.join(_creative_kb_hint_v44(meta)[1][:2]) or 'No strong KB hint'}
Caption: {meta.get('Caption','')}
Creator: {meta.get('Creator','')}
Track: {meta.get('Track','')}
TikTok music: {meta.get('Track From TikTok','')} - {meta.get('Artist From TikTok','')}
Is slideshow: {meta.get('Is Slideshow', False)}
Views: {meta.get('Views',0)} Likes: {meta.get('Likes',0)} Shares: {meta.get('Shares',0)} Saves: {meta.get('Saves',0)}
""".strip()


def _download_cover_bytes_v43(url: str, apify_token: str) -> bytes:
    if not url:
        return b""
    headers = {"Authorization": f"Bearer {apify_token}"} if "api.apify.com" in url and apify_token else {}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.content


def _call_gemini_v43(prompt: str, cover_url: str, gemini_key: str, apify_token: str) -> Dict:
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return {"parse_error": True, "raw_response": f"Missing google-genai: {e}"}
    try:
        client = genai.Client(api_key=gemini_key)
        contents = [prompt]
        try:
            img = _download_cover_bytes_v43(cover_url, apify_token) if cover_url else b""
        except Exception:
            img = b""
        if img:
            contents.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = response.text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"```$", "", text).strip()
        return json.loads(text)
    except Exception as e:
        return {"parse_error": True, "raw_response": str(e)}


def _normalize_ai_result_v43(result: Dict) -> Dict:
    """Normalize Gemini JSON without writing fake final content.

    Important export/review rule:
    - If Gemini cannot classify, parse fails, returns Others, or returns no content details,
      the row must go to human review.
    - Do NOT fill final Content Details with placeholders like
      "AI could not confidently classify this post". Keep it blank so the reviewer
      knows it still needs a real human-written description.
    """
    if not isinstance(result, dict) or result.get("parse_error"):
        return {
            "Narrative": "",
            "Creative Type": "Others",
            "Content Details": "",
            "Confidence": 0.0,
            "Reasoning": safe_str(result.get("raw_response") if isinstance(result, dict) else result),
            "Needs Review": True,
            "Review Note": "AI parse/API issue. Please review manually.",
        }

    labels = result.get("creative_type", [])
    if isinstance(labels, str):
        labels = [labels]
    labels = [safe_str(x) for x in labels if safe_str(x) in CREATIVE_TYPES]
    if not labels:
        labels = ["Others"]

    try:
        conf = float(result.get("confidence", 0) or 0)
    except Exception:
        conf = 0.0

    content_details = safe_str(result.get("content_details"))
    narrative = safe_str(result.get("narrative"))
    needs_review = bool(conf < 0.72 or labels[0] == "Others" or not content_details)
    review_reasons = []
    if conf < 0.72:
        review_reasons.append("Low confidence")
    if labels[0] == "Others":
        review_reasons.append("Unclear / Others label")
    if not content_details:
        review_reasons.append("Missing content details")

    return {
        "Narrative": narrative if narrative else ("" if needs_review else labels[0]),
        "Creative Type": ", ".join(labels[:2]),
        "Content Details": content_details,
        "Confidence": conf,
        "Reasoning": safe_str(result.get("reasoning")),
        "Needs Review": needs_review,
        "Review Note": " / ".join(review_reasons) + (". Please review manually." if review_reasons else ""),
    }



# -----------------------------
# Phase 2: Creative KB + guardrails + lightweight Tier 2
# -----------------------------
CREATIVE_KB_DIR = "creative_knowledge"

@st.cache_data(show_spinner=False)
def _load_creative_kb_v44(base_dir: str = CREATIVE_KB_DIR) -> Dict:
    """Load optional Creative KB beside this app.

    The KB is pattern memory only. It stores creator/track/market/keyword tendencies,
    not exact TikTok URL -> label memorisation.
    """
    kb = {}
    for name in ["metadata", "creator_rules", "hashtag_rules", "url_type_rules", "market_rules", "track_rules", "keyword_rules"]:
        path = os.path.join(base_dir, f"{name}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                kb[name] = json.load(f)
        except Exception:
            kb[name] = {}
    return kb


def _kb_slug_v44(v) -> str:
    s = safe_str(v).lower().strip().lstrip("#@")
    return re.sub(r"[^a-z0-9_.\-ก-๙\u0e00-\u0e7f\u4e00-\u9fff가-힣ぁ-んァ-ン]+", "", s)


def _labels_from_ai_v44(ai: Dict) -> List[str]:
    labels = []
    for x in safe_str(ai.get("Creative Type", "")).split(','):
        x = x.strip()
        if x in CREATIVE_TYPES and x not in labels:
            labels.append(x)
    return labels or ["Others"]


def _set_labels_v44(ai: Dict, labels: List[str], note: str = "") -> Dict:
    clean = []
    for x in labels:
        if x in CREATIVE_TYPES and x not in clean:
            clean.append(x)
    if not clean:
        clean = ["Others"]
    ai["Creative Type"] = ", ".join(clean[:2])
    if note:
        old = safe_str(ai.get("Reasoning"))
        ai["Reasoning"] = (old + " | " + note).strip(" |")
    return ai


def _row_text_blob_v44(ai: Dict, meta: Dict) -> str:
    parts = [
        ai.get("Narrative", ""), ai.get("Creative Type", ""), ai.get("Content Details", ""), ai.get("Reasoning", ""),
        meta.get("Caption", ""), meta.get("Creator", ""), meta.get("Track", ""),
        meta.get("Track From TikTok", ""), meta.get("Artist From TikTok", ""), meta.get("Market", ""),
    ]
    return " ".join(safe_str(x) for x in parts).lower()


def _has_any_v44(blob: str, words: List[str]) -> bool:
    return any(w in blob for w in words)


def _creative_kb_hint_v44(meta: Dict) -> Tuple[List[str], List[str]]:
    """Return (suggested_labels, evidence) from strong KB signals."""
    kb = _load_creative_kb_v44()
    evidence = []
    candidates = []

    creator = _kb_slug_v44(meta.get("Creator") or extract_creator(meta.get("Link", "")))
    track = _kb_slug_v44(meta.get("Track") or meta.get("Track From TikTok"))
    market = display_market(meta.get("Market")) if safe_str(meta.get("Market")) else ""

    def add_rule(section, key, label, min_conf, min_total=2):
        if not key:
            return
        rule = (kb.get(section) or {}).get(key, {})
        if not isinstance(rule, dict):
            return
        conf = float(rule.get("confidence", 0) or 0)
        total = int(rule.get("total", rule.get("count", 0)) or 0)
        labels = rule.get("preferred_creative_type") or rule.get("preferred_tag") or []
        if isinstance(labels, str):
            labels = [labels]
        labels = [x for x in labels if x in CREATIVE_TYPES]
        if labels and conf >= min_conf and total >= min_total:
            candidates.append((labels, conf, total, label))
            evidence.append(f"{label}: {', '.join(labels)} ({conf:.2f}, n={total})")

    add_rule("creator_rules", creator, f"creator {creator}", 0.75, 2)
    add_rule("track_rules", track, f"track {track}", 0.78, 5)
    # Market rules are weak context only; require high confidence to avoid one-market overfitting.
    add_rule("market_rules", market, f"market {market}", 0.70, 20)

    blob = _row_text_blob_v44({"Narrative":"", "Creative Type":"", "Content Details":"", "Reasoning":""}, meta)
    for key, rule in (kb.get("keyword_rules") or {}).items():
        if key and key in blob:
            try:
                conf = float(rule.get("confidence", 0) or 0)
                total = int(rule.get("total", rule.get("count", 0)) or 0)
            except Exception:
                continue
            labels = rule.get("preferred_creative_type") or []
            if isinstance(labels, str):
                labels = [labels]
            labels = [x for x in labels if x in CREATIVE_TYPES]
            if labels and conf >= 0.82 and total >= 10:
                candidates.append((labels, conf, total, f"keyword {key}"))
                evidence.append(f"keyword {key}: {', '.join(labels)} ({conf:.2f}, n={total})")
                break

    if not candidates:
        return [], evidence
    candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return candidates[0][0], evidence



def _apply_consistency_soft_audit_v46(ai: Dict, meta: Dict) -> Dict:
    """Soft label-vs-description audit.

    This does not force manual review for every conflict. It adds QA fields so the
    Review / QA Report can surface suspicious rows without reducing automation.
    """
    ai = dict(ai)
    labels = _labels_from_ai_v44(ai)
    blob = _row_text_blob_v44(ai, meta)
    issues = []
    dance_cues = ["dance", "dancing", "choreo", "choreography", "dance challenge", "body movement", "full-body", "full body", "synchronized", "routine"]
    non_dance_cues = ["skincare", "makeup", "lashes", "eyelash", "outfit", "fit check", "static text", "text card", "quote", "lyrics", "lyric", "caption idea", "meme", "rant", "annoyed", "frustration"]
    if "Dance" in labels and not _has_any_v44(blob, dance_cues) and _has_any_v44(blob, non_dance_cues):
        issues.append("Dance label has weak choreography support while description suggests non-dance content.")
    if "Carousel" in labels and not bool(meta.get("Is Slideshow")) and "/photo/" not in safe_str(meta.get("Link", "")).lower():
        # Carousel can be a content style, but for normal videos it should be sampled in QA.
        issues.append("Carousel label used on a non-photo/non-slideshow post; verify format.")
    if labels == ["Others"]:
        issues.append("Creative Type is Others.")
    if issues:
        ai["QA Priority"] = "Medium" if not ai.get("Needs Review") else "High"
        ai["QA Reason"] = " ".join(issues)
        if not safe_str(ai.get("Review Note")):
            ai["Review Note"] = ai["QA Reason"] if ai.get("Needs Review") else ""
    else:
        ai.setdefault("QA Priority", "Low")
        ai.setdefault("QA Reason", "")
    return ai

def _apply_guardrails_and_kb_v44(ai: Dict, meta: Dict) -> Dict:
    """Use Gemini description + KB to correct obvious label errors without over-forcing review."""
    ai = dict(ai)
    labels = _labels_from_ai_v44(ai)
    blob = _row_text_blob_v44(ai, meta)

    lyric_cues = ["lyrics", "lyric", "karaoke", "spotify lyrics", "on-screen text", "onscreen text", "lyric text", "translated lyrics", "bilingual lyrics"]
    dance_cues = ["dance", "dancing", "choreo", "choreography", "dance challenge", "routine", "synchronized", "body movement", "hand gesture", "full-body", "full body"]
    beauty_cues = ["skincare", "makeup", "cosmetic", "lashes", "eyelash", "hair", "nail", "lipstick", "beauty routine"]
    fashion_cues = ["outfit", "ootd", "fit check", "clothing", "fashion", "dress", "styling", "lookbook"]
    comedy_cues = ["funny", "joke", "meme", "comedy", "frustration", "annoyed", "annoyance", "rant", "skit", "relatable"]
    relationship_cues = ["boyfriend", "girlfriend", "single", "relationship", "couple", "crush", "romantic", "love", "heartbreak"]
    quote_cues = ["quote", "caption idea", "text card", "motivational", "advice", "saying"]

    # Carousel format should be added for real slideshow/photo posts.
    if bool(meta.get("Is Slideshow")) and "Carousel" not in labels:
        labels = ["Carousel"] + [x for x in labels if x != "Carousel"]
        ai = _set_labels_v44(ai, labels[:2], "Guardrail: slideshow/photo format detected, Carousel included.")
        labels = _labels_from_ai_v44(ai)

    # Visible lyrics should beat Dance unless real choreography is also described.
    if _has_any_v44(blob, lyric_cues) and not _has_any_v44(blob, dance_cues):
        target = "Lyrics Translation" if "translated" in blob or "bilingual" in blob else "Lyrics"
        if "Dance" in labels or labels == ["Others"]:
            ai = _set_labels_v44(ai, [target], "Guardrail: visible lyric/text content is not Dance.")
            labels = _labels_from_ai_v44(ai)

    # Obvious not-Dance guard: useful for skincare/comedy/fashion/static content.
    if "Dance" in labels and not _has_any_v44(blob, dance_cues):
        if _has_any_v44(blob, beauty_cues):
            new = ["Beauty"]
            if _has_any_v44(blob, comedy_cues):
                new.append("Comedy")
            ai = _set_labels_v44(ai, new, "Guardrail: Beauty/skincare cues with no choreography, so Dance blocked.")
            labels = _labels_from_ai_v44(ai)
        elif _has_any_v44(blob, fashion_cues):
            ai = _set_labels_v44(ai, ["Fashion"], "Guardrail: outfit/fashion cues with no choreography, so Dance blocked.")
            labels = _labels_from_ai_v44(ai)
        elif _has_any_v44(blob, quote_cues):
            ai = _set_labels_v44(ai, ["Quotes"], "Guardrail: quote/text-card cues with no choreography, so Dance blocked.")
            labels = _labels_from_ai_v44(ai)

    # Some semantic shortcuts from the description itself.
    if labels == ["Others"]:
        if _has_any_v44(blob, beauty_cues):
            ai = _set_labels_v44(ai, ["Beauty"], "Guardrail: Beauty cues detected.")
        elif _has_any_v44(blob, fashion_cues):
            ai = _set_labels_v44(ai, ["Fashion"], "Guardrail: Fashion cues detected.")
        elif _has_any_v44(blob, relationship_cues):
            ai = _set_labels_v44(ai, ["Relationship"], "Guardrail: Relationship cues detected.")
        elif _has_any_v44(blob, comedy_cues):
            ai = _set_labels_v44(ai, ["Comedy"], "Guardrail: Comedy cues detected.")

    # Market-specific feature guardrails. These are intentionally scoped and feature-based,
    # not exact URL memorisation. They mostly add a second label or rescue repeated safe cases.
    labels = _labels_from_ai_v44(ai)
    label_set = set(labels)
    market_code = display_market(meta.get("Market")).upper()

    def add_or_rescue(label: str, note: str, force: bool = False):
        nonlocal ai, labels, label_set
        if label not in CREATIVE_TYPES:
            return
        if label in label_set:
            return
        if force or labels == ["Others"]:
            base = [label]
            if "Carousel" in label_set and label != "Carousel":
                base = ["Carousel", label]
            ai = _set_labels_v44(ai, base[:2], note)
        elif len(labels) == 1:
            ai = _set_labels_v44(ai, labels + [label], note)
        labels = _labels_from_ai_v44(ai)
        label_set = set(labels)

    lip_sync_cues = ["lip sync", "lipsync", "mouthing", "mouth", "singing along", "close-up", "close up", "filter challenge"]
    pov_cues = ["pov", "point of view", "first-person", "first person", "viewer perspective", "scenario"]
    slice_cues = ["daily", "everyday", "family", "food", "cafe", "school", "campus", "pet", "wedding", "baby", "meal", "home", "casual"]
    travel_cues = ["travel", "trip", "vacation", "snow", "winter", "beach", "scenery", "city view", "mountain"]
    fitness_cues = ["fitness", "gym", "workout", "sport", "athlete", "running", "training", "flex"]

    if market_code == "PH":
        if _has_any_v44(blob, lyric_cues) and not _has_any_v44(blob, dance_cues):
            add_or_rescue("Lyrics Translation" if "translated" in blob or "bilingual" in blob else "Lyrics", "PH guardrail: visible lyric/text content protected from Dance.", force=True)
        if _has_any_v44(blob, quote_cues + ["static text", "text overlay", "caption ideas", "caption idea"]):
            add_or_rescue("Quotes", "PH guardrail: static/text-overlay quote cues detected.", force=(labels == ["Carousel"] or labels == ["Others"]))
        if "Dance" in label_set and not _has_any_v44(blob, dance_cues) and _has_any_v44(blob, lip_sync_cues):
            ai = _set_labels_v44(ai, ["Lip Sync"], "PH guardrail: close-up/lip-sync cues with no choreography, so Dance was softened.")
            labels = _labels_from_ai_v44(ai); label_set = set(labels)

    elif market_code == "KR":
        if _has_any_v44(blob, dance_cues) and not _has_any_v44(blob, lyric_cues + beauty_cues + quote_cues):
            add_or_rescue("Dance", "KR guardrail: choreography/performance cue detected.", force=(labels == ["Others"]))

    elif market_code == "TH":
        if _has_any_v44(blob, dance_cues):
            add_or_rescue("Dance", "TH guardrail: dance/movement cue detected.")
        if _has_any_v44(blob, pov_cues):
            add_or_rescue("POV", "TH guardrail: POV/scenario cue detected.")
        if _has_any_v44(blob, comedy_cues):
            add_or_rescue("Comedy", "TH guardrail: playful/comedy cue detected.")
        if "Dance" in label_set and not _has_any_v44(blob, dance_cues) and _has_any_v44(blob, slice_cues):
            add_or_rescue("Slice of Life", "TH guardrail: casual/everyday scene cue detected.")

    elif market_code == "MY":
        if _has_any_v44(blob, relationship_cues):
            add_or_rescue("Relationship", "MY guardrail: relationship/romantic cue detected.")
        if _has_any_v44(blob, quote_cues + ["advice", "text overlay", "caption idea"]):
            add_or_rescue("Quotes", "MY guardrail: quote/advice/text cue detected.")
        if _has_any_v44(blob, comedy_cues):
            add_or_rescue("Comedy", "MY guardrail: humour/playful cue detected.")
        if _has_any_v44(blob, travel_cues):
            add_or_rescue("Travel", "MY guardrail: travel/scenery cue detected.")
        if _has_any_v44(blob, lip_sync_cues) and "Dance" in label_set and not _has_any_v44(blob, dance_cues):
            ai = _set_labels_v44(ai, ["Lip Sync"], "MY guardrail: lip-sync cue with weak choreography.")
            labels = _labels_from_ai_v44(ai); label_set = set(labels)

    elif market_code == "SG":
        if _has_any_v44(blob, beauty_cues):
            add_or_rescue("Beauty", "SG guardrail: beauty/skincare cue detected.")
        if _has_any_v44(blob, fashion_cues):
            add_or_rescue("Fashion", "SG guardrail: outfit/fashion cue detected.")
        if _has_any_v44(blob, relationship_cues):
            add_or_rescue("Relationship", "SG guardrail: relationship/couple cue detected.")
        if _has_any_v44(blob, comedy_cues):
            add_or_rescue("Comedy", "SG guardrail: comedy/frustration cue detected.")
        if _has_any_v44(blob, quote_cues):
            add_or_rescue("Quotes", "SG guardrail: quote/text cue detected.")

    elif market_code == "VN":
        if _has_any_v44(blob, ["translation", "translated", "bilingual", "vietnamese", "english subtitles"]):
            add_or_rescue("Lyrics Translation", "VN guardrail: translated/bilingual lyric cue detected.", force=(labels == ["Lyrics"] or labels == ["Others"]))
        if _has_any_v44(blob, lip_sync_cues):
            add_or_rescue("Lip Sync", "VN guardrail: lip-sync/performance cue detected.")
        if _has_any_v44(blob, pov_cues + ["scooter", "riding", "bouquet", "first person"]):
            add_or_rescue("POV", "VN guardrail: first-person/POV scenario cue detected.")
        if _has_any_v44(blob, quote_cues + ["phone call", "insecurity", "text overlay"]):
            add_or_rescue("Quotes", "VN guardrail: static text/quote cue detected.")
        if _has_any_v44(blob, slice_cues):
            add_or_rescue("Slice of Life", "VN guardrail: everyday/family/food/casual scene cue detected.")
        if _has_any_v44(blob, comedy_cues):
            add_or_rescue("Comedy", "VN guardrail: playful/skit/meme cue detected.")
        if _has_any_v44(blob, relationship_cues):
            add_or_rescue("Relationship", "VN guardrail: romantic/couple cue detected.")
        if _has_any_v44(blob, travel_cues):
            add_or_rescue("Travel", "VN guardrail: scenery/destination cue detected.")
        if _has_any_v44(blob, fitness_cues):
            add_or_rescue("Fitness", "VN guardrail: sport/fitness cue detected.")

    # KB should support weak labels, not blindly override strong current description.
    kb_labels, kb_evidence = _creative_kb_hint_v44(meta)
    labels = _labels_from_ai_v44(ai)
    if kb_labels:
        weak_current = labels == ["Others"] or float(ai.get("Confidence", 0) or 0) < 0.68
        kr_dance_recovery = display_market(meta.get("Market")) == "KR" and "Dance" in kb_labels and labels[0] in {"Lip Sync", "Fashion", "Beauty", "Celebrity Edits", "Slice of Life"}
        if weak_current:
            ai = _set_labels_v44(ai, kb_labels, "KB support: " + "; ".join(kb_evidence[:2]))
        elif kr_dance_recovery and "Dance" not in labels and not _has_any_v44(blob, lyric_cues + beauty_cues + quote_cues):
            ai = _set_labels_v44(ai, labels[:1] + ["Dance"], "KB support: KR track/creator often leans Dance.")

    ai = _apply_consistency_soft_audit_v46(ai, meta)
    try:
        ai["Confidence"] = float(ai.get("Confidence", 0) or 0)
    except Exception:
        ai["Confidence"] = 0.0
    ai["Needs Review"] = bool(ai.get("Needs Review") or ai["Confidence"] < 0.70 or _labels_from_ai_v44(ai)[0] == "Others")
    if ai["Needs Review"] and not safe_str(ai.get("Review Note")):
        ai["Review Note"] = "Low confidence or unclear label."
    return ai


def _download_video_v44(video_url: str, apify_token: str, out_path: str) -> bool:
    if not video_url:
        return False
    headers = {"Authorization": f"Bearer {apify_token}"} if "api.apify.com" in video_url and apify_token else {}
    try:
        r = requests.get(video_url, headers=headers, timeout=90)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 1000
    except Exception:
        return False


def _extract_frames_v44(video_path: str, out_dir: str, points: List[float] = None) -> List[str]:
    points = points or [0.10, 0.50, 0.90]
    try:
        import cv2
    except Exception:
        return []
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    paths = []
    if total <= 0:
        cap.release()
        return paths
    for p in points:
        pos = max(0, min(total - 1, int(total * p)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, frame = cap.read()
        if ok:
            path = os.path.join(out_dir, f"frame_{int(p*100):02d}.jpg")
            cv2.imwrite(path, frame)
            paths.append(path)
    cap.release()
    return paths


def _call_gemini_frames_v44(prompt: str, frame_paths: List[str], gemini_key: str) -> Dict:
    if not frame_paths:
        return {"parse_error": True, "raw_response": "No frames extracted"}
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return {"parse_error": True, "raw_response": f"Missing google-genai: {e}"}
    try:
        client = genai.Client(api_key=gemini_key)
        contents = [prompt + "\n\nYou are seeing sampled frames from the same TikTok video. Use the sequence to resolve motion/action ambiguity."]
        for fp in frame_paths:
            with open(fp, "rb") as f:
                contents.append(types.Part.from_bytes(data=f.read(), mime_type="image/jpeg"))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = response.text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"```$", "", text).strip()
        return json.loads(text)
    except Exception as e:
        return {"parse_error": True, "raw_response": str(e)}


def _call_gemini_full_video_v46(video_path: str, prompt: str, gemini_key: str) -> Dict:
    """Optional full-video fallback for unresolved motion ambiguity."""
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        return {"parse_error": True, "raw_response": f"Missing google-genai: {e}"}
    uploaded = None
    try:
        client = genai.Client(api_key=gemini_key)
        uploaded = client.files.upload(file=video_path)
        # Some accounts/models need a short processing wait. Best effort only.
        for _ in range(20):
            try:
                f = client.files.get(name=uploaded.name)
                state = safe_str(getattr(getattr(f, "state", ""), "name", getattr(f, "state", ""))).upper()
                if not state or state in {"ACTIVE", "READY", "SUCCEEDED"}:
                    break
                if "FAILED" in state:
                    return {"parse_error": True, "raw_response": "Gemini video upload processing failed"}
            except Exception:
                break
            time.sleep(1.5)
        contents = [prompt + "\n\nFull-video fallback: use temporal motion over the whole video. Choose Dance only when choreography/body movement is clearly visible over time.", uploaded]
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = resp.text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"```$", "", text).strip()
        return json.loads(text)
    except Exception as e:
        return {"parse_error": True, "raw_response": str(e)}
    finally:
        try:
            if uploaded is not None:
                client.files.delete(name=uploaded.name)
        except Exception:
            pass


def _maybe_tier2_frames_v44(ai: Dict, merged: Dict, rec: Dict, gemini_key: str, apify_token: str) -> Dict:
    """Run tier escalation for weak/ambiguous rows.

    v46 supports:
    - Tier 2A: 3 frames
    - Tier 2B: 9-frame motion refinement
    - Tier 2C: optional full-video fallback, disabled by default in UI because it is slow/quota-heavy
    """
    if not rec or not gemini_key:
        return ai
    labels = _labels_from_ai_v44(ai)
    conf = float(ai.get("Confidence", 0) or 0)
    blob = _row_text_blob_v44(ai, merged)
    motion_or_weak = conf < 0.72 or labels[0] in {"Dance", "Lip Sync", "Fitness", "Cover", "Others"} or "dance" in blob or "lip sync" in blob or "choreo" in blob
    if not motion_or_weak:
        return ai
    media = rec.get("mediaUrls") if isinstance(rec.get("mediaUrls"), list) else []
    video_url = media[0] if media else _nested_get(rec, "videoMeta.downloadAddr", "")
    if not video_url:
        return ai
    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "video.mp4")
        if not _download_video_v44(video_url, apify_token, video_path):
            return ai
        prompt = _build_prompt_v43(merged)

        best_ai = ai
        best_conf = conf

        # Tier 2A: fast 3-frame check.
        frame_paths = _extract_frames_v44(video_path, os.path.join(tmp, "frames_3"), [0.10, 0.50, 0.90])
        if frame_paths:
            result2 = _call_gemini_frames_v44(prompt, frame_paths, gemini_key)
            ai2 = _normalize_ai_result_v43(result2)
            ai2 = _apply_guardrails_and_kb_v44(ai2, merged)
            conf2 = float(ai2.get("Confidence", 0) or 0)
            if conf2 >= max(best_conf + 0.05, 0.72) or (labels[0] == "Others" and _labels_from_ai_v44(ai2)[0] != "Others"):
                ai2["Reasoning"] = (safe_str(ai2.get("Reasoning")) + " | Tier 2A 3-frame result selected over Tier 1.").strip(" |")
                best_ai, best_conf = ai2, conf2

        # Tier 2B: only for motion-heavy / still weak rows.
        best_labels = _labels_from_ai_v44(best_ai)
        best_blob = _row_text_blob_v44(best_ai, merged)
        should_9 = best_conf < 0.78 or best_labels[0] in {"Dance", "Lip Sync", "Fitness", "Cover", "Others"} or _has_any_v44(best_blob, ["dance", "choreo", "movement", "mouth", "mouthing", "lip sync"])
        if should_9:
            frame_paths9 = _extract_frames_v44(video_path, os.path.join(tmp, "frames_9"), [0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90])
            if frame_paths9:
                motion_prompt = prompt + "\n\nMotion refinement: compare all frames as a sequence. Use Dance only if choreography/body movement is clearly visible across frames; use Lip Sync if mouth/face performance is the main action."
                result9 = _call_gemini_frames_v44(motion_prompt, frame_paths9, gemini_key)
                ai9 = _normalize_ai_result_v43(result9)
                ai9 = _apply_guardrails_and_kb_v44(ai9, merged)
                conf9 = float(ai9.get("Confidence", 0) or 0)
                if conf9 >= max(best_conf + 0.05, 0.74) or (best_labels[0] == "Others" and _labels_from_ai_v44(ai9)[0] != "Others"):
                    ai9["Reasoning"] = (safe_str(ai9.get("Reasoning")) + " | Tier 2B 9-frame motion result selected.").strip(" |")
                    best_ai, best_conf = ai9, conf9

        # Tier 2C: full video fallback only if enabled.
        if st.session_state.get("enable_full_video_fallback_v46", False):
            best_labels = _labels_from_ai_v44(best_ai)
            if best_conf < 0.76 or best_labels[0] in {"Dance", "Lip Sync", "Others"}:
                resultv = _call_gemini_full_video_v46(video_path, prompt, gemini_key)
                aiv = _normalize_ai_result_v43(resultv)
                aiv = _apply_guardrails_and_kb_v44(aiv, merged)
                confv = float(aiv.get("Confidence", 0) or 0)
                if confv >= max(best_conf + 0.04, 0.75) or (best_labels[0] == "Others" and _labels_from_ai_v44(aiv)[0] != "Others"):
                    aiv["Reasoning"] = (safe_str(aiv.get("Reasoning")) + " | Tier 2C full-video result selected.").strip(" |")
                    best_ai = aiv
        return best_ai


def _review_ai_suggest_v53(row, gemini_key: str, apify_token: str) -> Dict:
    """Run the real tagging backend again for one row during human review.

    The review suggestion uses the same backend path as the initial run:
    Gemini cover analysis -> global/KB/market guardrails -> Tier 2A/2B frames
    when needed. It never returns mock data.
    """
    gemini_key = clean_api_secret(gemini_key)
    apify_token = clean_api_secret(apify_token)
    if not gemini_key:
        return {"parse_error": True, "raw_response": "Missing Gemini API key."}

    row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    link = safe_str(row_dict.get("Link"))
    rid = _extract_tiktok_id_from_url(link)
    cache = st.session_state.get("apify_records_by_key", {}) or {}
    rec = cache.get(f"id:{rid}") if rid else None
    if not rec and link:
        rec = cache.get(f"url:{_normalize_tiktok_url(link)}")

    # If the original record is unavailable after a rerun, build a compatible
    # record from the tagged row so cover/video frame analysis still works.
    if not isinstance(rec, dict):
        video_url = safe_str(row_dict.get("Video URL"))
        cover_url = safe_str(row_dict.get("Cover URL"))
        rec = {
            "id": rid,
            "webVideoUrl": link,
            "submittedVideoUrl": link,
            "text": safe_str(row_dict.get("Caption")),
            "locationCreated": safe_str(row_dict.get("Market")),
            "isSlideshow": bool(row_dict.get("Is Slideshow", False)),
            "authorMeta": {
                "name": safe_str(row_dict.get("Creator")),
                "nickName": safe_str(row_dict.get("Creator")),
                "fans": clean_num(row_dict.get("Followers")),
            },
            "musicMeta": {
                "musicName": safe_str(row_dict.get("Track From TikTok") or row_dict.get("Track")),
                "musicAuthor": safe_str(row_dict.get("Artist From TikTok")),
            },
            "videoMeta": {
                "originalCoverUrl": cover_url,
                "coverUrl": cover_url,
                "downloadAddr": video_url,
            },
            "mediaUrls": [video_url] if video_url else [],
            "playCount": clean_num(row_dict.get("Views")),
            "diggCount": clean_num(row_dict.get("Likes")),
            "commentCount": clean_num(row_dict.get("Comments")),
            "shareCount": clean_num(row_dict.get("Shares")),
            "collectCount": clean_num(row_dict.get("Saves")),
        }

    meta = dict(row_dict)
    # Fill any missing review metadata from the original Apify record.
    scraped = _record_to_metrics(rec)
    for key, value in scraped.items():
        if key not in meta or safe_str(meta.get(key)) == "" or meta.get(key) in [None, 0]:
            meta[key] = value
    meta["Link"] = link or safe_str(scraped.get("Link"))
    meta["Market"] = safe_str(row_dict.get("Market")) or safe_str(scraped.get("Market"))
    meta["Track"] = safe_str(row_dict.get("Track")) or safe_str(scraped.get("Track From TikTok"))

    prompt = _build_prompt_v43(meta) + """

REVIEW RE-ANALYSIS:
This row was sent to human review. Re-analyse it carefully using the supplied
cover image and, when needed, sampled video frames. Return the same JSON schema.
Do not guess: use Others with low confidence only when the content truly cannot
be classified from the available evidence.
"""

    result = _call_gemini_v43(
        prompt,
        safe_str(meta.get("Cover URL")) or _record_cover_url(rec),
        gemini_key,
        apify_token,
    )
    ai = _normalize_ai_result_v43(result)
    ai = _apply_guardrails_and_kb_v44(ai, meta)
    ai = _maybe_tier2_frames_v44(ai, meta, rec, gemini_key, apify_token)
    ai = _apply_consistency_soft_audit_v46(ai, meta)
    return ai

def _mock_results_v43(df: pd.DataFrame) -> pd.DataFrame:
    labels = ["Dance", "Lip Sync", "Relationship", "Quotes", "Beauty", "Comedy", "Celebrity Edits", "Media/Infotainment"]
    rows = []
    for i, r in df.iterrows():
        label = labels[i % len(labels)]
        needs_review = (i % 6 == 0)
        rows.append({
            **r.to_dict(),
            "Narrative": f"{label} post",
            "Creative Type": label,
            "Content Details": "Preview only. Add API keys to run Apify + Gemini.",
            "Confidence": 0.0,
            "Reasoning": "Mock result because API keys were not provided.",
            "Needs Review": needs_review,
            "Review Note": "Preview row. Run with API keys for real tagging." if needs_review else "",
            "Total Engagement": clean_num(r.get("Total Engagement")),
        })
    out_df = add_performance_fields(pd.DataFrame(rows))
    if "QA Priority" not in out_df.columns:
        out_df["QA Priority"] = out_df.get("Needs Review", False).map(lambda x: "High" if bool(x) else "Low") if "Needs Review" in out_df.columns else "Low"
    if "QA Reason" not in out_df.columns:
        out_df["QA Reason"] = ""
    return out_df


def _run_v55_backend_reference(df: pd.DataFrame) -> pd.DataFrame:
    """Run the real backend tagging process.

    Despite the historical function name, this no longer returns mock rows during
    normal use. It requires Gemini + Apify keys, runs Apify, calls Gemini, applies
    KB/guardrails/tier fallbacks, then returns tagged rows. If keys/API calls are
    missing, it returns an empty dataframe and shows an error instead of creating
    fake tagged output.
    """
    if df.empty:
        return pd.DataFrame()
    gemini_key = clean_api_secret(st.session_state.get("gemini_key", "") or st.session_state.get("gemini_key_input_v52", "") or st.session_state.get("gemini_key_input", ""))
    apify_token = clean_api_secret(st.session_state.get("apify_token", "") or st.session_state.get("apify_token_input_v52", "") or st.session_state.get("apify_token_input", ""))
    st.session_state.gemini_key = gemini_key
    st.session_state.apify_token = apify_token
    if not gemini_key or not apify_token:
        st.error("Please enter both Gemini API key and Apify token before running real tagging.")
        return pd.DataFrame()

    links = [safe_str(x) for x in df.get("Link", pd.Series(dtype=str)).tolist() if is_tiktok_link(x)]
    if not links:
        st.error("No valid TikTok links were selected for tagging.")
        return pd.DataFrame()

    status = st.empty()
    prog = st.progress(0)
    log = st.empty()
    logs = []
    try:
        status.markdown("<div class='good-note'>Running Apify scrape for selected posts...</div>", unsafe_allow_html=True)
        records = _apify_scrape_links_v43(links, apify_token)
    except Exception as e:
        st.error(f"Apify failed: {e}")
        return pd.DataFrame()

    by_id, by_url = {}, {}
    review_record_cache = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        url = _record_public_url(rec)
        rid = safe_str(rec.get("id")) or _extract_tiktok_id_from_url(url)
        if rid:
            by_id[rid] = rec
            review_record_cache[f"id:{rid}"] = rec
        if url:
            norm_url = _normalize_tiktok_url(url)
            by_url[norm_url] = rec
            review_record_cache[f"url:{norm_url}"] = rec
    # Keep the original Apify record available to the Review page. This lets
    # AI Suggest reuse hashtags, mediaUrls, videoMeta, musicMeta and creator data.
    st.session_state.apify_records_by_key = review_record_cache

    rows = []
    total = len(df)
    for pos, (_, r) in enumerate(df.iterrows(), start=1):
        link = safe_str(r.get("Link"))
        rid = _extract_tiktok_id_from_url(link)
        rec = by_id.get(rid) or by_url.get(_normalize_tiktok_url(link)) or {}
        scraped = _record_to_metrics(rec) if rec else {}
        merged = {**r.to_dict(), **{k: v for k, v in scraped.items() if v not in ["", 0, None]}}
        # Preserve user-provided market/track when present.
        if safe_str(r.get("Market")):
            merged["Market"] = r.get("Market")
        if safe_str(r.get("Track")):
            merged["Track"] = r.get("Track")
        if not rec:
            ai = {
                "Narrative": "Unavailable post",
                "Creative Type": "Others",
                "Content Details": "",
                "Confidence": 0.0,
                "Reasoning": "No Apify record matched this selected link.",
                "Needs Review": False,
                "Review Note": "Auto-removed unavailable post.",
                "Review Action": "REMOVE",
            }
        else:
            prompt = _build_prompt_v43(merged)
            result = _call_gemini_v43(prompt, merged.get("Cover URL", ""), gemini_key, apify_token)
            ai = _normalize_ai_result_v43(result)
            ai = _apply_guardrails_and_kb_v44(ai, merged)
            ai = _maybe_tier2_frames_v44(ai, merged, rec, gemini_key, apify_token)
        rows.append({**merged, **ai})
        prog.progress(min(pos / max(total, 1), 1.0))
        logs.append(f"{pos}/{total}: {safe_str(merged.get('Creator')) or extract_creator(link)} → {ai.get('Creative Type')}")
        _render_run_log_v45(log, logs)
    status.empty()
    out_df = add_performance_fields(pd.DataFrame(rows))
    if "QA Priority" not in out_df.columns:
        out_df["QA Priority"] = out_df.get("Needs Review", False).map(lambda x: "High" if bool(x) else "Low") if "Needs Review" in out_df.columns else "Low"
    if "QA Reason" not in out_df.columns:
        out_df["QA Reason"] = ""
    return out_df


# v56 backend override -------------------------------------------------------
# The active function below delegates classification to the preserved
# final_update_2 pipeline and adapts its columns to the current UI/QA schema.

def _selection_group_key_v56(row) -> Tuple[str, ...]:
    group_by = st.session_state.get("group_by", "No grouping")
    if group_by == "Market":
        return (display_market(row.get("Market")),)
    if group_by == "Track":
        return (display_empty(row.get("Track"), "Not specified"),)
    if group_by == "Source":
        return (display_empty(row.get("Source"), "Unknown source"),)
    if group_by == "Market + Track":
        return (display_market(row.get("Market")), display_empty(row.get("Track"), "Not specified"))
    return ("All selected posts",)


def _all_ranked_candidates_v56(batch: pd.DataFrame) -> pd.DataFrame:
    """Return the complete filtered/ranked pool behind the Top N preview."""
    if batch.empty:
        return batch.copy()
    if st.session_state.get("selection_mode", "Top posts") == "Tag every link":
        return selected_posts_preview(batch)
    old_top_n = st.session_state.get("top_n", 20)
    try:
        st.session_state.top_n = max(len(batch), int(old_top_n))
        return selected_posts_preview(batch)
    finally:
        st.session_state.top_n = old_top_n


def _removed_mask_v56(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    action = df.get("Review Action", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str).str.upper()
    status = df.get("Validation Status", pd.Series([""] * len(df), index=df.index)).fillna("").astype(str).str.lower()
    return (action == "REMOVE") | (status == "removed")


def _route_sensitive_for_selection_v56(tagged: pd.DataFrame, selection_mode: str) -> Tuple[pd.DataFrame, int]:
    """Skip sensitive rows in every mode; Top posts can backfill them later."""
    if tagged.empty:
        return tagged, 0
    out = tagged.copy()
    tier = out.get("Tier Used", pd.Series([""] * len(out), index=out.index)).fillna("").astype(str).str.strip().str.lower()
    raw_status = out.get("Raw Apify Status", pd.Series([""] * len(out), index=out.index)).fillna("").astype(str)
    sensitive_mask = tier.eq("sensitive_human_review") | raw_status.str.contains("SENSITIVE", case=False, na=False)
    count = int(sensitive_mask.sum())
    if count:
        out.loc[sensitive_mask, "Review Action"] = "REMOVE"
        out.loc[sensitive_mask, "Needs Review"] = False
        out.loc[sensitive_mask, "Validation Status"] = "removed"
        out.loc[sensitive_mask, "QA Priority"] = "Removed"
        if selection_mode == "Top posts":
            out.loc[sensitive_mask, "Review Note"] = "Sensitive post skipped in Top posts mode; use the next-ranked candidate."
            out.loc[sensitive_mask, "QA Reason"] = "Sensitive post skipped and replaced to preserve the requested Top N."
        else:
            out.loc[sensitive_mask, "Review Note"] = "Sensitive post skipped in Tag every link mode; no replacement was added."
            out.loc[sensitive_mask, "QA Reason"] = "Sensitive post skipped automatically and excluded from Review and final exports."
    return out, count


def run_real_tagging_backend(df: pd.DataFrame) -> pd.DataFrame:
    """Run final_update_2 while preserving the accepted UI and audit contract."""
    if df.empty:
        return pd.DataFrame()

    gemini_key = clean_api_secret(
        st.session_state.get("gemini_key", "")
        or st.session_state.get("gemini_key_input_v52", "")
        or st.session_state.get("gemini_key_input", "")
    )
    apify_token = clean_api_secret(
        st.session_state.get("apify_token", "")
        or st.session_state.get("apify_token_input_v52", "")
        or st.session_state.get("apify_token_input", "")
    )
    st.session_state.gemini_key = gemini_key
    st.session_state.apify_token = apify_token
    if not gemini_key or not apify_token:
        st.error("Please enter both Gemini API key and Apify token before running tagging.")
        return pd.DataFrame()

    selected = df.copy().reset_index(drop=True)
    selected = selected[selected.get("Link", pd.Series(dtype=str)).map(is_tiktok_link)].reset_index(drop=True)
    if selected.empty:
        st.error("No valid TikTok links were selected for tagging.")
        return pd.DataFrame()

    replace_unavailable = bool(st.session_state.get("replace_unavailable_posts", True))
    replace_unavailable = replace_unavailable and st.session_state.get("selection_mode", "Top posts") == "Top posts"
    candidate_pool = _all_ranked_candidates_v56(st.session_state.get("batch_df", pd.DataFrame()))
    if candidate_pool.empty:
        candidate_pool = selected.copy()

    target_counts: Dict[Tuple[str, ...], int] = {}
    for _, row in selected.iterrows():
        key = _selection_group_key_v56(row)
        target_counts[key] = target_counts.get(key, 0) + 1

    attempted = {final_update2_normalize_url(link) for link in selected["Link"].tolist()}
    pending = selected.copy()
    result_batches: List[pd.DataFrame] = []
    cached_records: Dict[str, Dict] = {}
    logs: List[str] = []
    status = st.empty()
    progress = st.progress(0)
    log_box = st.empty()
    replacement_count = 0

    while not pending.empty:
        links = [safe_str(link) for link in pending["Link"].tolist() if is_tiktok_link(link)]
        status.markdown(
            f"<div class='good-note'>Scraping and tagging {len(links)} post(s) with the final_update_2 pipeline...</div>",
            unsafe_allow_html=True,
        )
        try:
            records = final_update2_scrape_links(links, apify_token)
            cached_records.update(final_update2_review_cache(records))

            def on_progress(done: int, total: int, tier: str):
                progress.progress(min(done / max(total, 1), 1.0))
                _render_run_log_v45(log_box, logs)

            tagged_batch = final_update2_tag_candidates(
                pending,
                records,
                gemini_key,
                apify_token,
                logs=logs,
                on_progress=on_progress,
            )

            # Sensitive posts are never sent to Review or final exports. Top posts
            # mode backfills from the ranked candidate pool; Tag every link records
            # the skipped row in QA without adding an unrelated replacement.
            selection_mode = st.session_state.get("selection_mode", "Top posts")
            tagged_batch, skipped_sensitive = _route_sensitive_for_selection_v56(
                tagged_batch,
                selection_mode,
            )
            if skipped_sensitive:
                if selection_mode == "Top posts":
                    logs.append(f"Skipped {skipped_sensitive} sensitive post(s); selecting the next-ranked candidate(s).")
                else:
                    logs.append(f"Skipped {skipped_sensitive} sensitive post(s); Tag every link does not add replacements.")
                _render_run_log_v45(log_box, logs)
        except Exception as exc:
            st.error(f"final_update_2 backend failed: {exc}")
            return pd.DataFrame()

        result_batches.append(tagged_batch)
        combined = pd.concat(result_batches, ignore_index=True) if result_batches else pd.DataFrame()
        if not replace_unavailable:
            break

        available = combined[~_removed_mask_v56(combined)].copy()
        available_counts: Dict[Tuple[str, ...], int] = {}
        for _, row in available.iterrows():
            key = _selection_group_key_v56(row)
            available_counts[key] = available_counts.get(key, 0) + 1
        deficits = {key: max(0, target - available_counts.get(key, 0)) for key, target in target_counts.items()}
        if not any(deficits.values()):
            break

        replacements = []
        for _, candidate in candidate_pool.iterrows():
            normalized = final_update2_normalize_url(candidate.get("Link"))
            key = _selection_group_key_v56(candidate)
            if normalized in attempted or deficits.get(key, 0) <= 0:
                continue
            attempted.add(normalized)
            deficits[key] -= 1
            replacements.append(candidate.to_dict())
        if not replacements:
            logs.append("No more ranked candidates are available to replace unavailable posts.")
            _render_run_log_v45(log_box, logs)
            break
        pending = pd.DataFrame(replacements)
        replacement_count += len(pending)
        logs.append(f"Trying {len(pending)} next-ranked replacement post(s).")
        _render_run_log_v45(log_box, logs)

    st.session_state.apify_records_by_key = cached_records
    status.empty()
    progress.progress(1.0)
    output = pd.concat(result_batches, ignore_index=True) if result_batches else pd.DataFrame()
    output = add_performance_fields(output)
    if replacement_count:
        st.success(f"Used {replacement_count} next-ranked candidate(s) to replace unavailable or sensitive posts where possible.")
    return output


def _review_ai_suggest_final_update2(row, gemini_key: str, apify_token: str) -> Dict:
    """Re-run one review row through the same final_update_2 pipeline."""
    row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    link = safe_str(row_dict.get("Link"))
    post_id = _extract_tiktok_id_from_url(link)
    cache = st.session_state.get("apify_records_by_key", {}) or {}
    record = cache.get(f"id:{post_id}") if post_id else None
    if not isinstance(record, dict) and link:
        record = cache.get(f"url:{final_update2_normalize_url(link)}")
    records = [record] if isinstance(record, dict) else []
    if not records and link and apify_token:
        try:
            records = final_update2_scrape_links([link], apify_token)
            cache.update(final_update2_review_cache(records))
            st.session_state.apify_records_by_key = cache
        except Exception as exc:
            return {"parse_error": True, "raw_response": f"Apify failed during AI Suggest: {exc}"}
    try:
        suggested = final_update2_tag_candidates(
            pd.DataFrame([row_dict]),
            records,
            gemini_key,
            apify_token,
            logs=[],
        )
    except Exception as exc:
        return {"parse_error": True, "raw_response": str(exc)}
    if suggested.empty:
        return {"parse_error": True, "raw_response": "The backend returned no suggestion."}
    result = suggested.iloc[0].to_dict()
    if safe_str(result.get("Review Action")).upper() == "REMOVE":
        return {"parse_error": True, "raw_response": "This post is unavailable and cannot be analysed."}
    return result


def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return buf.getvalue()


def safe_sheet_name(name: str) -> str:
    name = safe_str(name) or "Not specified"
    name = re.sub(r"[\\/*?:\[\]]+", " ", name).strip()
    return (name or "Not specified")[:31]


def grouped_excel_bytes(final_df: pd.DataFrame) -> bytes:
    """Create the final Excel workbook with all rows, market tabs, and links-only."""
    if final_df is None or final_df.empty:
        return to_excel_bytes({"Final Output": pd.DataFrame()})

    df = final_df.copy()
    for col in ["Market", "Track", "Source"]:
        if col not in df.columns:
            df[col] = ""
    df["Market"] = df["Market"].map(display_market)
    df["Track"] = df["Track"].map(lambda x: display_empty(x, "Not specified"))
    df["Source"] = df["Source"].map(lambda x: display_empty(x, "Pasted links"))

    sort_cols = [c for c in ["Market", "Track", "Views", "Total Engagement"] if c in df.columns]
    ascending = [True, True] + [False] * max(0, len(sort_cols) - 2)
    try:
        df = df.sort_values(sort_cols, ascending=ascending) if sort_cols else df
    except Exception:
        pass

    sheets: Dict[str, pd.DataFrame] = {}
    used_names = set()

    def add_sheet(preferred_name: str, sheet_df: pd.DataFrame) -> None:
        base = safe_sheet_name(preferred_name)
        name = base
        counter = 2
        while name.lower() in used_names:
            suffix = f" {counter}"
            name = safe_sheet_name(base[: max(1, 31 - len(suffix))] + suffix)
            counter += 1
        used_names.add(name.lower())
        sheets[name] = sheet_df

    add_sheet("All Posts", df)

    # Market tabs are convenient for marketing teams reviewing one country at a time.
    if "Market" in df.columns:
        for market, sub in df.groupby("Market", dropna=False, sort=True):
            add_sheet(f"Market {display_market(market)}", sub.copy())

    link_cols = [c for c in ["Source", "Market", "Track", "Creator", "Creative Type", "Link"] if c in df.columns]
    links_df = df[link_cols].copy() if link_cols else (df[["Link"]].copy() if "Link" in df.columns else df.copy())
    add_sheet("Links Only", links_df)
    return to_excel_bytes(sheets)



def chart_bar(df: pd.DataFrame, x: str, y: str, title: str = "", orientation: str = "v", value_format: str = ""):
    """Plotly fallback, with readable labels and hidden toolbar.

    The marketing dashboard mainly uses HTML bar lists, but this helper is kept
    for future interactive charts. It forces dark text so labels remain visible
    on the light UI.
    """
    if df.empty or x not in df.columns or y not in df.columns:
        st.caption("No data yet.")
        return
    if px is not None:
        palette = ["#6254e8", "#0ea5e9", "#10b981", "#f97316", "#ec4899", "#8b5cf6", "#14b8a6", "#f59e0b", "#ef4444", "#64748b"]
        if orientation == "h":
            fig = px.bar(df, x=y, y=x, color=x, text=y, orientation="h", title=title, color_discrete_sequence=palette)
            fig.update_layout(
                template="plotly_white", showlegend=False,
                title=dict(font=dict(color="#111827", size=16), x=0.01, xanchor="left"),
                font=dict(color="#111827", size=13),
                height=max(340, len(df) * 46), margin=dict(l=20, r=42, t=58, b=46),
                plot_bgcolor="rgba(255,255,255,0.70)", paper_bgcolor="rgba(255,255,255,0)",
                xaxis=dict(
                    gridcolor="#cbd5e1", zerolinecolor="#94a3b8", automargin=True,
                    tickfont=dict(color="#111827", size=12),
                    title=dict(font=dict(color="#334155", size=12)),
                ),
                yaxis=dict(
                    title="", automargin=True,
                    tickfont=dict(color="#111827", size=12),
                ),
            )
            if value_format == "percent":
                fig.update_traces(texttemplate="%{x:.2f}%", hovertemplate="%{y}: %{x:.2f}%<extra></extra>")
            elif value_format == "integer":
                fig.update_traces(texttemplate="%{x:,.0f}", hovertemplate="%{y}: %{x:,.0f}<extra></extra>")
            fig.update_traces(textposition="outside", cliponaxis=False, textfont=dict(color="#111827", size=12))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            fig = px.bar(df, x=x, y=y, color=x, text=y, title=title, color_discrete_sequence=palette)
            fig.update_layout(
                template="plotly_white", showlegend=False,
                title=dict(font=dict(color="#111827", size=16), x=0.01, xanchor="left"),
                font=dict(color="#111827", size=13),
                height=360, margin=dict(l=48, r=32, t=58, b=58),
                plot_bgcolor="rgba(255,255,255,0.70)", paper_bgcolor="rgba(255,255,255,0)",
                xaxis=dict(
                    gridcolor="#cbd5e1", automargin=True,
                    tickfont=dict(color="#111827", size=12),
                    title=dict(font=dict(color="#334155", size=12)),
                ),
                yaxis=dict(
                    gridcolor="#cbd5e1", automargin=True,
                    tickfont=dict(color="#111827", size=12),
                    title=dict(font=dict(color="#334155", size=12)),
                ),
            )
            if value_format == "percent":
                fig.update_traces(texttemplate="%{y:.2f}%", hovertemplate="%{x}: %{y:.2f}%<extra></extra>")
            elif value_format == "integer":
                fig.update_traces(texttemplate="%{y:,.0f}", hovertemplate="%{x}: %{y:,.0f}<extra></extra>")
            fig.update_traces(textposition="outside", cliponaxis=False, textfont=dict(color="#111827", size=12))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        st.bar_chart(df.set_index(x)[y])


def summary_kpi_row(items: List[Tuple[str, str, str, str]]) -> str:
    """Colored KPI cards for marketing Summary page."""
    cards = []
    for label, value, hint, cls in items:
        hint_html = f"<div class='hint'>{esc(hint)}</div>" if safe_str(hint) else ""
        cards.append(
            f"<div class='summary-kpi {esc(cls)}'><div class='value'>{esc(value)}</div>"
            f"<div class='label'>{esc(label)}</div>{hint_html}</div>"
        )
    return "<div class='summary-kpi-grid'>" + "".join(cards) + "</div>"


def focus_cards(items: List[Tuple[str, str, str, str]]) -> str:
    cards = []
    for eyebrow, main, sub, cls in items:
        sub_html = f"<div class='sub'>{esc(sub)}</div>" if safe_str(sub) else ""
        cards.append(
            f"<div class='focus-card {esc(cls)}'><div class='eyebrow'>{esc(eyebrow)}</div>"
            f"<div class='main'>{esc(main)}</div>{sub_html}</div>"
        )
    return "<div class='focus-grid'>" + "".join(cards) + "</div>"


def section_title(title: str, accent: str = "#6254e8") -> str:
    icon_map = {
        "Creative Type Mix": "CT",
        "Views by Creative Type": "V",
        "Source Summary": "S",
        "Market Summary": "M",
        "KOL Size Performance": "K",
        "Track Summary": "T",
        "Top Posts": "",
        "Post Summary": "P",
        "Downloads": "↓",
    }
    icon = icon_map.get(title, "•")
    return (
        f"<div class='summary-section-title' style='--accent:{accent}'>"
        f"<div class='section-icon'>{esc(icon)}</div><div><h3>{esc(title)}</h3></div></div>"
    )


def bar_list(df: pd.DataFrame, label_col: str, value_col: str, max_rows: int = 10, value_suffix: str = "", show_share: bool = False) -> str:
    if df is None or df.empty or label_col not in df.columns or value_col not in df.columns:
        return "<div class='empty-panel'>No data available yet.</div>"
    show = df[[label_col, value_col]].copy().head(max_rows)
    show[value_col] = show[value_col].map(clean_num)
    max_val = int(show[value_col].max()) if not show.empty else 0
    total = int(show[value_col].sum()) if not show.empty else 0
    palette = ["#6254e8", "#0ea5e9", "#10b981", "#f97316", "#ec4899", "#8b5cf6", "#14b8a6", "#f59e0b", "#ef4444", "#64748b"]
    rows = []
    for i, r in show.iterrows():
        label = display_empty(r.get(label_col), "Not specified")
        val = clean_num(r.get(value_col))
        width = 0 if max_val <= 0 else max(4, min(100, val / max_val * 100))
        color = palette[len(rows) % len(palette)]
        if show_share and total:
            value_text = f"{val:,} ({val/total*100:.0f}%)"
        elif value_suffix:
            value_text = f"{val:,} {value_suffix}"
        else:
            value_text = f"{val:,}"
        rows.append(
            f"<div class='bar-row'><div class='bar-label' title='{esc(label)}'>{esc(label)}</div>"
            f"<div class='bar-track'><div class='bar-fill' style='width:{width:.1f}%;background:{color}'></div></div>"
            f"<div class='bar-value'>{esc(value_text)}</div></div>"
        )
    return "<div class='bar-list'>" + "".join(rows) + "</div>"


def display_filter_options(series: pd.Series, empty_label: str = "Not specified") -> List[str]:
    values = []
    for v in series.fillna("").tolist():
        label = display_empty(v, empty_label)
        if label not in values:
            values.append(label)
    return sorted(values)


def apply_filter_value(df: pd.DataFrame, col: str, value: str, empty_label: str = "Not specified") -> pd.DataFrame:
    if value == "All":
        return df
    if value == empty_label:
        return df[df[col].fillna("").astype(str).str.strip().eq("")]
    return df[df[col].fillna("").astype(str).str.strip().eq(value)]

# -----------------------------
# Header
# -----------------------------
st.markdown(
    """
<div class='app-title hero-v37 hero-title-only'>
  <div class='hero-copy'>
    <h1>TikTok Post Tagging Tool</h1>
  </div>
</div>
""",
    unsafe_allow_html=True,
)
step_strip(st.session_state.step)

# -----------------------------
# STEP 1
# -----------------------------
if st.session_state.step == 1:
    st.markdown("<div class='card'><h2>API Keys</h2></div>", unsafe_allow_html=True)

    # Keep the visible input fields separate from the saved runtime keys.
    # This prevents Streamlit reruns/navigation from accidentally using stale or blank values.
    if "gemini_key_input_v52" not in st.session_state:
        st.session_state.gemini_key_input_v52 = st.session_state.get("gemini_key", "")
    if "apify_token_input_v52" not in st.session_state:
        st.session_state.apify_token_input_v52 = st.session_state.get("apify_token", "")

    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Gemini API key", type="password", key="gemini_key_input_v52")
    with c2:
        st.text_input("Apify token", type="password", key="apify_token_input_v52")

    if st.button("Save keys and continue", type="primary", width="stretch"):
        st.session_state.gemini_key = clean_api_secret(st.session_state.get("gemini_key_input_v52", ""))
        st.session_state.apify_token = clean_api_secret(st.session_state.get("apify_token_input_v52", ""))
        if not st.session_state.gemini_key or not st.session_state.apify_token:
            st.error("Please paste both Gemini API key and Apify token.")
        else:
            st.success("API keys saved for this session.")
            go(2)

# -----------------------------
# STEP 2
# -----------------------------
elif st.session_state.step == 2:
    st.markdown("<div class='card'><h2>Add posts</h2><p class='sub'>Upload post files and add pasted TikTok links into one combined batch.</p></div>", unsafe_allow_html=True)

    # Current prototype runs General UGC creative type tagging by default.
    # General-only prototype. Drama / Creator Core mode can be added later as a separate backend route.
    st.session_state.mode = "General UGC creative types"

    add_tab, paste_tab = st.tabs(["Upload post files", "Paste extra TikTok links"])

    with add_tab:
        st.markdown("<div class='card'><h3>Upload post files</h3><p class='sub'>CSV or Excel files with TikTok links. You can select multiple files.</p>", unsafe_allow_html=True)
        files = st.file_uploader(
            "Post data files",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="files_upload_v24",
        )
        parsed_frames = []
        summary_rows = []
        errors = []
        if files:
            for f in files:
                try:
                    df = read_any_table(f)
                    std, cols = standardize_file_rows(df, f.name)
                    parsed_frames.append(std)
                    markets = sorted([m for m in std.get("Market", pd.Series(dtype=str)).fillna("").unique().tolist() if safe_str(m)])
                    tracks = sorted([t for t in std.get("Track", pd.Series(dtype=str)).fillna("").unique().tolist() if safe_str(t)])
                    summary_rows.append({
                        "File": f.name,
                        "TikTok links": len(std),
                        "Markets": ", ".join(markets[:3]) + ("..." if len(markets) > 3 else "") if markets else "Not specified",
                        "Tracks": ", ".join(tracks[:2]) + ("..." if len(tracks) > 2 else "") if tracks else "Not specified",
                    })
                except Exception as e:
                    errors.append(f"{f.name}: {e}")
            if summary_rows:
                st.markdown(render_table(pd.DataFrame(summary_rows), max_rows=10), unsafe_allow_html=True)
            if errors:
                st.markdown("<div class='warn-note'>" + "<br>".join(map(esc, errors)) + "</div>", unsafe_allow_html=True)
            combined_upload = pd.concat(parsed_frames, ignore_index=True) if parsed_frames else pd.DataFrame()
            if not combined_upload.empty:
                if st.button("Add uploaded rows to batch", type="primary", width="stretch"):
                    added, skipped = append_to_batch(combined_upload)
                    st.session_state.last_message = f"Added {added} uploaded rows. Skipped {skipped} duplicate rows."
                    st.rerun()
        else:
            st.markdown("<p class='sub'>No file selected yet.</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with paste_tab:
        st.markdown("<div class='card'><h3>Paste TikTok links</h3><p class='sub'>Use this to add extra links that are not included in your files.</p>", unsafe_allow_html=True)
        link_text = st.text_area("TikTok links", placeholder="Paste one TikTok link per line", height=150)
        c1, c2 = st.columns([1.25, 0.75])
        with c1:
            paste_track = st.text_input("Track / sound name", placeholder="Optional")
        with c2:
            market_choice = st.selectbox("Market", MARKET_OPTIONS, index=0)
            paste_market = "" if market_choice == "Other / no market" else market_choice
        links = parse_links(link_text)
        market_label = paste_market if paste_market else "Other"
        st.markdown(f"<div class='pill-row'><span class='pill green'>Links detected: {len(links)}</span><span class='pill blue'>Market: {esc(market_label)}</span></div>", unsafe_allow_html=True)
        if st.button("Add pasted links to batch", type="primary", width="stretch"):
            if not links:
                st.warning("Paste at least one TikTok link first.")
            else:
                rows = []
                for l in links:
                    rows.append({
                        "Source": "Pasted links",
                        "Input Type": "Pasted",
                        "Link": l,
                        "Market": paste_market,
                        "Track": safe_str(paste_track),
                        "Viral Date": "",
                        "Date": "",
                        "Creator": extract_creator(l),
                        "Views": 0,
                        "Likes": 0,
                        "Comments": 0,
                        "Shares": 0,
                        "Saves": 0,
                        "Total Engagement": 0,
                    })
                added, skipped = append_to_batch(pd.DataFrame(rows))
                st.session_state.last_message = f"Added {added} pasted links. Skipped {skipped} duplicate links."
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.last_message:
        st.markdown(f"<div class='good-note'>{esc(st.session_state.last_message)}</div>", unsafe_allow_html=True)

    batch = st.session_state.batch_df
    st.markdown("<div class='card'><h3>Current batch</h3>", unsafe_allow_html=True)
    if batch.empty:
        st.markdown("<p class='sub'>No posts added yet. Upload files or paste links above, then add them to the batch.</p>", unsafe_allow_html=True)
    else:
        market_count = len([m for m in batch["Market"].fillna("").unique() if safe_str(m)])
        track_count = len([t for t in batch["Track"].fillna("").unique() if safe_str(t)])
        st.markdown(metric_row([
            ("Posts", str(len(batch)), "Ready in batch"),
            ("Markets", str(market_count) if market_count else "—", "Optional"),
            ("Tracks", str(track_count) if track_count else "—", "Optional"),
            ("Sources", str(batch["Source"].nunique()), "Files + pasted"),
        ]), unsafe_allow_html=True)
        st.markdown(render_table(batch, max_rows=10, cols=["Source", "Link", "Market", "Track", "Date", "Creator"]), unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("Clear batch", width="stretch"):
                st.session_state.batch_df = pd.DataFrame()
                st.session_state.selected_df = pd.DataFrame()
                st.session_state.tagged_df = pd.DataFrame()
                st.session_state.last_message = ""
                reset_date_filter_state_v68()
                st.rerun()
        with c2:
            if st.button("Back", width="stretch"):
                go(1)
        with c3:
            if st.button("Continue", type="primary", width="stretch"):
                go(3)
    st.markdown("</div>", unsafe_allow_html=True)

# STEP 3
# -----------------------------
elif st.session_state.step == 3:
    batch = st.session_state.batch_df
    st.markdown("<div class='card'><h2>Select posts</h2><p class='sub'>Choose which rows to include first, then pick top posts or tag every link.</p></div>", unsafe_allow_html=True)
    if batch.empty:
        st.markdown("<div class='warn-note'>No posts in batch yet.</div>", unsafe_allow_html=True)
        if st.button("Go back to Add Posts", type="primary"):
            go(2)
        st.stop()

    # Build friendly filter options. Blank markets are grouped as Other.
    filter_df = batch.copy()
    filter_df["Market Display"] = filter_df["Market"].map(display_market) if "Market" in filter_df.columns else "Other"
    filter_df["Track Display"] = filter_df["Track"].map(lambda x: display_empty(x, "Not specified")) if "Track" in filter_df.columns else "Not specified"
    filter_df["Source Display"] = filter_df["Source"].map(lambda x: display_empty(x, "Unknown source")) if "Source" in filter_df.columns else "Unknown source"

    st.session_state.selection_mode = st.radio(
        "How many posts do you want to tag?",
        ["Top posts", "Tag every link"],
        horizontal=True,
        index=0 if st.session_state.get("selection_mode", "Top posts") == "Top posts" else 1,
    )

    if st.session_state.selection_mode == "Top posts":
        main1, main2 = st.columns([0.7, 1.3])
        with main1:
            number_label = "Posts per group" if st.session_state.get("group_by", "No grouping") != "No grouping" else "Number of posts"
            st.session_state.top_n = st.number_input(
                number_label,
                min_value=1,
                max_value=max(len(batch), 1),
                value=min(int(st.session_state.get("top_n", 20)), max(len(batch), 1)),
                step=1,
            )
        with main2:
            rank_options = ["Total Engagement", "Views", "Likes", "Comments", "Shares", "Saves", "Followers", "Engagement Rate", "Likes Rate", "Comments Rate", "Shares Rate", "Saves Rate"]
            prev_rank = st.session_state.get("rank_metrics", ["Total Engagement"])
            if isinstance(prev_rank, str):
                prev_rank = [prev_rank]
            prev_rank = [x for x in prev_rank if x in rank_options] or ["Total Engagement"]
            st.session_state.rank_metrics = st.multiselect(
                "Rank top posts by",
                rank_options,
                default=prev_rank,
                help="Choose more than one metric if needed. Example: Views + Shares sorts by Views first, then Shares.",
            )
            if not st.session_state.rank_metrics:
                st.session_state.rank_metrics = ["Total Engagement"]
    else:
        st.markdown("<div class='good-note'>Every TikTok link in the filtered view will be tagged in the original combined-batch order.</div>", unsafe_allow_html=True)

    with st.expander("Optional: grouping and filters", expanded=False):
        if st.session_state.selection_mode == "Top posts":
            group_options = ["No grouping", "Market", "Track", "Source", "Market + Track"]
            prev_group = st.session_state.get("group_by", "No grouping")
            if prev_group not in group_options:
                prev_group = "No grouping"
            st.session_state.group_by = st.selectbox(
                "Group top posts by",
                group_options,
                index=group_options.index(prev_group),
            )

            group_explain = {
                "No grouping": "Select the Top N posts from the whole batch.",
                "Market": "Select Top N separately for each market. Blank market will be grouped as Other.",
                "Track": "Select Top N separately for each track. Blank track will be grouped as Not specified.",
                "Source": "Select Top N separately for each uploaded file or pasted-link batch.",
                "Market + Track": "Select Top N separately for every market + track combination.",
            }
            if st.session_state.group_by != "No grouping":
                st.markdown(
                    f"<div class='group-summary-note'>{group_explain.get(st.session_state.group_by, '')}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.session_state.group_by = "No grouping"
            st.markdown(
                "<div class='group-summary-note'>Tag every link keeps the original combined-batch order.</div>",
                unsafe_allow_html=True,
            )

        limit_input = st.checkbox("Limit input to specific market, track, or source", value=st.session_state.get("limit_input", False))
        st.session_state.limit_input = limit_input
        if limit_input:
            f1, f2, f3 = st.columns(3)
            with f1:
                market_options = ["All"] + sorted(filter_df["Market Display"].dropna().unique().tolist())
                prev = st.session_state.get("select_markets", ["All"])
                prev = [x for x in prev if x in market_options] or ["All"]
                st.session_state.select_markets = st.multiselect("Market", market_options, default=prev)
                if not st.session_state.select_markets:
                    st.session_state.select_markets = ["All"]
            with f2:
                track_options = ["All"] + sorted(filter_df["Track Display"].dropna().unique().tolist())
                prev = st.session_state.get("select_tracks", ["All"])
                prev = [x for x in prev if x in track_options] or ["All"]
                st.session_state.select_tracks = st.multiselect("Track", track_options, default=prev)
                if not st.session_state.select_tracks:
                    st.session_state.select_tracks = ["All"]
            with f3:
                source_options = ["All"] + sorted(filter_df["Source Display"].dropna().unique().tolist())
                prev = st.session_state.get("select_sources", ["All"])
                prev = [x for x in prev if x in source_options] or ["All"]
                st.session_state.select_sources = st.multiselect("Source", source_options, default=prev)
                if not st.session_state.select_sources:
                    st.session_state.select_sources = ["All"]
        else:
            st.session_state.select_markets = ["All"]
            st.session_state.select_tracks = ["All"]
            st.session_state.select_sources = ["All"]

        if st.session_state.selection_mode == "Top posts" and st.session_state.group_by != "No grouping":
            st.markdown(
                f"<div class='good-note'>Selection preview: top <b>{int(st.session_state.top_n)}</b> posts per <b>{st.session_state.group_by}</b>, ranked by <b>{', '.join(st.session_state.rank_metrics)}</b>.</div>",
                unsafe_allow_html=True,
            )

        st.session_state.use_date_filter = st.checkbox("Limit posts to a date window", value=st.session_state.get("use_date_filter", False))
        if st.session_state.use_date_filter:
            # Only show tracks still eligible after the optional Market/Track/Source
            # filters. This keeps the per-track date form short and relevant.
            date_scope_df = filter_df.copy()
            selected_markets = st.session_state.get("select_markets", ["All"])
            if selected_markets and "All" not in selected_markets:
                date_scope_df = date_scope_df[date_scope_df["Market Display"].isin(selected_markets)]
            selected_tracks = st.session_state.get("select_tracks", ["All"])
            if selected_tracks and "All" not in selected_tracks:
                date_scope_df = date_scope_df[date_scope_df["Track Display"].isin(selected_tracks)]
            selected_sources = st.session_state.get("select_sources", ["All"])
            if selected_sources and "All" not in selected_sources:
                date_scope_df = date_scope_df[date_scope_df["Source Display"].isin(selected_sources)]
            date_track_names = sorted(date_scope_df["Track Display"].dropna().astype(str).unique().tolist())

            if len(date_track_names) > 1:
                previous_scope = st.session_state.get("date_filter_scope_v68", DATE_SCOPE_SHARED)
                if previous_scope not in {DATE_SCOPE_SHARED, DATE_SCOPE_PER_TRACK}:
                    previous_scope = DATE_SCOPE_SHARED
                st.session_state.date_filter_scope_v68 = previous_scope
                st.markdown("**Date setup**")
                scope_left, scope_right = st.columns(2)
                with scope_left:
                    st.button(
                        DATE_SCOPE_SHARED,
                        type="primary" if previous_scope == DATE_SCOPE_SHARED else "secondary",
                        width="stretch",
                        key="date_scope_shared_button_v68",
                        on_click=set_date_filter_scope_v68,
                        args=(DATE_SCOPE_SHARED,),
                    )
                with scope_right:
                    st.button(
                        DATE_SCOPE_PER_TRACK,
                        type="primary" if previous_scope == DATE_SCOPE_PER_TRACK else "secondary",
                        width="stretch",
                        key="date_scope_per_track_button_v68",
                        on_click=set_date_filter_scope_v68,
                        args=(DATE_SCOPE_PER_TRACK,),
                    )
                date_scope = st.session_state.get("date_filter_scope_v68", DATE_SCOPE_SHARED)
            else:
                date_scope = DATE_SCOPE_SHARED
            st.session_state.date_filter_scope_v68 = date_scope

            if date_scope == DATE_SCOPE_PER_TRACK:
                st.session_state.date_window = st.number_input(
                    "Date window (± days)",
                    min_value=1,
                    max_value=60,
                    value=int(st.session_state.get("date_window", 7)),
                    key="track_date_window_widget_v68",
                )
                st.caption("Choose a date for each track. Turn off Include for non-viral tracks.")
                old_settings = st.session_state.get("track_date_settings_v68", {}) or {}
                next_settings: Dict[str, Dict] = {}
                for track_name in date_track_names:
                    old_setting = old_settings.get(track_name, {}) if isinstance(old_settings, dict) else {}
                    inferred_date = inferred_viral_date_for_track_v68(date_scope_df, track_name)
                    stored_date = input_post_date(old_setting.get("date"))
                    default_date = (
                        stored_date.date()
                        if not pd.isna(stored_date)
                        else inferred_date or st.session_state.get("viral_date", date.today())
                    )
                    suffix = track_date_widget_suffix_v68(track_name)
                    with st.container(border=True):
                        track_col, use_col, date_col = st.columns([2.2, 0.75, 1.05], vertical_alignment="bottom")
                        with track_col:
                            st.markdown(f"**{esc(track_name)}**")
                        with use_col:
                            use_track_date = st.checkbox(
                                "Include",
                                value=bool(old_setting.get("enabled", True)),
                                key=f"track_date_enabled_v68_{suffix}",
                            )
                        with date_col:
                            track_date = st.date_input(
                                f"Viral date for {track_name}",
                                value=default_date,
                                disabled=not use_track_date,
                                key=f"track_date_value_v68_{suffix}",
                                label_visibility="collapsed",
                            )
                    next_settings[track_name] = {
                        "enabled": bool(use_track_date),
                        "date": track_date.isoformat(),
                    }
                st.session_state.track_date_settings_v68 = next_settings
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.session_state.viral_date = st.date_input("Date", value=st.session_state.get("viral_date", date.today()))
                with c2:
                    st.session_state.date_window = st.number_input("Date window (± days)", min_value=1, max_value=60, value=int(st.session_state.get("date_window", 7)))
                window_start = pd.Timestamp(st.session_state.viral_date) - pd.Timedelta(days=int(st.session_state.date_window))
                window_end = pd.Timestamp(st.session_state.viral_date) + pd.Timedelta(days=int(st.session_state.date_window))
                st.caption(
                    f"Date range: {window_start.strftime('%d %b %Y')} to {window_end.strftime('%d %b %Y')}. "
                    "TikTok link dates are used when available."
                )
        if st.session_state.selection_mode == "Top posts":
            # Top N must remain complete, so unavailable and sensitive posts are
            # always replaced by the next eligible ranked candidate.
            st.session_state.replace_unavailable_posts = True

    # Optional filters live inside a collapsed expander, so keep an active date
    # window visible beside the selection results. This prevents a previous batch's
    # date filter from silently carrying into a new Top N/grouping test.
    if st.session_state.get("use_date_filter"):
        active_scope = st.session_state.get("date_filter_scope_v68", DATE_SCOPE_SHARED)
        if active_scope == DATE_SCOPE_PER_TRACK:
            active_settings = st.session_state.get("track_date_settings_v68", {}) or {}
            enabled_settings = {
                track: setting for track, setting in active_settings.items()
                if isinstance(setting, dict) and bool(setting.get("enabled", False))
            }
            st.markdown(
                "<div class='good-note'><b>Date filter on</b> · "
                f"{len(enabled_settings)} tracks · ±{int(st.session_state.get('date_window', 7))} days</div>",
                unsafe_allow_html=True,
            )
        elif st.session_state.get("viral_date"):
            active_window_start = pd.Timestamp(st.session_state.viral_date) - pd.Timedelta(days=int(st.session_state.get("date_window", 7)))
            active_window_end = pd.Timestamp(st.session_state.viral_date) + pd.Timedelta(days=int(st.session_state.get("date_window", 7)))
            st.markdown(
                "<div class='good-note'><b>Date filter on</b> · "
                f"{active_window_start.strftime('%d %b %Y')}–{active_window_end.strftime('%d %b %Y')}</div>",
                unsafe_allow_html=True,
            )

    selected = selected_posts_preview(batch)
    st.session_state.selected_df = selected
    st.markdown("<div class='card'><h3>Selected posts</h3>", unsafe_allow_html=True)
    selected_markets_count = len([m for m in selected.get('Market Display', selected.get('Market', pd.Series(dtype=str))).fillna('').unique() if safe_str(m)]) if not selected.empty else 0
    selected_tracks_count = len([t for t in selected.get('Track Display', selected.get('Track', pd.Series(dtype=str))).fillna('').unique() if safe_str(t)]) if not selected.empty else 0
    if st.session_state.selection_mode == "Top posts":
        rank_summary = ", ".join(st.session_state.get("rank_metrics", ["Total Engagement"]))
        group_summary = st.session_state.get("group_by", "No grouping")
        rank_caption = f"Top {int(st.session_state.get('top_n', 20))} per group" if group_summary != "No grouping" else "Top posts overall"
    else:
        rank_summary = "Original order"
        group_summary = "No grouping"
        rank_caption = "Every filtered link"
    st.markdown(metric_row([
        ("Selected", str(len(selected)), "Posts to tag"),
        ("From batch", str(len(batch)), "Total added"),
        ("Group by", group_summary, rank_caption),
        ("Markets", str(selected_markets_count) if selected_markets_count else "—", "Other included if blank"),
        ("Rank", rank_summary, "Selection logic"),
    ]), unsafe_allow_html=True)
    st.markdown(render_table(selected, max_rows=12, cols=["Source", "Link", "Market", "Track", "Creator", "Followers", "KOL Size", "Views", "Likes", "Comments", "Shares", "Saves", "Total Engagement", "Engagement Rate"]), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Back", width="stretch"):
            go(2)
    with c2:
        if st.button("Continue", type="primary", width="stretch"):
            go(4)
    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------
# STEP 4
# -----------------------------
elif st.session_state.step == 4:
    selected = st.session_state.selected_df if not st.session_state.selected_df.empty else selected_posts_preview(st.session_state.batch_df)
    st.markdown("<div class='card'><h2>Run tagging</h2></div>", unsafe_allow_html=True)
    if selected.empty:
        st.markdown("<div class='warn-note'>No selected posts yet.</div>", unsafe_allow_html=True)
        if st.button("Go to Select Posts", type="primary"):
            go(3)
        st.stop()
    st.markdown(metric_row([
        ("Posts", str(len(selected)), "To tag"),
        ("Mode", "General" if st.session_state.mode.startswith("General") else "Drama", "Taxonomy"),
        ("Markets", str(len([m for m in selected['Market'].fillna('').unique() if safe_str(m)])), "Detected"),
        ("Tracks", str(len([t for t in selected['Track'].fillna('').unique() if safe_str(t)])), "Detected"),
        ("Selection", st.session_state.get("selection_mode", "Top posts"), "Method"),
    ]), unsafe_allow_html=True)
    st.markdown(render_table(selected, max_rows=10, cols=["Link", "Market", "Track", "Creator", "Followers", "KOL Size", "Views", "Total Engagement", "Engagement Rate"]), unsafe_allow_html=True)
    # Full-video fallback is kept disabled in the marketing-facing app for speed/quota stability.
    st.session_state.enable_full_video_fallback_v46 = False
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Back", width="stretch"):
            go(3)
    with c2:
        if st.button("Start tagging", type="primary", width="stretch"):
            tagged_result = run_real_tagging_backend(selected)
            if tagged_result is not None and not tagged_result.empty:
                st.session_state.tagged_df = tagged_result
                go(5)
            else:
                st.warning("No tagged rows were created. Please check your API keys, selected links, or Apify/Gemini error message above.")

# -----------------------------
# STEP 5
# -----------------------------
elif st.session_state.step == 5:
    tagged = st.session_state.tagged_df
    st.markdown("<div class='card'><h2>Review</h2><p class='sub'>Check the posts that still need a human decision.</p></div>", unsafe_allow_html=True)

    if tagged.empty:
        st.markdown("<div class='warn-note'>No tagged rows yet.</div>", unsafe_allow_html=True)
        if st.button("Go to Run Tagging", type="primary"):
            go(4)
        st.stop()

    review_action_series = tagged.get("Review Action", pd.Series([""] * len(tagged), index=tagged.index)).fillna("").astype(str).str.upper()
    review_df = tagged[(tagged.get("Needs Review", False) == True) & (review_action_series != "REMOVE")].copy()

    if review_df.empty:
        st.markdown("<div class='good-note'>All flagged posts have been reviewed.</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Back to Run Tagging", width="stretch"):
                go(4)
        with c2:
            if st.button("Continue to Summary", type="primary", width="stretch"):
                go(6)
        st.stop()

    # Original-app style: one review item at a time, with Previous / Skip navigation.
    pointer = int(st.session_state.get("review_pointer", 0) or 0)
    pointer = max(0, min(pointer, len(review_df) - 1))
    st.session_state.review_pointer = pointer
    original_idx = review_df.index[pointer]
    row = tagged.loc[original_idx]

    st.progress((pointer + 1) / max(len(review_df), 1))
    nav1, nav2, nav3 = st.columns([1.15, 5, 1.15])
    with nav1:
        if st.button("Previous", disabled=(pointer == 0), width="stretch", key=f"review_prev_{original_idx}"):
            st.session_state.review_pointer = max(0, pointer - 1)
            st.rerun()
    with nav2:
        st.markdown(
            f"<div style='text-align:center;color:#64748b;font-size:13px;font-weight:800;padding:10px 0'>Post {pointer + 1} of {len(review_df)}</div>",
            unsafe_allow_html=True,
        )
    with nav3:
        if st.button("Skip", width="stretch", key=f"review_skip_{original_idx}"):
            st.session_state.review_pointer = (pointer + 1) % len(review_df)
            st.rerun()

    link = safe_str(row.get("Link"))
    creator = safe_str(row.get("Creator")) or extract_creator(link) or "Unknown creator"
    market = display_market(row.get("Market"))
    track = display_empty(row.get("Track"), "Not specified")
    caption = display_empty(row.get("Caption"), "No caption available")
    views = clean_num(row.get("Views"))
    likes = clean_num(row.get("Likes"))
    shares = clean_num(row.get("Shares"))
    reason = display_empty(
        _first_nonblank_v43(row.get("Review Note"), row.get("QA Reason"), row.get("Reasoning")),
        "The AI result needs a manual check.",
    )
    current_type = safe_str(row.get("Creative Type"))
    current_narrative = safe_str(row.get("Narrative"))
    current_details = safe_str(row.get("Content Details"))

    image_url = ""
    for possible_col in ["Cover URL", "cover_url", "Thumbnail", "thumbnail", "Image", "image_url"]:
        if possible_col in tagged.columns and safe_str(row.get(possible_col)):
            image_url = safe_str(row.get(possible_col))
            break
    video_url = ""
    for possible_col in ["Video URL", "video_url", "Video", "video"]:
        if possible_col in tagged.columns and safe_str(row.get(possible_col)):
            video_url = safe_str(row.get(possible_col))
            break

    left, middle, right = st.columns([0.82, 1.18, 1.48], gap="large")

    with left:
        _render_review_preview_v45(image_url, video_url, link, st.session_state.get("apify_token", ""))

    with middle:
        st.markdown(
            f"""
            <div class='review-info-card'>
              <div class='review-label'>Creator</div>
              <div class='review-value'>@{esc(creator)}</div>
              <div class='review-label'>Market · Track</div>
              <div class='review-value'>{esc(market)} · {esc(track)}</div>
              <div class='review-label'>Caption</div>
              <div class='review-value' style='white-space:pre-wrap'>{esc(caption)}</div>
              <div class='review-stats'>
                <div class='review-stat'><div class='num'>{views:,}</div><div class='lbl'>Views</div></div>
                <div class='review-stat'><div class='num'>{likes:,}</div><div class='lbl'>Likes</div></div>
                <div class='review-stat'><div class='num'>{shares:,}</div><div class='lbl'>Shares</div></div>
              </div>
              <div class='review-label'>Flagged reason</div>
              <div class='review-reason'>{esc(reason)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        action_key = f"review_action_v55_{original_idx}"
        if action_key not in st.session_state:
            st.session_state[action_key] = "Keep & Tag"

        st.markdown("<div class='review-panel-card'><h3>Review Action</h3><div class='review-action-title'>What should happen to this post?</div>", unsafe_allow_html=True)
        keep_col, remove_col = st.columns(2)
        with keep_col:
            if st.button(
                "Keep & Tag",
                type="primary" if st.session_state[action_key] == "Keep & Tag" else "secondary",
                width="stretch",
                key=f"review_keep_v55_{original_idx}",
            ):
                st.session_state[action_key] = "Keep & Tag"
                st.rerun()
        with remove_col:
            if st.button(
                "Remove / Ignore",
                type="primary" if st.session_state[action_key] == "Remove" else "secondary",
                width="stretch",
                key=f"review_remove_v55_{original_idx}",
            ):
                st.session_state[action_key] = "Remove"
                st.rerun()

        if st.session_state[action_key] == "Remove":
            st.markdown("<div class='review-note-warn'>This post will be excluded from the final CSV/XLSX.</div>", unsafe_allow_html=True)
            remove_reason = st.text_input(
                "Removal reason",
                value="Unavailable / wrong link / not relevant",
                key=f"review_remove_reason_v55_{original_idx}",
            )
            if st.button("Confirm remove & next", type="primary", width="stretch", key=f"review_confirm_remove_v55_{original_idx}"):
                audit_fields = final_update2_review_audit_update(
                    row.get("Original AI Labels", row.get("Creative Type", "Others")),
                    row.get("Final Labels", row.get("Creative Type", "Others")),
                    row.get("Label History", ""),
                    action="REMOVE",
                    note=remove_reason,
                )
                for column, value in audit_fields.items():
                    st.session_state.tagged_df.at[original_idx, column] = value
                st.session_state.tagged_df.at[original_idx, "Review Action"] = "REMOVE"
                st.session_state.tagged_df.at[original_idx, "Needs Review"] = False
                st.session_state.tagged_df.at[original_idx, "Review Note"] = remove_reason
                st.session_state.tagged_df.at[original_idx, "QA Reason"] = remove_reason
                st.session_state.tagged_df.at[original_idx, "QA Priority"] = "Removed"
                st.session_state.tagged_df.at[original_idx, "Tier Used"] = "tier3_human"
                st.session_state.tagged_df.at[original_idx, "Validation Status"] = "removed"
                st.session_state.review_pointer = 0
                st.session_state.pop(action_key, None)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='review-note-info'>Keep the post, confirm or edit the tags below, then save.</div></div>", unsafe_allow_html=True)
            st.markdown("<div class='review-panel-card'><h3>Fill in the tags</h3>", unsafe_allow_html=True)

            ai_result_key = f"review_ai_result_v55_{original_idx}"
            narrative_key = f"review_narrative_v55_{original_idx}"
            type_key = f"review_type_v55_{original_idx}"
            details_key = f"review_details_v55_{original_idx}"

            if narrative_key not in st.session_state:
                st.session_state[narrative_key] = current_narrative
            if type_key not in st.session_state:
                st.session_state[type_key] = [x.strip() for x in current_type.split(",") if x.strip() in CREATIVE_TYPES][:2]
            if details_key not in st.session_state:
                st.session_state[details_key] = current_details

            if st.button("AI Suggest", width="stretch", key=f"review_ai_suggest_v55_{original_idx}"):
                gemini_key_r = clean_api_secret(st.session_state.get("gemini_key", ""))
                apify_token_r = clean_api_secret(st.session_state.get("apify_token", ""))
                if not gemini_key_r:
                    st.error("Save your Gemini API key in Step 1 first.")
                else:
                    with st.spinner("Analysing this post with Gemini..."):
                        suggestion = _review_ai_suggest_final_update2(row, gemini_key_r, apify_token_r)
                    st.session_state[ai_result_key] = suggestion
                    if suggestion.get("parse_error"):
                        st.error(f"AI Suggest failed: {safe_str(suggestion.get('raw_response'))}")
                    else:
                        suggested_labels = [x.strip() for x in safe_str(suggestion.get("Creative Type")).split(",") if x.strip() in CREATIVE_TYPES][:2]
                        st.session_state[narrative_key] = safe_str(suggestion.get("Narrative"))
                        st.session_state[type_key] = suggested_labels
                        st.session_state[details_key] = safe_str(suggestion.get("Content Details"))
                        st.rerun()

            ai_prefill = st.session_state.get(ai_result_key, {})
            if ai_prefill and not ai_prefill.get("parse_error"):
                ai_conf = float(ai_prefill.get("Confidence", 0) or 0)
                ai_labels = safe_str(ai_prefill.get("Creative Type")) or "—"
                ai_reason = safe_str(ai_prefill.get("Reasoning"))
                st.markdown(
                    f"<div class='review-note-info'><strong>AI suggestion:</strong> {esc(ai_labels)} · {ai_conf:.0%} confidence"
                    + (f"<br><span style='font-size:12px;color:#64748b'>{esc(ai_reason)}</span>" if ai_reason else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
            elif ai_prefill and ai_prefill.get("parse_error"):
                st.markdown("<div class='review-note-warn'>AI Suggest could not analyse this post. Please tag it manually.</div>", unsafe_allow_html=True)

            narrative = st.text_input("Narrative", key=narrative_key)
            creative_types = st.multiselect("Creative Type (max 2)", CREATIVE_TYPES, max_selections=2, key=type_key)
            details = st.text_area("Content Details", height=130, key=details_key)

            # final_update_2 manual-metrics workflow. Scraper exception/sensitive
            # rows often retain a usable TikTok link but have no engagement data.
            metric_values = {
                "Views": clean_num(row.get("Views")),
                "Likes": clean_num(row.get("Likes")),
                "Comments": clean_num(row.get("Comments")),
                "Shares": clean_num(row.get("Shares")),
                "Saves": clean_num(row.get("Saves")),
            }
            needs_manual_metrics = bool(row.get("Manual Metrics Required", False)) or safe_str(row.get("Tier Used")) in {
                "scraper_exception", "sensitive_human_review"
            } or all(value == 0 for value in metric_values.values())
            metric_keys = {name: f"review_metric_{name.lower()}_v56_{original_idx}" for name in metric_values}
            if needs_manual_metrics:
                st.markdown(
                    "<div class='review-note-warn'>Metrics were not captured by the scraper. Open the TikTok link and enter the current numbers before saving.</div>",
                    unsafe_allow_html=True,
                )
                mc1, mc2 = st.columns(2)
                with mc1:
                    manual_views = st.number_input("Views", min_value=0, value=metric_values["Views"], step=1, key=metric_keys["Views"])
                    manual_likes = st.number_input("Likes", min_value=0, value=metric_values["Likes"], step=1, key=metric_keys["Likes"])
                    manual_comments = st.number_input("Comments", min_value=0, value=metric_values["Comments"], step=1, key=metric_keys["Comments"])
                with mc2:
                    manual_shares = st.number_input("Shares", min_value=0, value=metric_values["Shares"], step=1, key=metric_keys["Shares"])
                    manual_saves = st.number_input("Saves", min_value=0, value=metric_values["Saves"], step=1, key=metric_keys["Saves"])
            else:
                manual_views = metric_values["Views"]
                manual_likes = metric_values["Likes"]
                manual_comments = metric_values["Comments"]
                manual_shares = metric_values["Shares"]
                manual_saves = metric_values["Saves"]

            if st.button("Save & next", type="primary", width="stretch", key=f"review_save_v55_{original_idx}"):
                if not narrative or not creative_types or not details:
                    st.error("Please fill Narrative, at least one Creative Type, and Content Details before saving.")
                elif needs_manual_metrics and int(manual_views) == 0 and int(manual_likes) == 0 and int(manual_shares) == 0:
                    st.error("Please enter the TikTok metrics before saving.")
                else:
                    selected_label_text = ", ".join(creative_types)
                    audit_fields = final_update2_review_audit_update(
                        row.get("Original AI Labels", row.get("Creative Type", "Others")),
                        selected_label_text,
                        row.get("Label History", ""),
                        action="KEEP",
                        note="Reviewed manually",
                    )
                    for column, value in audit_fields.items():
                        st.session_state.tagged_df.at[original_idx, column] = value
                    st.session_state.tagged_df.at[original_idx, "Narrative"] = narrative
                    st.session_state.tagged_df.at[original_idx, "Creative Type"] = audit_fields["Final Labels"]
                    st.session_state.tagged_df.at[original_idx, "Content Details"] = details
                    st.session_state.tagged_df.at[original_idx, "Views"] = int(manual_views)
                    st.session_state.tagged_df.at[original_idx, "Likes"] = int(manual_likes)
                    st.session_state.tagged_df.at[original_idx, "Comments"] = int(manual_comments)
                    st.session_state.tagged_df.at[original_idx, "Shares"] = int(manual_shares)
                    st.session_state.tagged_df.at[original_idx, "Saves"] = int(manual_saves)
                    st.session_state.tagged_df.at[original_idx, "Manual Metrics Required"] = False
                    st.session_state.tagged_df.at[original_idx, "Needs Review"] = False
                    st.session_state.tagged_df.at[original_idx, "Review Action"] = "KEEP"
                    st.session_state.tagged_df.at[original_idx, "Review Note"] = "Reviewed manually"
                    st.session_state.tagged_df.at[original_idx, "QA Priority"] = "Reviewed"
                    st.session_state.tagged_df.at[original_idx, "Tier Used"] = "tier3_human"
                    st.session_state.tagged_df.at[original_idx, "Validation Status"] = "reviewed"
                    st.session_state.tagged_df = add_performance_fields(st.session_state.tagged_df)
                    st.session_state.review_pointer = 0
                    for key in [ai_result_key, narrative_key, type_key, details_key, action_key, *metric_keys.values()]:
                        st.session_state.pop(key, None)
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Back", width="stretch", key="review_back_v55"):
            go(4)
    with c2:
        if st.button("Continue to Summary", type="primary", width="stretch", key="review_continue_v55"):
            go(6)

# -----------------------------
# STEP 6
# -----------------------------
elif st.session_state.step == 6:
    tagged = st.session_state.tagged_df
    st.markdown("<div class='card'><h2>Summary & Export</h2></div>", unsafe_allow_html=True)
    if tagged.empty:
        st.markdown("<div class='warn-note'>No tagged rows yet.</div>", unsafe_allow_html=True)
        if st.button("Go to Run Tagging", type="primary"):
            go(4)
        st.stop()

    # Marketing summary excludes auto-removed unavailable/private posts. The
    # internal QA workbook still receives every attempted row below.
    qa_all_rows = tagged.copy()
    work = tagged[~_removed_mask_v56(tagged)].copy()
    for col in ["Source", "Input Type", "Link", "Market", "Track", "Creator", "Date", "Creative Type", "Narrative", "Content Details", "KOL Size"]:
        if col not in work.columns:
            work[col] = ""
    for col in ["Views", "Likes", "Comments", "Shares", "Saves", "Total Engagement", "Followers"]:
        if col not in work.columns:
            work[col] = 0
        work[col] = work[col].map(clean_num)
    work["Market Display"] = work["Market"].map(display_market)
    work["Track Display"] = work["Track"].map(lambda x: display_empty(x, "Not specified"))
    work["Source Display"] = work["Source"].map(lambda x: display_empty(x, "Manual / pasted links"))
    work["Creative Type"] = work["Creative Type"].map(lambda x: display_empty(x, "Others"))
    work["Primary Creative Type"] = work["Creative Type"].map(primary_creative_type)
    work["KOL Size Display"] = work["KOL Size"].map(lambda x: display_empty(x, "Unknown"))

    # Combined filters: users can focus by source + market + track + creative type, then sort the post table by any metric.
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        source_opts = ["All"] + sorted(work["Source Display"].dropna().unique().tolist())
        source_filter = st.selectbox("Source", source_opts, key="summary_source_v28")
    with f2:
        market_opts = ["All"] + sorted(work["Market Display"].dropna().unique().tolist())
        market_filter = st.selectbox("Market", market_opts, key="summary_market_v28")
    with f3:
        track_opts = ["All"] + sorted(work["Track Display"].dropna().unique().tolist())
        track_filter = st.selectbox("Track", track_opts, key="summary_track_v28")
    with f4:
        type_opts = ["All"] + sorted(work["Primary Creative Type"].dropna().unique().tolist())
        type_filter = st.selectbox("Creative Type", type_opts, key="summary_type_v55")
    m1, m2 = st.columns([1, 1])
    metric_choices = ["Views", "Total Engagement", "Likes", "Comments", "Shares", "Saves", "Followers", "Engagement Rate", "Likes Rate", "Comments Rate", "Shares Rate", "Saves Rate"]
    with m1:
        focus_metric = st.selectbox("Sort post table by", metric_choices, key="summary_metric_v28")
    with m2:
        sort_order = st.selectbox("Order", ["Highest first", "Lowest first"], key="summary_sort_v28")

    filtered = work.copy()
    if source_filter != "All":
        filtered = filtered[filtered["Source Display"] == source_filter]
    if market_filter != "All":
        filtered = filtered[filtered["Market Display"] == market_filter]
    if track_filter != "All":
        filtered = filtered[filtered["Track Display"] == track_filter]
    if type_filter != "All":
        filtered = filtered[filtered["Primary Creative Type"] == type_filter]

    total_views = int(filtered["Views"].sum())
    total_eng = int(filtered["Total Engagement"].sum())
    er = (total_eng / total_views * 100) if total_views else 0
    avg_views = int(total_views / len(filtered)) if len(filtered) and total_views else 0
    market_count = len([m for m in filtered["Market"].fillna("").unique().tolist() if safe_str(m)])
    track_count = len([t for t in filtered["Track"].fillna("").unique().tolist() if safe_str(t)])
    has_metrics = bool(total_views or total_eng or filtered[["Likes", "Comments", "Shares", "Saves"]].sum().sum())
    filtered["Engagement Rate"] = filtered.apply(lambda r: (clean_num(r.get("Total Engagement")) / clean_num(r.get("Views")) * 100) if clean_num(r.get("Views")) else 0, axis=1)

    st.markdown(summary_kpi_row([
        ("Posts", f"{len(filtered):,}", "", "kpi-purple"),
        ("Views", short_num(total_views) if has_metrics else "—", "", "kpi-blue"),
        ("Engagements", short_num(total_eng) if has_metrics else "—", "Likes + comments + shares + saves", "kpi-orange"),
        ("Engagement Rate", f"{er:.1f}%" if has_metrics else "—", "Engagements / views", "kpi-green"),
        ("Markets", str(market_count) if market_count else "—", "", "kpi-pink"),
    ]), unsafe_allow_html=True)

    if not has_metrics:
        st.markdown("<div class='soft-note'>Metrics are not available yet. Once Apify refreshes views, likes, comments, shares, and saves, the performance sections will populate automatically.</div>", unsafe_allow_html=True)

    top_type = display_empty(filtered["Primary Creative Type"].mode().iloc[0] if not filtered.empty else "", "—")
    top_type_count = int((filtered["Primary Creative Type"] == top_type).sum()) if top_type != "—" else 0
    top_market = display_empty(filtered["Market Display"].mode().iloc[0] if not filtered.empty else "", "Other")
    top_track = display_empty(filtered["Track Display"].mode().iloc[0] if not filtered.empty else "", "Not specified")
    source_text = "Mixed sources" if filtered["Source Display"].nunique() > 1 else display_empty(filtered["Source Display"].iloc[0] if len(filtered) else "", "—")
    if has_metrics and not filtered.empty:
        type_perf = filtered.groupby("Primary Creative Type", dropna=False).agg(Views=("Views", "sum"), Posts=("Link", "count")).reset_index()
        highest_views_type = display_empty(type_perf.sort_values("Views", ascending=False).iloc[0]["Primary Creative Type"], "—")
        highest_views_total = int(type_perf.sort_values("Views", ascending=False).iloc[0]["Views"])
        best_perf_sub = f"{short_num(highest_views_total)} views"
    else:
        highest_views_type = "Metrics pending"
        best_perf_sub = "Connect Apify metrics to see performance"

    st.markdown(focus_cards([
        ("Most common format", top_type, "", "focus-purple"),
        ("Best reach type", highest_views_type, best_perf_sub, "focus-blue"),
        ("Main market", top_market, "", "focus-green"),
        ("Track / source", top_track if top_track != "Not specified" else source_text, "", "focus-orange"),
    ]), unsafe_allow_html=True)

    # Visual summary. Use custom visible bars instead of a plain white chart, so every number is obvious.
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<div class='card'>" + section_title("Creative Type Mix", "#6254e8"), unsafe_allow_html=True)
        mix = filtered["Primary Creative Type"].value_counts().reset_index()
        mix.columns = ["Creative Type", "Posts"]
        st.markdown(bar_list(mix, "Creative Type", "Posts", max_rows=12, value_suffix="posts", show_share=True), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        metric_for_chart = focus_metric if focus_metric != "Engagement Rate" else "Views"
        metric_title = f"{metric_for_chart} by Creative Type"
        st.markdown("<div class='card'>" + section_title(metric_title, "#0ea5e9"), unsafe_allow_html=True)
        if has_metrics and metric_for_chart in filtered.columns:
            metric_mix = filtered.groupby("Primary Creative Type", dropna=False)[metric_for_chart].sum().reset_index().rename(columns={"Primary Creative Type": "Creative Type"}).sort_values(metric_for_chart, ascending=False)
            st.markdown(bar_list(metric_mix.head(12), "Creative Type", metric_for_chart, max_rows=12), unsafe_allow_html=True)
        else:
            st.markdown("<div class='empty-panel'>Performance chart will appear after metrics are available.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Source summary is useful when users mix uploaded files and pasted links.
    if filtered["Source Display"].nunique() > 1:
        st.markdown("<div class='card'>" + section_title("Source Summary", "#8b5cf6"), unsafe_allow_html=True)
        source_summary = filtered.groupby("Source Display", dropna=False).agg(
            Posts=("Link", "count"), Views=("Views", "sum"), Likes=("Likes", "sum"), Comments=("Comments", "sum"), Shares=("Shares", "sum"), Saves=("Saves", "sum"), Engagements=("Total Engagement", "sum")
        ).reset_index().rename(columns={"Source Display": "Source"})
        source_summary["Engagement Rate"] = source_summary.apply(lambda r: f"{(r['Engagements']/r['Views']*100):.1f}%" if r["Views"] else "—", axis=1)
        st.markdown(render_table(source_summary.sort_values("Views" if focus_metric == "Engagement Rate" else focus_metric if focus_metric in source_summary.columns else "Views", ascending=(sort_order == "Lowest first")), max_rows=12, cols=["Source", "Posts", "Views", "Engagements", "Engagement Rate"]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>" + section_title("Market Summary", "#10b981"), unsafe_allow_html=True)
    if market_count:
        market_summary = filtered.groupby("Market Display", dropna=False).agg(
            Posts=("Link", "count"), Views=("Views", "sum"), Likes=("Likes", "sum"), Comments=("Comments", "sum"), Shares=("Shares", "sum"), Saves=("Saves", "sum"), Engagements=("Total Engagement", "sum")
        ).reset_index().rename(columns={"Market Display": "Market"})
        market_summary["Engagement Rate"] = market_summary.apply(lambda r: f"{(r['Engagements']/r['Views']*100):.1f}%" if r["Views"] else "—", axis=1)
        market_sort_col = "Views" if focus_metric == "Engagement Rate" else focus_metric if focus_metric in market_summary.columns else "Views"
        market_summary = market_summary.sort_values([market_sort_col, "Posts"], ascending=[(sort_order == "Lowest first"), False])
        st.markdown(render_table(market_summary, max_rows=12, cols=["Market", "Posts", "Views", "Engagements", "Engagement Rate"]), unsafe_allow_html=True)
    else:
        st.markdown("<div class='empty-panel'>No market data provided. Rows without market are grouped as Other.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # KOL performance follows every Summary filter. When several markets are
    # visible, include Market in the grouping because KOL thresholds differ by
    # country; within one market, keep the view compact by showing KOL Size only.
    st.markdown("<div class='card'>" + section_title("KOL Size Performance", "#14b8a6"), unsafe_allow_html=True)
    if filtered.empty:
        st.markdown("<div class='empty-panel'>No posts are available in the current view.</div>", unsafe_allow_html=True)
    else:
        kol_group_cols = ["KOL Size Display"]
        if market_filter == "All":
            kol_group_cols = ["Market Display", "KOL Size Display"]
        kol_summary = filtered.groupby(kol_group_cols, dropna=False).agg(
            Posts=("Link", "count"),
            Average_Views=("Views", "mean"),
            Average_Engagements=("Total Engagement", "mean"),
            Median_Engagement_Rate=("Engagement Rate", "median"),
            Total_Views=("Views", "sum"),
            Total_Shares=("Shares", "sum"),
            Total_Saves=("Saves", "sum"),
        ).reset_index()
        kol_summary["Shares Rate"] = kol_summary.apply(
            lambda row: (row["Total_Shares"] / row["Total_Views"] * 100) if row["Total_Views"] else 0,
            axis=1,
        )
        kol_summary["Saves Rate"] = kol_summary.apply(
            lambda row: (row["Total_Saves"] / row["Total_Views"] * 100) if row["Total_Views"] else 0,
            axis=1,
        )
        if market_filter == "All":
            kol_summary["Performance Group"] = kol_summary.apply(
                lambda row: f"{display_empty(row.get('Market Display'), 'Other')} · {display_empty(row.get('KOL Size Display'), 'Unknown')}",
                axis=1,
            )
        else:
            kol_summary["Performance Group"] = kol_summary["KOL Size Display"].map(lambda value: display_empty(value, "Unknown"))

        k1, k2 = st.columns(2)
        with k1:
            kol_views_chart = kol_summary[["Performance Group", "Average_Views"]].copy()
            kol_views_chart["Average Views"] = kol_views_chart["Average_Views"].round().astype(int)
            chart_bar(
                kol_views_chart.sort_values("Average Views", ascending=False).head(12),
                "Performance Group",
                "Average Views",
                "Average Views by KOL Size",
                orientation="h",
                value_format="integer",
            )
        with k2:
            kol_rate_chart = kol_summary[["Performance Group", "Median_Engagement_Rate"]].copy()
            kol_rate_chart["Median Engagement Rate"] = kol_rate_chart["Median_Engagement_Rate"].round(2)
            chart_bar(
                kol_rate_chart.sort_values("Median Engagement Rate", ascending=False).head(12),
                "Performance Group",
                "Median Engagement Rate",
                "Median Engagement Rate by KOL Size",
                orientation="h",
                value_format="percent",
            )

        kol_table = kol_summary.copy()
        if market_filter == "All":
            kol_table = kol_table.rename(columns={"Market Display": "Market", "KOL Size Display": "KOL Size"})
            kol_cols = ["Market", "KOL Size", "Posts", "Average Views", "Average Engagements", "Median Engagement Rate", "Shares Rate", "Saves Rate"]
        else:
            kol_table = kol_table.rename(columns={"KOL Size Display": "KOL Size"})
            kol_cols = ["KOL Size", "Posts", "Average Views", "Average Engagements", "Median Engagement Rate", "Shares Rate", "Saves Rate"]
        kol_table = kol_table.rename(columns={
            "Average_Views": "Average Views",
            "Average_Engagements": "Average Engagements",
            "Median_Engagement_Rate": "Median Engagement Rate",
        })
        kol_table["Average Views"] = kol_table["Average Views"].map(lambda value: f"{int(round(value)):,}")
        kol_table["Average Engagements"] = kol_table["Average Engagements"].map(lambda value: f"{int(round(value)):,}")
        for rate_col in ["Median Engagement Rate", "Shares Rate", "Saves Rate"]:
            kol_table[rate_col] = kol_table[rate_col].map(lambda value: f"{float(value):.2f}%")
        st.markdown(render_table(kol_table, max_rows=40, cols=kol_cols), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>" + section_title("Track Summary", "#f97316"), unsafe_allow_html=True)
    track_summary = filtered.groupby(["Market Display", "Track Display"], dropna=False).agg(
        Posts=("Link", "count"), Views=("Views", "sum"), Likes=("Likes", "sum"), Comments=("Comments", "sum"), Shares=("Shares", "sum"), Saves=("Saves", "sum"), Engagements=("Total Engagement", "sum")
    ).reset_index().rename(columns={"Market Display": "Market", "Track Display": "Track"})
    track_summary["Engagement Rate"] = track_summary.apply(lambda r: f"{(r['Engagements']/r['Views']*100):.1f}%" if r["Views"] else "—", axis=1)
    track_sort_col = "Views" if focus_metric == "Engagement Rate" else focus_metric if focus_metric in track_summary.columns else "Views"
    track_summary = track_summary.sort_values([track_sort_col, "Posts"], ascending=[(sort_order == "Lowest first"), False])
    st.markdown(render_table(track_summary, max_rows=12, cols=["Market", "Track", "Posts", "Views", "Engagements", "Engagement Rate"]), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if has_metrics:
        st.markdown("<div class='card'>" + section_title("Top Posts", "#ec4899"), unsafe_allow_html=True)
        top_posts = filtered.copy()
        sort_col = focus_metric if focus_metric in top_posts.columns else "Views"
        top_posts = top_posts.sort_values([sort_col, "Total Engagement"], ascending=[sort_order == "Lowest first", False])
        top_posts["Engagement Rate"] = top_posts.apply(lambda r: f"{(r['Total Engagement']/r['Views']*100):.1f}%" if r["Views"] else "—", axis=1)
        top_posts["Track"] = top_posts["Track Display"]
        top_posts["Market"] = top_posts["Market Display"]
        st.markdown(render_table(top_posts, max_rows=15, cols=["Creator", "Market", "Track", "Creative Type", "Followers", "KOL Size", "Views", "Total Engagement", "Engagement Rate", "Link"]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Post-level checking is handled by the Review page and final downloads.
    # Keep the marketing Summary focused on performance, mix, market/track/source summaries, and downloads.
    summary_df = filtered.copy()
    summary_df["Market"] = summary_df["Market Display"]
    summary_df["Track"] = summary_df["Track Display"]
    sort_col = focus_metric if focus_metric in summary_df.columns else "Views"

    st.markdown("<div class='card'>" + section_title("Downloads", "#6254e8"), unsafe_allow_html=True)
    # Clean marketing export: no QA/debug columns here.
    # QA Priority / QA Reason / validation details belong only in the Review / QA Report.
    export_base_df = summary_df.copy()
    if "Review Action" in export_base_df.columns:
        export_base_df = export_base_df[export_base_df["Review Action"].astype(str).str.upper() != "REMOVE"]
    if "Creative Type" in export_base_df.columns:
        export_base_df = export_base_df[export_base_df["Creative Type"].astype(str).str.lower() != "removed"]
    for _bad_placeholder in [
        "AI could not confidently classify this post.",
        "No detailed description returned.",
        "Post was unavailable, private, deleted, or not returned by Apify.",
        "Preview only. Add API keys to run Apify + Gemini.",
    ]:
        if "Content Details" in export_base_df.columns:
            export_base_df["Content Details"] = export_base_df["Content Details"].replace(_bad_placeholder, "")
    final_df = export_base_df[[c for c in MARKETING_EXPORT_COLUMNS if c in export_base_df.columns]].copy()
    final_sort_col = sort_col if sort_col in final_df.columns else ("Views" if "Views" in final_df.columns else None)
    if "Market" in final_df.columns:
        try:
            if final_sort_col:
                final_df = final_df.sort_values(["Market", "Track", final_sort_col], ascending=[True, True, sort_order == "Lowest first"])
            else:
                final_df = final_df.sort_values(["Market", "Track"], ascending=True)
        except Exception:
            final_df = final_df.sort_values([c for c in ["Market", "Track"] if c in final_df.columns], ascending=True)
    qa_df = qa_all_rows.copy()
    qa_front = [
        "App Version", "Source", "Input Type", "Link", "Market", "Track", "Creator",
        "Narrative", "Creative Type", *QA_AUDIT_COLUMNS, "Content Details",
        "Needs Review", "Review Action", "Review Note", "Review Risk",
        "Tier Used", "Validation Status", "Validation Score",
    ]
    qa_front = [column for column in qa_front if column in qa_df.columns]
    qa_df = qa_df[qa_front + [column for column in qa_df.columns if column not in qa_front]]
    report = {
        "Summary": pd.DataFrame([{
            "App Version": "v68.9",
            "Posts": len(filtered),
            "Views": total_views,
            "Engagements": total_eng,
            "Engagement Rate": f"{er:.1f}%" if has_metrics else "Metrics unavailable",
            "Top Creative Type": top_type,
            "Top Market": top_market,
            "Top Track": top_track,
            "Source": source_text,
            "Current Sort Metric": selection_rank_metric_label(
                st.session_state.get("selection_mode", "Top posts"),
                st.session_state.get("rank_metrics", ["Total Engagement"]),
            ),
        }]),
        "Final Output": final_df,
        "Rows To Review": qa_df[qa_df.get("Needs Review", False) == True] if "Needs Review" in qa_df.columns else pd.DataFrame(),
        "All Rows": qa_df,
    }
    st.markdown("""
    <div class='download-grid'>
      <div class='download-card'><strong>Final CSV</strong><span>Clean output sorted/grouped by market when market is available.</span></div>
      <div class='download-card'><strong>Grouped XLSX</strong><span>Excel workbook with All Posts, market tabs, and Links Only.</span></div>
      <div class='download-card'><strong>Review / QA Report</strong><span>Internal file with review rows, QA priority, QA reason, confidence and diagnostics.</span></div>
    </div>
    """, unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button("Download Final CSV", final_df.to_csv(index=False).encode("utf-8-sig"), "tagged_posts_final_grouped.csv", "text/csv", width="stretch")
    with d2:
        st.download_button("Download Grouped XLSX", grouped_excel_bytes(final_df), "tagged_posts_grouped_by_market.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    with d3:
        st.download_button("Download Review / QA Report", to_excel_bytes(report), "review_qa_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Back to Review", width="stretch"):
            go(5)
    with c2:
        if st.button("Start new batch", type="primary", width="stretch"):
            st.session_state.batch_df = pd.DataFrame()
            st.session_state.selected_df = pd.DataFrame()
            st.session_state.tagged_df = pd.DataFrame()
            st.session_state.last_message = ""
            reset_date_filter_state_v68()
            go(2)
