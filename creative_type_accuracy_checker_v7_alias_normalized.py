import io
import re
from typing import Set, Optional, List

import pandas as pd
import streamlit as st

from accuracy_metrics import (
    contains_match,
    contains_reason,
    exact_match,
    normalize_label,
    primary_match,
    primary_reason,
    split_label_list,
    split_labels,
)

st.set_page_config(page_title="Creative Type Accuracy Checker - Stable", layout="wide")

st.title("Creative Type Accuracy Checker")
st.caption("A row passes when at least one AI label matches a manual label. Primary-label and exact-match scores are shown only as stricter diagnostics.")

# -----------------------------
# Helpers
# -----------------------------

def is_blank(x) -> bool:
    if pd.isna(x):
        return True
    s = str(x).strip()
    return s == "" or s.lower() in {"nan", "none", "null", "na", "n/a", "-", "--"}


def read_file(uploaded_file) -> pd.DataFrame:
    """Robust CSV/XLSX reader for Streamlit uploads."""
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()

    if name.endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(io.BytesIO(raw), engine="openpyxl")
        except Exception:
            # Fallback without explicit engine
            return pd.read_excel(io.BytesIO(raw))

    if name.endswith(".csv"):
        # Try common encodings and separators
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
        last_err = None
        for enc in encodings:
            try:
                return pd.read_csv(io.BytesIO(raw), encoding=enc)
            except Exception as e:
                last_err = e
        # Try autodetect separator
        for enc in encodings:
            try:
                return pd.read_csv(io.BytesIO(raw), encoding=enc, sep=None, engine="python", on_bad_lines="skip")
            except Exception as e:
                last_err = e
        raise last_err

    raise ValueError("Unsupported file type. Please upload CSV, XLSX, or XLS.")


def clean_col_name(c):
    return str(c).strip().replace("\n", " ")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [clean_col_name(c) for c in df.columns]
    return df


def auto_col(df: pd.DataFrame, candidates: List[str], contains_all: Optional[List[str]] = None):
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lower_map:
            return lower_map[key]
    if contains_all:
        for c in df.columns:
            lc = str(c).lower()
            if all(term.lower() in lc for term in contains_all):
                return c
    return None


def video_id(v):
    if is_blank(v):
        return ""
    s = str(v).strip()
    m = re.search(r"/video/(\d+)", s)
    if m:
        return m.group(1)
    m = re.search(r"video[:=]?(\d{10,})", s, flags=re.I)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{10,}", s):
        return s
    return ""


def norm_url(v):
    if is_blank(v):
        return ""
    s = str(v).strip().split("?")[0].rstrip("/")
    s = s.replace("http://", "https://")
    s = s.replace("https://m.tiktok.com/", "https://www.tiktok.com/")
    return s


def merge_key(v):
    vid = video_id(v)
    if vid:
        return f"video:{vid}"
    u = norm_url(v)
    if u:
        return f"url:{u}"
    return ""


def to_excel_bytes(sheets):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return buf.getvalue()

# -----------------------------
# Upload
# -----------------------------

st.markdown("### 1) Upload files")
col_u1, col_u2 = st.columns(2)
with col_u1:
    manual_file = st.file_uploader("Manual / Ground Truth file", type=["xlsx", "xls", "csv"], key="manual")
with col_u2:
    ai_file = st.file_uploader("AI Output file", type=["xlsx", "xls", "csv"], key="ai")

if not (manual_file and ai_file):
    st.info("Upload both files to start.")
    st.stop()

try:
    manual_df = normalize_columns(read_file(manual_file))
    ai_df = normalize_columns(read_file(ai_file))
except Exception as e:
    st.error("Could not read one of the files.")
    st.exception(e)
    st.stop()

st.success(f"Files loaded: manual {manual_df.shape[0]} rows x {manual_df.shape[1]} cols, AI {ai_df.shape[0]} rows x {ai_df.shape[1]} cols")

with st.expander("Preview uploaded files"):
    cprev1, cprev2 = st.columns(2)
    with cprev1:
        st.write("Manual preview")
        st.dataframe(manual_df.head(5), use_container_width=True)
    with cprev2:
        st.write("AI preview")
        st.dataframe(ai_df.head(5), use_container_width=True)

# -----------------------------
# Settings
# -----------------------------

st.markdown("### 2) Select columns")
manual_auto = auto_col(
    manual_df,
    ["Creative Type (Manual)", "Creative Type", "Manual Creative Type", "manual creative type"],
    contains_all=["creative", "type"],
)
ai_auto = auto_col(
    ai_df,
    ["Creative Type (AI)", "Creative Type", "AI Creative Type", "ai creative type"],
    contains_all=["creative", "type"],
)

c1, c2, c3 = st.columns(3)
with c1:
    manual_col = st.selectbox(
        "Manual Creative Type column",
        manual_df.columns,
        index=list(manual_df.columns).index(manual_auto) if manual_auto in manual_df.columns else 0,
    )
with c2:
    ai_col = st.selectbox(
        "AI Creative Type column",
        ai_df.columns,
        index=list(ai_df.columns).index(ai_auto) if ai_auto in ai_df.columns else 0,
    )
with c3:
    match_mode = st.radio("Match rows by", ["TikTok Link / Video ID", "Row order"], index=0)

ignore_ai_blank = st.checkbox("Ignore rows where AI label is blank", value=False)
ignore_manual_blank = st.checkbox("Ignore rows where manual label is blank", value=True, disabled=True)

# -----------------------------
# Build comparison
# -----------------------------

unmatched_manual_df = pd.DataFrame()
unmatched_ai_df = pd.DataFrame()
manual_source_rows = len(manual_df)
ai_source_rows = len(ai_df)
coverage = 0.0

if match_mode == "TikTok Link / Video ID":
    link_candidates = ["Link", "link", "TikTok Link", "tiktok_url", "URL", "url", "Video URL", "video_url", "Post URL"]
    m_link_auto = auto_col(manual_df, link_candidates) or manual_df.columns[0]
    a_link_auto = auto_col(ai_df, link_candidates) or ai_df.columns[0]

    c4, c5 = st.columns(2)
    with c4:
        manual_key_col = st.selectbox("Manual Link / Video ID column", manual_df.columns, index=list(manual_df.columns).index(m_link_auto))
    with c5:
        ai_key_col = st.selectbox("AI Link / Video ID column", ai_df.columns, index=list(ai_df.columns).index(a_link_auto))

    m = manual_df.copy()
    a = ai_df.copy()
    m["_match_key"] = m[manual_key_col].apply(merge_key)
    a["_match_key"] = a[ai_key_col].apply(merge_key)

    empty_m = (m["_match_key"] == "").sum()
    empty_a = (a["_match_key"] == "").sum()
    if empty_m or empty_a:
        st.warning(f"Empty match keys: manual={empty_m}, AI={empty_a}. Check that the selected columns contain TikTok links or video IDs.")

    valid_manual_keys = set(m.loc[m["_match_key"] != "", "_match_key"])
    valid_ai_keys = set(a.loc[a["_match_key"] != "", "_match_key"])
    unmatched_manual_df = m[(m["_match_key"] == "") | (~m["_match_key"].isin(valid_ai_keys))].copy()
    unmatched_ai_df = a[(a["_match_key"] == "") | (~a["_match_key"].isin(valid_manual_keys))].copy()
    duplicate_manual = int(m.loc[m["_match_key"] != "", "_match_key"].duplicated(keep=False).sum())
    duplicate_ai = int(a.loc[a["_match_key"] != "", "_match_key"].duplicated(keep=False).sum())
    if duplicate_manual or duplicate_ai:
        st.warning(f"Duplicate TikTok keys detected: manual={duplicate_manual}, AI={duplicate_ai}. Review duplicates before trusting the score.")

    compare_df = m.merge(a, on="_match_key", how="inner", suffixes=("_manual", "_ai"))
    coverage = (len(valid_manual_keys & valid_ai_keys) / len(valid_manual_keys) * 100) if valid_manual_keys else 0.0
    st.caption(f"Matched rows by TikTok key: {len(compare_df)}")
    if len(unmatched_manual_df) or len(unmatched_ai_df):
        st.warning(
            f"Unmatched rows: {len(unmatched_manual_df)} manual row(s) missing from AI output; "
            f"{len(unmatched_ai_df)} AI row(s) missing from manual data."
        )

    manual_eval_col = f"{manual_col}_manual" if f"{manual_col}_manual" in compare_df.columns else manual_col
    ai_eval_col = f"{ai_col}_ai" if f"{ai_col}_ai" in compare_df.columns else ai_col
else:
    n = min(len(manual_df), len(ai_df))
    compare_df = pd.DataFrame({
        "Row": range(2, n + 2),
        "Manual Creative Type": manual_df[manual_col].iloc[:n].values,
        "AI Creative Type": ai_df[ai_col].iloc[:n].values,
    })
    for ctx in ["Link", "Username", "Date", "Content Details", "Narrative"]:
        if ctx in manual_df.columns:
            compare_df[ctx] = manual_df[ctx].iloc[:n].values
    manual_eval_col = "Manual Creative Type"
    ai_eval_col = "AI Creative Type"
    unmatched_manual_df = manual_df.iloc[n:].copy()
    unmatched_ai_df = ai_df.iloc[n:].copy()
    coverage = (n / len(manual_df) * 100) if len(manual_df) else 0.0
    st.caption(f"Matched rows by order: {len(compare_df)}")

if compare_df.empty:
    st.error("No rows matched. If using TikTok Link / Video ID, check that both selected key columns contain the same TikTok video links or IDs. Try Row order only if the two files are in exactly the same order.")
    st.stop()

total_before = len(compare_df)
mask = pd.Series(True, index=compare_df.index)
if ignore_manual_blank:
    mask &= ~compare_df[manual_eval_col].apply(is_blank)
if ignore_ai_blank:
    mask &= ~compare_df[ai_eval_col].apply(is_blank)

compare_df = compare_df[mask].copy()
ignored = total_before - len(compare_df)

if compare_df.empty:
    st.error("After ignoring blank labels, no rows remain to evaluate.")
    st.stop()

compare_df["Manual Labels"] = compare_df[manual_eval_col].apply(lambda x: ", ".join(split_label_list(x)))
compare_df["AI Labels"] = compare_df[ai_eval_col].apply(lambda x: ", ".join(split_label_list(x)))
compare_df["Primary Match"] = compare_df.apply(lambda r: primary_match(r[manual_eval_col], r[ai_eval_col]), axis=1)
compare_df["Contains Match"] = compare_df.apply(lambda r: contains_match(r[manual_eval_col], r[ai_eval_col]), axis=1)
compare_df["Exact Match"] = compare_df.apply(lambda r: exact_match(r[manual_eval_col], r[ai_eval_col]), axis=1)
compare_df["Secondary-only Match"] = compare_df["Contains Match"] & ~compare_df["Primary Match"]
compare_df["Result"] = compare_df["Contains Match"].map({True: "PASS", False: "FAIL"})
compare_df["Reason"] = compare_df.apply(lambda r: contains_reason(r[manual_eval_col], r[ai_eval_col]), axis=1)

# -----------------------------
# Results
# -----------------------------

total = len(compare_df)
primary_correct = int(compare_df["Primary Match"].sum())
primary_wrong = total - primary_correct
primary_acc = primary_correct / total * 100 if total else 0
contains_correct = int(compare_df["Contains Match"].sum())
contains_acc = contains_correct / total * 100 if total else 0
exact = int(compare_df["Exact Match"].sum())
exact_acc = exact / total * 100 if total else 0
secondary_only = int(compare_df["Secondary-only Match"].sum())

st.markdown("### 3) Results")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Rows Evaluated", total)
k2.metric("Coverage", f"{coverage:.1f}%")
k3.metric("PASS", contains_correct)
k4.metric("FAIL", total - contains_correct)
k5.metric("Label Coverage Accuracy", f"{contains_acc:.1f}%")
k6.metric("Exact Match", f"{exact_acc:.1f}%")
st.caption(
    f"Primary-label diagnostic: {primary_correct}/{total} = {primary_acc:.1f}% · "
    f"Rows matched by the second AI label: {secondary_only} · Ignored rows: {ignored}"
)

# Per label
rows = []
manual_labels_all = sorted(set().union(*compare_df[manual_eval_col].apply(split_labels))) if total else []
for label in manual_labels_all:
    sub = compare_df[compare_df[manual_eval_col].apply(lambda x: label in split_labels(x))]
    lt = len(sub)
    lp = int(sub["Primary Match"].sum())
    lc = int(sub["Contains Match"].sum())
    le = int(sub["Exact Match"].sum())
    rows.append({
        "Creative Type": label,
        "Primary Correct": lp,
        "Contains Correct": lc,
        "Exact Correct": le,
        "Total": lt,
        "Primary Accuracy %": round(lp / lt * 100, 1) if lt else 0,
        "Contains Accuracy %": round(lc / lt * 100, 1) if lt else 0,
        "Exact Accuracy %": round(le / lt * 100, 1) if lt else 0,
    })
per_label_df = pd.DataFrame(rows).sort_values("Contains Accuracy %", ascending=True) if rows else pd.DataFrame()

st.subheader("Per-label Accuracy")
st.dataframe(per_label_df, use_container_width=True, hide_index=True)

# Mismatches + optional acceptability review
failed_df = compare_df[~compare_df["Contains Match"]].copy()
matched_df = compare_df[compare_df["Contains Match"]].copy()
secondary_only_df = compare_df[compare_df["Secondary-only Match"]].copy()

st.subheader("Mismatches")
st.dataframe(failed_df, use_container_width=True, hide_index=True)

st.subheader("Matched Rows")
st.dataframe(matched_df, use_container_width=True, hide_index=True)

if not secondary_only_df.empty:
    st.subheader("Secondary-only Matches")
    st.caption("These rows correctly pass your label-coverage rule because the matching label appears second.")
    st.dataframe(secondary_only_df, use_container_width=True, hide_index=True)

if not unmatched_manual_df.empty or not unmatched_ai_df.empty:
    st.subheader("Unmatched Rows")
    if not unmatched_manual_df.empty:
        st.write("Manual rows missing from AI output")
        st.dataframe(unmatched_manual_df, use_container_width=True, hide_index=True)
    if not unmatched_ai_df.empty:
        st.write("AI rows missing from manual data")
        st.dataframe(unmatched_ai_df, use_container_width=True, hide_index=True)

report = {
    "Summary": pd.DataFrame([{
        "Manual Source Rows": manual_source_rows,
        "AI Source Rows": ai_source_rows,
        "Rows Evaluated": total,
        "Coverage %": round(coverage, 2),
        "Ignored Rows": ignored,
        "PASS": contains_correct,
        "FAIL": total - contains_correct,
        "Label Coverage Accuracy %": round(contains_acc, 2),
        "Primary PASS": primary_correct,
        "Primary FAIL": primary_wrong,
        "Primary Accuracy %": round(primary_acc, 2),
        "Contains Match %": round(contains_acc, 2),
        "Exact Match %": round(exact_acc, 2),
        "Secondary-only Matches": secondary_only,
        "Unmatched Manual Rows": len(unmatched_manual_df),
        "Unmatched AI Rows": len(unmatched_ai_df),
        "Match Mode": match_mode,
        "Manual Column": manual_col,
        "AI Column": ai_col,
    }]),
    "Per Label Accuracy": per_label_df,
    "Mismatches": failed_df,
    "Matched Rows": matched_df,
    "Secondary-only Matches": secondary_only_df,
    "Unmatched Manual Rows": unmatched_manual_df,
    "Unmatched AI Rows": unmatched_ai_df,
    "All Compared Rows": compare_df,
}

c6, c7 = st.columns(2)
with c6:
    st.download_button(
        "Download Compared CSV",
        compare_df.to_csv(index=False).encode("utf-8-sig"),
        "creative_type_accuracy_compared.csv",
        "text/csv",
        use_container_width=True,
    )
with c7:
    st.download_button(
        "Download Excel Report",
        to_excel_bytes(report),
        "creative_type_accuracy_report.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
