import streamlit as st
import pandas as pd
import json
import os
import re
import time
import random
import requests
import cv2
import tempfile
import io

st.set_page_config(
    page_title="TikTok Content Tagging",
    page_icon="🎵",
    layout="wide"
)

# ── Global CSS ─────────────────────────────────────────────
st.markdown("""
<style>
/* Base */
[data-testid="stAppViewContainer"] { background: #f8fafc; }
[data-testid="stSidebar"] { display: none !important; }

/* Hide default top padding */
.block-container { padding-top: 0 !important; padding-bottom: 2rem; max-width: 1100px; }

/* Top navbar brand bar */
.topnav {
    background: #1e1b4b;
    padding: 0 32px;
    display: flex;
    align-items: center;
    height: 52px;
    margin: -1rem -1rem 0 -1rem;
}
.topnav-brand { color: white; font-size: 15px; font-weight: 700; letter-spacing: .01em; }

/* Page header band */
.page-header {
    background: linear-gradient(135deg, #1e1b4b 0%, #4f46e5 100%);
    border-radius: 12px;
    padding: 28px 32px;
    margin-bottom: 24px;
    color: white;
}
.page-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 700; color: white; }
.page-header p  { margin: 0; font-size: 13px; opacity: .75; color: #c7d2fe; }

/* Metric cards */
.metric-row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
.metric-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 18px 22px;
    min-width: 130px;
    flex: 1;
}
.metric-card .val { font-size: 28px; font-weight: 800; color: #1e1b4b; margin-bottom: 2px; }
.metric-card .val.green { color: #059669; }
.metric-card .val.amber { color: #d97706; }
.metric-card .val.indigo { color: #4f46e5; }
.metric-card .lbl { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }

/* Section card */
.section-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 24px;
    margin-bottom: 20px;
}
.section-card h3 { margin: 0 0 16px; font-size: 15px; font-weight: 700; color: #1e1b4b; }

/* Compact workflow UI */
.workflow-strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
    margin-bottom: 16px;
}
.workflow-step {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 12px;
    color: #475569;
}
.workflow-step strong {
    display: block;
    color: #1e1b4b;
    font-size: 13px;
    margin-bottom: 2px;
}
.checklist {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 16px;
}
.checklist ul {
    margin: 0;
    padding-left: 18px;
    color: #475569;
    font-size: 13px;
    line-height: 1.7;
}
.file-row {
    display: grid;
    grid-template-columns: 2.2fr 2.3fr 1.1fr 1fr 1.2fr 0.4fr;
    gap: 12px;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid #f1f5f9;
}
.file-row.header {
    padding-top: 0;
    color: #64748b;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .05em;
}
.file-name {
    color: #334155;
    font-size: 13px;
    font-weight: 700;
    word-break: break-word;
}
.small-muted {
    color: #64748b;
    font-size: 12px;
}
.status-pill {
    display: inline-block;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
.status-ok { background: #ecfdf5; color: #047857; }
.status-warn { background: #fffbeb; color: #b45309; }
.status-bad { background: #fef2f2; color: #dc2626; }
.run-panel {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px;
}
.run-panel .big {
    color: #1e1b4b;
    font-size: 22px;
    font-weight: 800;
}
.run-panel .label {
    color: #64748b;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .05em;
}

/* Tier badges */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
}
.badge-t0 { background: #f1f5f9; color: #475569; }
.badge-t1 { background: #ecfdf5; color: #059669; }
.badge-t2 { background: #fffbeb; color: #b45309; }
.badge-t3 { background: #eef2ff; color: #4338ca; }
.badge-fail { background: #fef2f2; color: #dc2626; }

/* Info banner */
.info-banner {
    background: #eef2ff;
    border-left: 4px solid #4f46e5;
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 13px;
    color: #374151;
    margin-bottom: 16px;
}
.warn-banner {
    background: #fffbeb;
    border-left: 4px solid #f59e0b;
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 13px;
    color: #374151;
    margin-bottom: 16px;
}

/* Review post card */
.post-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 20px;
}
.post-card .label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing:.05em; margin-bottom: 2px; }
.post-card .value { font-size: 14px; color: #1e293b; margin-bottom: 12px; }
.post-card .stat  { font-size: 13px; color: #475569; }

/* Divider */
.divider { border: none; border-top: 1px solid #e2e8f0; margin: 20px 0; }

/* Sidebar nav label */
.nav-label {
    font-size: 11px;
    color: #818cf8 !important;
    text-transform: uppercase;
    letter-spacing: .08em;
    font-weight: 700;
    margin-bottom: 4px;
    display: block;
}

/* Global: force all Streamlit widget labels to be dark + readable */
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label,
div[class*="stSelectbox"] label,
div[class*="stMultiSelect"] label,
div[class*="stTextArea"] label,
div[class*="stSlider"] label,
div[class*="stRadio"] label,
div[class*="stCheckbox"] label {
    color: #1e293b !important;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────
ALLOWED_CREATIVE_TYPES = [
    'Slice of Life', 'Lyrics', 'Lyrics Translation', 'Relationship',
    'POV', 'Dance', 'Cover', 'Lip Sync', 'Carousel', 'Media/Infotainment',
    'Quotes', 'Travel', 'Reflection', 'Comedy', 'Beauty',
    'Movie/Tv/Drama Edits', 'Celebrity Edits', 'Fitness', 'Remix',
    'Fashion', 'Gaming'
]
ALLOWED_SET = set(ALLOWED_CREATIVE_TYPES)

# Default Gemini model. Keep this aligned with your current working setup.
# If the video fallback fails for your account/model, change this to another video-capable Gemini model available to you.
GEMINI_MODEL = 'gemini-3.1-flash-lite'

NARRATIVE_OPTIONS = [
    'NA', 'Relationship', 'Friendship', 'Family', 'Lifestyle',
    'Dance', 'Simple Dance', 'Dance Tutorial', 'Lip Sync',
    'Fashion', 'Beauty', 'Product Showcase', 'Tutorial',
    'Travel', 'Beach Vacation', 'Food', 'Fitness', 'Comedy',
    'Reflection', 'Healing', 'Quotes', 'Motivation',
    'Celebrity Edit', 'Drama Edit', 'Gaming', 'Celebration',
    'Study', 'Work', 'Pets', 'CNY', 'Ramadan',
    'Custom', 'Other'
]

VAGUE_PATTERNS = [r'^[\W\s\d]+$', r'^.{0,15}$']

# ── Session state ──────────────────────────────────────────
defaults = {
    'master_df': pd.DataFrame(),
    'review_idx': 0,
    'gemini_key': '',
    'apify_token': '',
    'tagging_log': [],
    'staged_files': [],   # list of {name, records, track, market, has_video, tagged}
    'raw_records': {},    # dict of post_id -> raw record dict (for review page lookups)
    'uploader_version': 0,  # increments to reset file_uploader after removing files
    'has_tagged_results': False,
    'original_df': pd.DataFrame(),
    'original_url_col': '',
    'original_market_map': {},
    'removed_post_ids': set(),
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Persistent raw JSON index helpers.
# The review page should always use the uploaded TikTok JSON as the source of truth
# for URL, cover, creator and engagement metrics, not the AI output row alone.
def _norm_post_id(val):
    try:
        if val is None:
            return ''
        s = str(val).strip()
        if s.endswith('.0') and s[:-2].isdigit():
            s = s[:-2]
        return s
    except Exception:
        return ''

def rebuild_raw_records_index():
    idx = {}
    for sf in st.session_state.get('staged_files', []):
        for rec in sf.get('records', []):
            if isinstance(rec, dict):
                rid = _norm_post_id(rec.get('id', ''))
                if rid:
                    idx[rid] = rec
    # Keep anything already cached too.
    for rid, rec in list(st.session_state.get('raw_records', {}).items()):
        nrid = _norm_post_id(rid)
        if nrid and isinstance(rec, dict):
            idx.setdefault(nrid, rec)
    st.session_state.raw_records = idx
    return idx

def _raw_get_nested(rec, dotted, default=''):
    if not isinstance(rec, dict):
        return default
    cur = rec
    for part in dotted.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur

def _first_nonempty(*vals):
    for v in vals:
        try:
            if v is None:
                continue
            if isinstance(v, float) and _math_global.isnan(v):
                continue
        except Exception:
            pass
        if str(v).strip() not in ['', 'nan', 'None']:
            return v
    return ''


def _norm_url_for_merge_global(v):
    """Normalize TikTok URLs for matching without changing display values."""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return ""
    s = s.split("?")[0].strip().rstrip("/")
    s = s.replace("https://m.tiktok.com/", "https://www.tiktok.com/")
    s = s.replace("http://m.tiktok.com/", "https://www.tiktok.com/")
    s = s.replace("http://www.tiktok.com/", "https://www.tiktok.com/")
    return s

def _extract_tiktok_video_id_global(v):
    """Extract stable TikTok video ID from a URL-like value."""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return ""
    m = re.search(r"/video/(\d+)", s)
    if m:
        return m.group(1)
    for pat in [r"[?&](?:item_id|share_item_id|aweme_id|modal_id)=(\d+)", r"(?:item_id|share_item_id|aweme_id|modal_id)[=:](\d+)"]:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    if re.fullmatch(r"\d{10,}", s):
        return s
    return ""

def _merge_key_global(url_val, id_val=""):
    vid = _extract_tiktok_video_id_global(url_val) or _extract_tiktok_video_id_global(id_val)
    if vid:
        return f"video:{vid}"
    norm = _norm_url_for_merge_global(url_val)
    return f"url:{norm}" if norm else ""

def _read_report_global(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith('.csv'):
        return pd.read_csv(uploaded_file), 'csv'
    return pd.read_excel(uploaded_file), 'xlsx'

def _detect_url_col_global(df):
    for candidate in ['Link', 'link', 'TikTok Link', 'Tiktok Link', 'URL', 'url', 'Video URL', 'video_url', 'tiktok_url', 'submittedVideoUrl', 'webVideoUrl']:
        if candidate in df.columns:
            return candidate
    return None

def _detect_market_col_global(df):
    for candidate in ['Country', 'country', 'Market', 'market', 'Region', 'region']:
        if candidate in df.columns:
            return candidate
    return None

def _build_original_market_map(df, url_col, market_col):
    out = {}
    if df is None or df.empty or not url_col or not market_col:
        return out
    for _, r in df.iterrows():
        key = _merge_key_global(r.get(url_col, ''))
        market = str(r.get(market_col, '')).strip()
        if key and market and market.lower() not in ['nan', 'none', 'null']:
            out[key] = market
    return out


def _detect_track_col_global(df):
    """Detect the track/sound column in the original report."""
    for candidate in ['Artist - Sound', 'Artist-Sound', 'Track', 'track', 'Sound', 'sound', 'Song', 'song', 'Music', 'music']:
        if candidate in df.columns:
            return candidate
    return None

def _clean_link_list(vals):
    links = []
    seen = set()
    for v in vals:
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except Exception:
            pass
        url = str(v).strip()
        if not url or url.lower() in ['nan', 'none', 'null']:
            continue
        if 'tiktok.com' not in url.lower():
            continue
        key = _merge_key_global(url) or url
        if key in seen:
            continue
        seen.add(key)
        links.append(url)
    return links

def _build_excel_track_batches(df, country_col, track_col, link_col):
    """Group original report into one Apify batch per Country + Artist - Sound."""
    batches = []
    if df is None or df.empty or not track_col or not link_col:
        return batches
    group_cols = [track_col]
    if country_col and country_col in df.columns:
        group_cols = [country_col, track_col]
    for group_key, g in df.groupby(group_cols, dropna=False):
        if isinstance(group_key, tuple):
            country = str(group_key[0]).strip()
            track = str(group_key[1]).strip()
        else:
            country = ''
            track = str(group_key).strip()
        if not track or track.lower() in ['nan', 'none', 'null']:
            track = 'Unknown Track'
        if not country or country.lower() in ['nan', 'none', 'null']:
            country = 'UNKNOWN'
        links = _clean_link_list(g[link_col].tolist())
        if links:
            batches.append({
                'country': country,
                'track': track,
                'links': links,
                'rows': len(g),
                'link_count': len(links),
            })
    return batches

def run_apify_tiktok_scraper_api(links, apify_token):
    """Run existing Apify TikTok Scraper Actor and return dataset items.

    This replaces manual JSON download/upload. The output items are the same type
    of records your current run_pipeline() already consumes.
    """
    try:
        from apify_client import ApifyClient
    except Exception as e:
        raise RuntimeError("Missing dependency: install with `pip install apify-client`.") from e

    if not apify_token:
        raise RuntimeError('Missing Apify token.')
    if not links:
        return []

    client = ApifyClient(apify_token)
    run_input = {
        'postURLs': links,
        'resultsPerPage': len(links),
        'shouldDownloadVideos': True,
        'shouldDownloadCovers': True,
        'shouldDownloadSlideshowImages': True,
        'shouldDownloadAvatars': False,
        'shouldDownloadMusicCovers': False,
        'downloadSubtitlesOptions': 'NEVER_DOWNLOAD_SUBTITLES',
        'commentsPerPost': 0,
        'topLevelCommentsPerPost': 0,
        'maxRepliesPerComment': 0,
        'excludePinnedPosts': False,
        'maxFollowersPerProfile': 0,
        'maxFollowingPerProfile': 0,
        'scrapeRelatedSearchWords': False,
        'scrapeRelatedVideos': False,
        'proxyCountryCode': 'None',
    }
    run = client.actor('clockworks/tiktok-scraper').call(run_input=run_input)

    # Apify Python client may return either a dict-like object or a Run object
    if isinstance(run, dict):
        dataset_id = run.get('defaultDatasetId') or run.get('default_dataset_id')
    else:
        dataset_id = (
            getattr(run, 'default_dataset_id', None)
            or getattr(run, 'defaultDatasetId', None)
        )

    if not dataset_id:
        raise RuntimeError('Apify run finished but no default dataset was returned.')

    return list(client.dataset(dataset_id).iterate_items())

def _apply_original_market_to_results(result_df):
    """Use original CSV/XLSX Country/Market as the source of truth for market."""
    market_map = st.session_state.get('original_market_map', {})
    if result_df is None or result_df.empty or not market_map:
        return result_df
    out = result_df.copy()
    for idx, r in out.iterrows():
        key = _merge_key_global(r.get('tiktok_url', ''), r.get('id', ''))
        if key in market_map:
            out.at[idx, 'market'] = market_map[key]
    return out

def _repair_review_metadata_in_master_df():
    """Fill URL/cover/metrics/creator/caption for every master_df row from uploaded JSON.
    This prevents only the first flagged row from working while later flagged rows show 0/no URL.
    """
    if st.session_state.get('master_df', pd.DataFrame()).empty:
        return
    raw_idx = rebuild_raw_records_index()
    df = st.session_state.master_df
    for pos, r in df.iterrows():
        rid = _norm_post_id(r.get('id', ''))
        rec = raw_idx.get(rid, {})
        if not rec:
            continue
        # Always repair if current value is empty/zero.
        df.at[pos, 'tiktok_url'] = _first_nonempty(r.get('tiktok_url'), rec.get('webVideoUrl'), rec.get('submittedVideoUrl'))
        df.at[pos, 'cover_url'] = _first_nonempty(r.get('cover_url'), _raw_get_nested(rec, 'videoMeta.originalCoverUrl'), _raw_get_nested(rec, 'videoMeta.coverUrl'))
        df.at[pos, 'video_url'] = _first_nonempty(r.get('video_url'), (rec.get('mediaUrls') or [''])[0] if isinstance(rec.get('mediaUrls'), list) and rec.get('mediaUrls') else '', _raw_get_nested(rec, 'videoMeta.downloadAddr'))
        df.at[pos, 'creator'] = _first_nonempty(r.get('creator'), _raw_get_nested(rec, 'authorMeta.name'), _raw_get_nested(rec, 'authorMeta.nickName'), '—')
        # TikTok username is authorMeta.name; display name is authorMeta.nickName.
        df.at[pos, 'creator_handle'] = _first_nonempty(r.get('creator_handle'), _raw_get_nested(rec, 'authorMeta.name'))
        df.at[pos, 'creator_display'] = _first_nonempty(r.get('creator_display'), _raw_get_nested(rec, 'authorMeta.nickName'))
        df.at[pos, 'caption'] = _first_nonempty(r.get('caption'), rec.get('text'))
        # For metrics, if existing is 0/blank, use raw JSON.
        for col, raw_key in [('plays','playCount'), ('likes','diggCount'), ('shares','shareCount'), ('saves','collectCount'), ('comments','commentCount')]:
            try:
                cur = r.get(col, 0)
                cur_i = int(float(cur)) if str(cur).strip() not in ['', 'nan', 'None'] else 0
            except Exception:
                cur_i = 0
            if cur_i == 0:
                df.at[pos, col] = _si(rec.get(raw_key, 0))
        try:
            df.at[pos, '_raw_row_json'] = json.dumps(rec, default=str)
        except Exception:
            pass
    st.session_state.master_df = df

# ── Helper functions ───────────────────────────────────────
import math as _math_global

import math as _math_global

def _si(val, default=0):
    """Safe int conversion handling NaN/None/float strings from pandas round-trips."""
    try:
        if val is None: return default
        if isinstance(val, float) and _math_global.isnan(val): return default
        # pandas casts int cols to float when NaN exists in same col after concat
        return int(float(val))
    except (ValueError, TypeError):
        return default

def is_too_vague(row):
    caption  = str(row.get('text', '')).strip()
    hashtags = row.get('hashtags', [])
    n_tags   = len(hashtags) if isinstance(hashtags, list) else 0
    if n_tags > 1:
        return False
    for pat in VAGUE_PATTERNS:
        if re.match(pat, caption):
            return True
    return False

def get_cover_url(row):
    return row.get('videoMeta.originalCoverUrl', '') or row.get('videoMeta.coverUrl', '')

def get_video_url(row):
    media = row.get('mediaUrls', [])
    if isinstance(media, list) and media:
        return media[0]
    return row.get('videoMeta.downloadAddr', '')

def download_image_bytes(url, apify_token):
    headers = {}
    if 'api.apify.com' in url:
        headers = {'Authorization': f'Bearer {apify_token}'}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.content

def download_video(video_url, output_path, apify_token):
    headers = {'Authorization': f'Bearer {apify_token}'}
    r = requests.get(video_url, headers=headers, timeout=90)
    r.raise_for_status()
    with open(output_path, 'wb') as f:
        f.write(r.content)
    return output_path

# Frame sampling presets
# 3-frame mode is fast and works well for static / text / lifestyle content.
# 9-frame mode gives better temporal coverage for motion-heavy content such as Dance and Lip Sync,
# but is slower, so v27 uses it only as an adaptive refinement step.
FRAME_POINTS_3 = [0.10, 0.50, 0.90]
FRAME_POINTS_9 = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
MOTION_HEAVY_TYPES = {'Dance', 'Lip Sync', 'Fitness', 'Cover'}
MOTION_CUE_WORDS = [
    'dance', 'dancing', 'choreo', 'choreography', 'challenge', '댄스', '춤',
    'cover', 'sing', 'singing', 'lip sync', 'lipsync', 'fitness', 'workout', 'gym'
]

def extract_frames(video_path, output_dir, points=None):
    if points is None:
        points = FRAME_POINTS_3
    os.makedirs(output_dir, exist_ok=True)
    cap   = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_paths = []
    if total <= 0:
        cap.release()
        return frame_paths
    for p in points:
        # Clamp position to avoid seeking past the last frame.
        frame_pos = max(0, min(total - 1, int(total * p)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ok, frame = cap.read()
        if ok:
            path = os.path.join(output_dir, f'frame_{int(p*100):02d}.jpg')
            cv2.imwrite(path, frame)
            frame_paths.append(path)
    cap.release()
    return frame_paths

def _result_has_motion_heavy_label(result):
    labels = result.get('creative_type', []) if isinstance(result, dict) else []
    if not isinstance(labels, list):
        return False
    return any(str(x).strip() in MOTION_HEAVY_TYPES for x in labels)

def _row_has_motion_cues(row):
    try:
        caption = str(row.get('text', '') or '').lower()
    except Exception:
        caption = ''
    tags_raw = row.get('hashtags', [])
    tags = []
    if isinstance(tags_raw, list):
        for h in tags_raw:
            tags.append((h.get('name', '') if isinstance(h, dict) else str(h)).lower())
    text = caption + ' ' + ' '.join(tags)
    return any(w in text for w in MOTION_CUE_WORDS)

DANCE_VISUAL_CUES = [
    'dance', 'dancing', 'dancer', 'choreo', 'choreography', 'dance challenge',
    'synchronized', 'synchronised', 'sync movement', 'coordinated movement',
    'full-body', 'full body', 'body movement', 'hand gesture', 'dance move',
    'formation', 'performance', 'group dance', 'dance practice'
]

NON_DANCE_LIPSYNC_CUES = [
    'close-up', 'close up', 'mouth', 'mouthing', 'singing to camera',
    'face expression', 'facial expression', 'little/no choreography', 'no choreography'
]

def _result_text_blob(result):
    if not isinstance(result, dict):
        return ''
    parts = []
    for k in ['narrative', 'content_details', 'reasoning']:
        v = result.get(k, '')
        if isinstance(v, list):
            v = ' '.join(map(str, v))
        parts.append(str(v))
    labels = result.get('creative_type', [])
    if isinstance(labels, list):
        parts.append(' '.join(map(str, labels)))
    return ' '.join(parts).lower()

def _result_has_dance_visual_cues(result):
    blob = _result_text_blob(result)
    return any(cue in blob for cue in DANCE_VISUAL_CUES)

def _result_is_clear_lipsync_only(result):
    blob = _result_text_blob(result)
    has_lipsync = ('lip sync' in blob or 'lipsync' in blob or 'mouthing' in blob or 'mouth' in blob)
    has_dance = any(cue in blob for cue in DANCE_VISUAL_CUES)
    has_non_dance = any(cue in blob for cue in NON_DANCE_LIPSYNC_CUES)
    return has_lipsync and has_non_dance and not has_dance

def apply_dance_guardrails(result, row=None):
    """Post-process obvious Dance/Lip Sync confusion without another Gemini call.

    This is conservative: it only adds/replaces Dance when the model's own
    narrative/details/reasoning or the caption/hashtags contain dance/choreography cues.
    It is designed to improve KR-style choreography posts while avoiding PH-style
    genuine lip-sync posts.
    """
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    label_set = set(labels)
    row_dance_cue = _row_has_motion_cues(row) if row is not None else False
    result_dance_cue = _result_has_dance_visual_cues(result)
    clear_lipsync_only = _result_is_clear_lipsync_only(result)

    should_force_dance = (row_dance_cue or result_dance_cue) and not clear_lipsync_only

    if should_force_dance and 'Dance' not in label_set:
        # If the model predicted Lip Sync/Relationship/Celebrity Edits but its own
        # description mentions choreography, include Dance. Keep one useful secondary
        # label only when possible.
        new_labels = ['Dance']
        for keep in ['Celebrity Edits', 'Lip Sync', 'Relationship', 'Carousel']:
            if keep in labels and keep not in new_labels:
                new_labels.append(keep)
                break
        result['creative_type'] = new_labels[:2]
        old_reason = str(result.get('reasoning', '') or '')
        result['reasoning'] = (old_reason + ' | Guardrail: dance/choreography cues detected, so Dance was prioritized over Lip Sync/Relationship.').strip(' |')
        try:
            result['confidence'] = max(float(result.get('confidence', 0) or 0), 0.78)
        except Exception:
            result['confidence'] = 0.78
    elif 'Dance' in label_set and 'Lip Sync' in label_set and result_dance_cue:
        # Keep Dance first when both labels are present.
        rest = [x for x in labels if x != 'Dance']
        result['creative_type'] = ['Dance'] + rest[:1]
    return result

def build_prompt(row):
    caption    = row.get('text', '')
    _raw_tags  = row.get('hashtags')
    _raw_tags  = _raw_tags if isinstance(_raw_tags, list) else []
    hashtags   = [h.get('name','') if isinstance(h,dict) else str(h) for h in _raw_tags]
    htag_str   = ' '.join(f'#{h}' for h in hashtags) if hashtags else '(none)'
    author     = row.get('authorMeta.nickName','') or row.get('authorMeta.name','')
    music      = row.get('musicMeta.musicName','')
    music_auth = row.get('musicMeta.musicAuthor','')
    duration   = row.get('videoMeta.duration','')
    location   = row.get('locationCreated','')
    play       = row.get('playCount', 0)
    likes      = row.get('diggCount', 0)
    shares     = row.get('shareCount', 0)
    saves      = row.get('collectCount', 0)
    is_slide   = row.get('isSlideshow', False)
    allowed_str = '\n'.join(f'  - {t}' for t in ALLOWED_CREATIVE_TYPES)
    return f"""You are a senior TikTok UGC content analyst for Universal Music Group.
Your task is to classify TikTok posts for music marketing analysis across Malaysia, Philippines, Singapore, Korea, Thailand, Vietnam and wider SEA markets.

Return ONLY valid JSON. No markdown. No explanation outside JSON.

=== POST METADATA ===
Caption: {caption}
Hashtags: {htag_str}
Creator: {author}
Music: {music} by {music_auth}
Duration: {duration}s | Market: {location} | Is Slideshow: {is_slide}
Plays: {play:,} | Likes: {likes:,} | Shares: {shares:,} | Saves: {saves:,}

=== ALLOWED CREATIVE TYPE LABELS ===
Use exact spelling only:
{allowed_str}

=== VERY IMPORTANT CLASSIFICATION PRINCIPLE ===
Do NOT simply describe the scene. Classify the PRIMARY CONTENT FORMAT.
Ask: "What type of TikTok content is this?" rather than "What objects appear in the frame?"

Examples:
- A person dancing in a mall is Dance, not Slice of Life.
- Full-body choreography or synchronized movement is Dance, even if the caption is romantic or the creator mouths lyrics.
- A person mouthing lyrics in a bedroom is Lip Sync only when mouth/face performance is the main action and there is little/no choreography.
- A drama/anime/movie scene edit is Movie/Tv/Drama Edits, not Slice of Life.
- A K-pop idol photo/video montage is Celebrity Edits, not Slice of Life.
- A makeup routine is Beauty, not Fashion, even if the outfit is nice.

=== OUTPUT RULES ===
- Creative Type: return 1 or 2 labels only.
- If isSlideshow=true, ALWAYS include Carousel as one label.
- If Carousel is included, use the second label for the actual content type when possible, e.g. ["Carousel", "Beauty"].
- Do not use Slice of Life as a fallback when a more specific label applies.
- If uncertain, choose the strongest visible signal and lower confidence.
- Remix is audio-only. Never use Remix for visual transitions, outfit changes, or editing style.

=== NARRATIVE RULES ===
Narrative is a short flexible theme phrase, NOT a fixed category.
Write 1 to 5 words.
Use NA only if no meaningful theme is visible.

Good narrative examples:
- Simple dance
- Girl lip syncing
- Dance tutorial
- Idol edit
- Drama edit
- Beach vacation
- Makeup routine
- Product showcase
- Rainy walk
- Late night conversation
- Missing someone
- Campus life
- Outfit showcase
- Game edit
- Healing
- Relationship quote
- Fitness flex
- Cooking tutorial

Do not force narrative into one label like Relationship or Lifestyle if a more specific short phrase fits.

=== DECISION TREE — APPLY IN THIS ORDER ===
1. Is this a slideshow/photo carousel? If yes, include Carousel.
2. Is the main content from a movie, drama, TV show, anime, web series or fictional scene? Use Movie/Tv/Drama Edits.
3. Is the main content a fan edit/montage of a real celebrity, idol, singer, actor, athlete, influencer or public figure? Use Celebrity Edits.
4. Is visible choreography, repeated body movement, dance challenge, or synchronized/group movement the main focus? Use Dance.
5. Is the creator mainly mouthing/singing lyrics with little/no choreography? Use Lip Sync. If choreography is visible, Dance wins over Lip Sync.
6. Is the creator performing a cover, singing/playing an instrument as their own performance? Use Cover.
7. Is the main focus makeup, skincare, hair, nails or cosmetics? Use Beauty.
8. Is the main focus clothing, outfit styling, OOTD, fit check or fashion haul? Use Fashion.
9. Is the main message romantic love, longing, heartbreak, partner dynamics or affection for someone special? Use Relationship.
10. Is it a first-person acted scenario or "POV" setup? Use POV, optionally with Comedy or Relationship.
11. Is the main purpose humour, joke, meme, prank or comedic skit? Use Comedy.
12. Are lyrics visibly displayed as the main content? Use Lyrics. If translated/bilingual lyrics are shown, use Lyrics Translation.
13. Is the post educational/informative/tutorial/review/news/tips/DIY/product recommendation? Use Media/Infotainment.
14. Is the main visual focus destination/scenery/vacation/travel vlog? Use Travel.
15. Is the main focus gameplay/game UI/game characters/game edit? Use Gaming.
16. Is the main focus workout, gym, sport training, physique, exercise or flexing? Use Fitness.
17. Is it mainly a quote card/text quote? Use Quotes.
18. Is it personal introspection, self-growth, emotional reflection or life lesson? Use Reflection.
19. Is it ordinary daily life without a stronger specific label? Use Slice of Life.

=== CREATIVE TYPE HANDBOOK ===

1) Dance
Definition: Dance performance or choreography is the dominant content format.
Use for: dance challenge, choreography, hand gesture dance, group dance, idol dance challenge, dance tutorial, dance practice, dance trend.
Do NOT confuse with:
- Lip Sync: mouth movement/singing with no dominant choreography.
- Slice of Life: everyday location does not matter if the main action is dancing.
- Celebrity Edits: if the video is mainly an idol/celebrity montage, use Celebrity Edits; if it is a creator or group performing choreography, use Dance.
Rule: If visible body movement/choreography is a major focus, classify as Dance even if captions are vague.
Priority rule: Dance OVERRIDES Lip Sync, Relationship and Slice of Life when the visual format is choreography/performance.
Korea/K-pop rule: If idol/creator content shows a dance challenge, practice, choreography, performance stage, hand-gesture dance or synchronized group movement, choose Dance. Use Celebrity Edits only when it is mainly a fan montage/edit rather than the dance itself.
Motion note: because only sampled frames may be available, look for progression across frames. If multiple frames show full-body poses, synchronized movement, dance formation or choreography, choose Dance even if the caption is romantic or the creator appears to be mouthing lyrics.

2) Lip Sync
Definition: Creator mouths lyrics/dialogue or sings along to the audio.
Use for: singing along, mouthing lyrics, emotional lip-sync performance, acting to lyrics/dialogue, close-up singing to camera.
Do NOT use when: full-body choreography is dominant -> Dance.
Rule: If the main performance is face/mouth expression rather than choreography, choose Lip Sync. If full-body movement/choreography is visible across frames, choose Dance instead of Lip Sync.
Do NOT classify as Lip Sync just because the creator's mouth is open or music has lyrics. Lip Sync requires mouth/face performance to be the dominant format.

3) Cover
Definition: Creator performs their own musical cover.
Use for: singing cover, instrument cover, acoustic performance, piano/guitar/drum cover, vocal performance not just mouthing existing audio.
Do NOT confuse with Lip Sync: Lip Sync = mouthing existing audio; Cover = creator performs the song.

4) Movie/Tv/Drama Edits
Definition: Edits or clips centered on fictional media.
Use for: movie scenes, TV scenes, drama clips, K-drama edits, anime edits, fictional character edits, series montage, cinematic scene compilations.
Do NOT confuse with:
- Celebrity Edits: real celebrity/idol/public figure fan edit.
- Slice of Life: fictional clips are never Slice of Life.
Rule: If the content comes from a movie/show/drama/anime/fictional scene, choose Movie/Tv/Drama Edits.

5) Celebrity Edits
Definition: Fan edit or montage of a real public figure.
Use for: K-pop idol edits, celebrity photos/videos, actor/artist/athlete montage, fancam edit, concert/performance edit, public figure compilation, F1 driver edit.
Do NOT confuse with:
- Movie/Tv/Drama Edits: fictional character/scene from drama/movie/anime.
- Dance: if the main focus is a creator dancing, choose Dance; if it is a fan edit of an idol/celebrity, choose Celebrity Edits.
Rule: If the subject is a real famous/public person and the format is edit/montage/fan content, choose Celebrity Edits.

6) Beauty
Definition: Makeup, skincare, hair, nails or cosmetics are the main focus.
Use for: makeup routine, makeup tutorial, GRWM makeup, skincare products, skincare routine, eye makeup, lip makeup, hair tutorial, hairstyle transformation, nail art, beauty product carousel, cosmetic review.
Do NOT use Beauty just because someone looks attractive.
Do NOT confuse with Fashion: Fashion requires clothing/outfit to be the focus.
Rule: If cosmetics/hair/skin/nails are the main action or product, choose Beauty.

7) Fashion
Definition: Clothing/outfit/styling is the main focus.
Use for: OOTD, fit check, outfit showcase, outfit transition, clothing haul, lookbook, styling tips, accessories when styling is primary, mirror outfit check.
Do NOT confuse with Beauty: makeup/skincare/hair/nails -> Beauty.
Rule: If the video showcases what someone is wearing, choose Fashion.

8) Relationship
Definition: Romantic love, affection, longing, heartbreak, devotion or partner dynamics are central.
Use for: couple content, boyfriend/girlfriend, husband/wife, missing someone, romantic quotes, affection for someone special, late-night conversation with someone special, relationship advice, emotional openness between partners, heartbreak.
Do NOT use for ordinary daily memories unless romance is the main message.
Rule: If the emotional meaning is about love/romance/partner, choose Relationship.

9) Slice of Life
Definition: Everyday real-life moments without a stronger specific format.
Use for: daily routine, walking, studying, commuting, coffee, rain scenes, home life, casual memories, school/campus life, lifestyle montage, aesthetic ordinary life.
Do NOT use as a default.
Do NOT use when Dance, Lip Sync, Beauty, Fashion, Relationship, Travel, POV, Celebrity Edits or Movie/Tv/Drama Edits clearly apply.
Rule: Slice of Life is only for ordinary life content with no more specific label.

10) POV
Definition: First-person scenario, roleplay, acted hypothetical, or explicit "POV:" framing.
Use for: POV text, acted situation, scenario from viewer perspective, relationship POV, funny POV.
Can combine with: Comedy, Relationship.
Do NOT confuse with Slice of Life: if it is acted/framed as a scenario, choose POV.
Rule: If the caption/on-screen text sets up a scenario such as "POV: ...", use POV.

11) Comedy
Definition: Main purpose is humour.
Use for: joke, meme, prank, funny skit, humorous acting, exaggerated reaction, comedic situation.
Can combine with: POV.
Do NOT use if the content is only light-hearted but not primarily funny. Do NOT classify a skit as Lip Sync just because music is playing; if the creator is acting/talking for humour, choose Comedy.

12) Lyrics
Definition: Original song lyrics are visibly displayed or are the central content.
Use for: lyric video, lyric edit, karaoke-style text, emotional lyric text, post built around written lyrics.
Do NOT use merely because the audio has lyrics.
Rule: Lyrics must be visible or captionally central.

13) Lyrics Translation
Definition: Lyrics are translated into another language.
Use for: bilingual lyrics, subtitle translation, translated lyric explanation.
Rule: If both original lyrics and translated text are shown, choose Lyrics Translation.

14) Quotes
Definition: Standalone quote/saying is the main content.
Use for: motivational quote, emotional quote, aesthetic quote card, relationship quote, short saying, text quote slideshow.
Do NOT confuse with Reflection:
- Quotes = presenting a quote/line.
- Reflection = personal introspection or life lesson.

15) Reflection
Definition: Personal introspection, self-growth, emotional reflection or life lesson.
Use for: self-acceptance, healing, mother's sacrifice, gratitude, sadness, personal realization, life lesson, emotional thoughts.
Do NOT confuse with Quotes if the post only displays a quote without personal introspection.

16) Media/Infotainment
Definition: Informational, educational, explanatory, tutorial, review, news, DIY, tip-based or recommendation content.
Use for: news article, facts, explainer, how-to, DIY, tutorial, recipe/cake idea, product recommendation, digicam review, horoscope/forecast, Valentine's bracelet idea.
Do NOT confuse with Slice of Life: if it teaches/informs/recommends something, use Media/Infotainment.

17) Travel
Definition: Travel/destination/scenery is the main focus.
Use for: beach, mountains, city view, vacation, tourism, trip vlog, landscape, destination montage, travel memory.
Rule: If the visual focus is place/scenery/trip, choose Travel even if caption is emotional.

18) Gaming
Definition: Game-related content is central.
Use for: gameplay, game screenshots, game UI, game character edit, game fan video, Minecraft, Genshin, Racing Master, Omori or similar gaming content.
Do NOT confuse game character edits with Movie/Tv/Drama Edits unless clearly from film/TV/anime rather than a game.

19) Fitness
Definition: Exercise, gym, sport training or physique is central.
Use for: workout, gym, bodybuilding, flexing muscles, showing physique, fitness transformation, sport training, exercise routine.

20) Remix
Definition: Audio has been transformed.
Use ONLY for: sped up, slowed, mashup, DJ edit, remix audio, alternate audio version.
Do NOT use for: visual transitions, edited clips, fashion transformations, fan edits.

21) Carousel
Definition: TikTok slideshow/photo carousel format.
Use when: isSlideshow=true or the post is clearly a sequence of still photos.
Always include Carousel if isSlideshow=true.
Best practice: use Carousel + content label, e.g. Carousel + Beauty, Carousel + Quotes, Carousel + Celebrity Edits.

=== COMMON CONFUSIONS TO AVOID ===
- Dance vs Lip Sync: Dance = choreography/body movement. Lip Sync = mouth/face performance to lyrics.
- Dance vs Slice of Life: if dancing is visible, do not call it Slice of Life just because setting is casual.
- Beauty vs Fashion: Beauty = makeup/skincare/hair/nails/cosmetics. Fashion = clothes/outfit/styling.
- Relationship vs Slice of Life: Relationship = romance/partner/love/longing. Slice of Life = ordinary daily life.
- Quotes vs Reflection: Quotes = quote text. Reflection = personal introspection/life lesson.
- Celebrity Edits vs Movie/Tv/Drama Edits: real public figure = Celebrity Edits. Fictional/drama/movie/anime scene = Movie/Tv/Drama Edits.
- Media/Infotainment vs Slice of Life: if the post teaches, explains, recommends or reports, use Media/Infotainment.
- Lyrics vs Lip Sync: Lyrics = text shown. Lip Sync = person mouths/sings lyrics.

=== CONFIDENCE GUIDANCE ===
- 0.90-1.00: clear visual/caption signal.
- 0.75-0.89: likely correct but some ambiguity.
- 0.50-0.74: weak signal; should probably be reviewed.
- <0.50: cannot determine confidently.
For motion-heavy labels like Dance, Lip Sync, Fitness and Cover, lower confidence if only static frames are available and motion is unclear.

=== CONTENT DETAILS ===
Write one concise sentence describing what happens visually, including setting, mood, objects, people and visual style.

=== OUTPUT FORMAT ===
{{"narrative": "<short theme phrase or NA>", "creative_type": ["<label1>", "<label2 optional>"], "content_details": "<one sentence>", "confidence": <float>, "reasoning": "<short reason for Creative Type>"}}"""

def call_gemini(contents, gemini_key, max_retries=4):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=gemini_key)
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(response_mime_type='application/json')
            )
            text = response.text.strip()
            text = re.sub(r'^```json\s*', '', text)
            text = re.sub(r'```$', '', text).strip()
            return json.loads(text)
        except Exception as e:
            err = str(e)
            if '429' in err or 'RESOURCE_EXHAUSTED' in err:
                wait = 90*(attempt+1) + random.randint(0,15)
                time.sleep(wait)
            elif '503' in err or 'UNAVAILABLE' in err:
                wait = 20*(attempt+1) + random.randint(0,10)
                time.sleep(wait)
            else:
                return {'parse_error': True, 'raw_response': err, 'needs_human_review': True}
    return {'parse_error': True, 'raw_response': 'Max retries exceeded', 'needs_human_review': True}

def call_gemini_video_file(video_path, prompt, gemini_key, max_retries=3):
    """Send the full video file to Gemini as a final AI fallback.

    This is intentionally used sparingly because uploading and analysing a video
    is slower and consumes more quota than frame-based analysis.
    """
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=gemini_key)
    uploaded = None
    try:
        uploaded = client.files.upload(file=video_path)

        # Videos can need a short processing period before they are usable.
        for _ in range(30):
            try:
                uploaded = client.files.get(name=uploaded.name)
                state = getattr(uploaded, 'state', None)
                state_name = getattr(state, 'name', str(state)).upper()
                if 'ACTIVE' in state_name or 'SUCCEEDED' in state_name or 'READY' in state_name:
                    break
                if 'FAILED' in state_name:
                    return {'parse_error': True, 'raw_response': 'Video file processing failed', 'needs_human_review': True}
            except Exception:
                # Some SDK versions return immediately usable file handles.
                break
            time.sleep(2)

        video_prompt = prompt + """

FULL VIDEO FALLBACK:
You are now given the full video, not just still frames.
Focus on temporal motion and sequence of actions.
For Dance vs Lip Sync:
- Dance = full-body or upper-body choreography, repeated moves, synchronized/group movement, dance challenge, dance practice/performance.
- Lip Sync = mainly mouth/face performance to lyrics/dialogue, with little or no choreography.
If choreography is visible across time, prioritise Dance over Lip Sync.
Return the same JSON schema only.
"""

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[video_prompt, uploaded],
                    config=types.GenerateContentConfig(response_mime_type='application/json')
                )
                text = response.text.strip()
                text = re.sub(r'^```json\s*', '', text)
                text = re.sub(r'```$', '', text).strip()
                return json.loads(text)
            except Exception as e:
                err = str(e)
                if '429' in err or 'RESOURCE_EXHAUSTED' in err:
                    time.sleep(90*(attempt+1) + random.randint(0,15))
                elif '503' in err or 'UNAVAILABLE' in err:
                    time.sleep(20*(attempt+1) + random.randint(0,10))
                else:
                    return {'parse_error': True, 'raw_response': err, 'needs_human_review': True}
        return {'parse_error': True, 'raw_response': 'Max retries exceeded in video fallback', 'needs_human_review': True}
    except Exception as e:
        return {'parse_error': True, 'raw_response': f'Video fallback failed: {e}', 'needs_human_review': True}
    finally:
        # Best-effort cleanup. Not all SDK/account modes support delete.
        try:
            if uploaded is not None:
                client.files.delete(name=uploaded.name)
        except Exception:
            pass

def _should_try_video_fallback(row, result, status):
    """Use full-video analysis only for likely motion ambiguity, to protect quota."""
    try:
        conf = float(result.get('confidence', 0) or 0)
    except Exception:
        conf = 0
    labels = result.get('creative_type', []) if isinstance(result, dict) else []
    labels = set(labels) if isinstance(labels, list) else set()
    row_motion = _row_has_motion_cues(row)
    result_dance_cues = _result_has_dance_visual_cues(result)
    motion_label = bool(labels & MOTION_HEAVY_TYPES)
    possible_dance_lipsync_confusion = ('Lip Sync' in labels and (row_motion or result_dance_cues))
    return (
        status == 'review'
        or conf < 0.70
        or possible_dance_lipsync_confusion
        or (motion_label and conf < 0.82)
    )

def validate(result):
    issues, score = [], 0
    if result.get('parse_error'):
        return 'review', 0, ['Parse error']
    narrative = result.get('narrative', '')
    if isinstance(narrative, list):
        narrative = ', '.join(str(x).strip() for x in narrative if str(x).strip())
        result['narrative'] = narrative
    narrative_clean = str(narrative).strip()
    if not narrative_clean or narrative_clean in ['null', 'None', '?', '']:
        issues.append('Missing narrative')
    elif len(narrative_clean.split()) > 7:
        issues.append(f'Narrative too long: {narrative_clean}')
    else:
        score += 1
    ct = result.get('creative_type', [])
    if not isinstance(ct, list) or len(ct) == 0:
        issues.append('creative_type must be non-empty list')
    elif len(ct) > 2:
        issues.append(f'Too many creative types: {ct}')
    else:
        invalid = [x for x in ct if x not in ALLOWED_SET]
        if invalid:
            issues.append(f'Invalid labels: {invalid}')
        else:
            score += 2
    cd = result.get('content_details', '')
    if not cd or len(str(cd)) < 20 or cd in ['null', 'None']:
        issues.append('Content details too short')
    else:
        score += 1
    conf = result.get('confidence', 0)
    if conf >= 0.75:
        score += 1
    else:
        issues.append(f'Low confidence: {conf}')
    status = 'pass' if score >= 4 and not issues else 'review'
    return status, score, issues

def build_out(row, vid_id, market, track, result, tier_used, status, score, issues, tier3_reason, raw_record=None, source_file="", source_row_num=None):
    # raw_record is the original JSON object from the uploaded TikTok scraper file.
    # Use it as the source of truth for metrics and URLs because the normalized
    # pandas row can sometimes lose nested fields after reruns.
    raw_record = raw_record or {}
    def _get(field, default=''):
        val = row.get(field, default)
        try:
            if isinstance(val, float) and _math_global.isnan(val):
                return raw_record.get(field, default)
        except Exception:
            pass
        if val in [None, '']:
            return raw_record.get(field, default)
        return val
    def _raw_video_meta(key):
        vm = raw_record.get('videoMeta', {}) if isinstance(raw_record, dict) else {}
        return vm.get(key, '') if isinstance(vm, dict) else ''
    def _raw_media_url():
        media = raw_record.get('mediaUrls', []) if isinstance(raw_record, dict) else []
        if isinstance(media, list) and media:
            return media[0]
        return _raw_video_meta('downloadAddr')
    final_conf  = result.get('confidence', 0)
    needs_human = (
        result.get('needs_human_review', False) or
        status == 'review' or final_conf == 0 or
        not result.get('narrative') or
        result.get('narrative') in ['?', 'null', 'None']
    )
    return {
        'id':                   vid_id,
        'market':               market,
        'track':                track,
        'source_file':          source_file,
        'source_row_num':       source_row_num if source_row_num is not None else '',
        # Public TikTok URL for users to open in browser
        'tiktok_url':           (_get('webVideoUrl') or _get('submittedVideoUrl')
                                 or _get('videoMeta.webVideoUrl') or _get('video.webVideoUrl')
                                 or _get('videoUrl') or _get('url') or _get('inputUrl') or ''),
        # Downloadable media URL for frame extraction / AI review
        'video_url':            (get_video_url(row) or _raw_media_url()),
        'cover_url':            (get_cover_url(row) or _raw_video_meta('originalCoverUrl')
                                 or _raw_video_meta('coverUrl') or _get('coverUrl') or _get('video.coverUrl') or ''),
        'creator':              (_get('authorMeta.name') or _get('authorMeta.nickName') or
                                 (raw_record.get('authorMeta', {}).get('name', '') if isinstance(raw_record.get('authorMeta', {}), dict) else '') or '—'),
        # TikTok username is authorMeta.name; display name is authorMeta.nickName.
        'creator_handle':       (_get('authorMeta.name') or (raw_record.get('authorMeta', {}).get('name', '') if isinstance(raw_record.get('authorMeta', {}), dict) else '')),
        'creator_display':      (_get('authorMeta.nickName') or (raw_record.get('authorMeta', {}).get('nickName', '') if isinstance(raw_record.get('authorMeta', {}), dict) else '')), 
        'caption':              _get('text'),
        'plays':                _si(_get('playCount', raw_record.get('playCount', 0))),
        'likes':                _si(_get('diggCount', raw_record.get('diggCount', 0))),
        'shares':               _si(_get('shareCount', raw_record.get('shareCount', 0))),
        'saves':                _si(_get('collectCount', raw_record.get('collectCount', 0))),
        'comments':             _si(_get('commentCount', raw_record.get('commentCount', 0))),
        'music_name':           (_get('musicMeta.musicName') or (raw_record.get('musicMeta', {}).get('musicName', '') if isinstance(raw_record.get('musicMeta', {}), dict) else '')),
        'music_author':         (_get('musicMeta.musicAuthor') or (raw_record.get('musicMeta', {}).get('musicAuthor', '') if isinstance(raw_record.get('musicMeta', {}), dict) else '')),
        'is_slideshow':         bool(_get('isSlideshow', raw_record.get('isSlideshow', False))),
        'Narrative':            (', '.join(str(x).strip() for x in result.get('narrative', []) if str(x).strip()) if isinstance(result.get('narrative', ''), list) else str(result.get('narrative', '')).strip()),
        'Creative Type':        ', '.join(result.get('creative_type', [])),
        'Content Details':      result.get('content_details', ''),
        'confidence':           final_conf,
        'reasoning':            result.get('reasoning', ''),
        'tier_used':            tier_used,
        'validation_status':    status,
        'validation_score':     score,
        'validation_issues':    ' | '.join(issues) if issues else '',
        'needs_human_review':   needs_human,
        'tier3_reason':         tier3_reason,
        # Keep a lightweight copy of the normalized source row so the Review page
        # can still recover metrics/link/cover for every pending item after reruns.
        '_raw_row_json':        json.dumps(raw_record if raw_record else (row.to_dict() if hasattr(row, 'to_dict') else dict(row)), default=str),
    }

def run_pipeline(records, track, gemini_key, apify_token, log_list, delay_seconds=1, on_row_done=None, source_file=""):
    from google.genai import types as gtypes
    raw_records_by_index = {i: rec for i, rec in enumerate(records) if isinstance(rec, dict)}
    raw_records_map = {str(rec.get('id', i)): rec for i, rec in enumerate(records) if isinstance(rec, dict)}
    df = pd.json_normalize(records)
    results = []
    for i, (_, row) in enumerate(df.iterrows()):
        raw_source = raw_records_by_index.get(i, {})
        row_id_val = row.get('id', '')
        try:
            row_id_missing = pd.isna(row_id_val)
        except Exception:
            row_id_missing = row_id_val in [None, '']
        if not row_id_missing and str(row_id_val).strip():
            vid_id = str(row_id_val).strip()
            raw_source = raw_records_map.get(vid_id, raw_source)
        elif raw_source.get('id'):
            vid_id = str(raw_source.get('id')).strip()
        else:
            # Error / sensitive rows may not have an id. Use URL as a stable id so the review page can still find it.
            vid_id = str(raw_source.get('url') or row.get('url') or f'error_row_{i}').strip()

        caption = str(row.get('text', '') if not pd.isna(row.get('text', '')) else '')[:60]
        log_list.append(f"[{i+1}/{len(df)}] {caption or raw_source.get('error', 'scraper error row')}...")
        market = row.get('locationCreated', raw_source.get('locationCreated', 'UNKNOWN'))
        try:
            if pd.isna(market):
                market = raw_source.get('locationCreated', 'UNKNOWN')
        except Exception:
            pass

        # Special case: scraper failed / sensitive / unavailable post.
        # Important: pandas creates NaN for missing error columns; NaN is truthy in Python.
        # Use _clean_text so normal rows are NOT incorrectly sent to human review.
        def _clean_text(v):
            try:
                if pd.isna(v):
                    return ''
            except Exception:
                pass
            if v is None:
                return ''
            txt = str(v).strip()
            return '' if txt.lower() in ['nan', 'none', 'null'] else txt

        scraper_error = _clean_text(raw_source.get('error')) or _clean_text(row.get('error'))
        scraper_error_code = _clean_text(raw_source.get('errorCode')) or _clean_text(row.get('errorCode'))

        raw_play = _si(raw_source.get('playCount', row.get('playCount', 0)))
        raw_like = _si(raw_source.get('diggCount', row.get('diggCount', 0)))
        raw_share = _si(raw_source.get('shareCount', row.get('shareCount', 0)))
        raw_comment = _si(raw_source.get('commentCount', row.get('commentCount', 0)))
        raw_save = _si(raw_source.get('collectCount', row.get('collectCount', 0)))
        public_url = _clean_text(raw_source.get('webVideoUrl')) or _clean_text(raw_source.get('submittedVideoUrl')) or _clean_text(raw_source.get('url')) or _clean_text(row.get('url'))
        all_metrics_zero = (raw_play == 0 and raw_like == 0 and raw_share == 0 and raw_comment == 0 and raw_save == 0)

        # Only rows with an actual scraper error, or rows with no usable metrics but a URL,
        # go directly to manual review. Normal rows continue to Gemini.
        if scraper_error or scraper_error_code or (all_metrics_zero and public_url and not _clean_text(row.get('text'))):
            reason_text = scraper_error or scraper_error_code or 'Metrics unavailable from scraper'
            log_list.append(f"  → Scraper/metrics exception ({scraper_error_code or reason_text}) — manual review with TikTok URL")
            result = {
                'narrative': '',
                'creative_type': [],
                'content_details': '',
                'confidence': 0,
                'reasoning': str(reason_text),
                'needs_human_review': True,
            }
            out = build_out(
                row, vid_id, market, track, result,
                'scraper_exception', 'review', 0,
                [str(scraper_error_code or reason_text)],
                'Scraper could not retrieve full metadata. Open the TikTok URL, tag manually, and fill metrics if needed.',
                raw_source, source_file, i
            )
            # Ensure the public URL is preserved even when the scraper row only has `url`.
            if not out.get('tiktok_url') and public_url:
                out['tiktok_url'] = public_url
            out['manual_metrics_required'] = (out.get('plays', 0) == 0 and out.get('likes', 0) == 0 and out.get('shares', 0) == 0)
            results.append(out)
            if on_row_done:
                on_row_done(i + 1, len(df), out, 'scraper_exception')
            time.sleep(delay_seconds)
            continue

        if is_too_vague(row):
            log_list.append("  → Caption too vague — trying visual-only analysis (Tier 0V)...")
            vague_prompt = build_prompt(row).replace(
                "Analyse this TikTok post. Return ONLY valid JSON — no markdown, no explanation.",
                "Analyse this TikTok post. NOTE: No caption or hashtags are available — judge PURELY from visuals. Return ONLY valid JSON — no markdown, no explanation."
            )
            tier0_result = None
            # Try video frames first for vague posts (best signal without text)
            video_url = get_video_url(row)
            if video_url:
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        video_path = os.path.join(tmp, f'{vid_id}.mp4')
                        download_video(video_url, video_path, apify_token)
                        frame_paths = extract_frames(video_path, os.path.join(tmp, 'frames'))
                        contents_v = [vague_prompt]
                        for fp in frame_paths:
                            with open(fp, 'rb') as f:
                                contents_v.append(gtypes.Part.from_bytes(data=f.read(), mime_type='image/jpeg'))
                        tier0_result = call_gemini(contents_v, gemini_key)
                        tier0_result['tier_used'] = 'tier0_visual_frames'
                        log_list.append("  → Tier 0V: video frames sent to Gemini")
                except Exception as e:
                    log_list.append(f"  → Tier 0V video failed: {e}")
            # Fallback to cover image if video unavailable or failed
            if tier0_result is None:
                cover_url = get_cover_url(row)
                if cover_url:
                    try:
                        img_bytes = download_image_bytes(cover_url, apify_token)
                        contents_c = [vague_prompt, gtypes.Part.from_bytes(data=img_bytes, mime_type='image/jpeg')]
                        tier0_result = call_gemini(contents_c, gemini_key)
                        tier0_result['tier_used'] = 'tier0_visual_cover'
                        log_list.append("  → Tier 0V: cover image sent to Gemini")
                    except Exception as e:
                        log_list.append(f"  → Tier 0V cover failed: {e}")
            # Evaluate result — only flag human if still can't determine
            if tier0_result is not None and not tier0_result.get('parse_error'):
                t0_status, t0_score, t0_issues = validate(tier0_result)
                if t0_status == 'pass' and tier0_result.get('confidence', 0) >= 0.70:
                    log_list.append(f"  → Tier 0V PASS: {tier0_result.get('narrative')} | {tier0_result.get('confidence',0):.0%}")
                    out = build_out(row, vid_id, market, track, tier0_result,
                                   tier0_result['tier_used'], t0_status, t0_score, t0_issues, '', raw_source, source_file, i)
                    results.append(out)
                    if on_row_done:
                        on_row_done(i + 1, len(df), out, tier0_result['tier_used'])
                    time.sleep(delay_seconds)
                    continue
                else:
                    log_list.append(f"  → Tier 0V low confidence ({tier0_result.get('confidence',0):.0%}) — flagging for human review")
                    out = build_out(row, vid_id, market, track, tier0_result,
                                   tier0_result['tier_used'], 'review', t0_score, t0_issues,
                                   'Vague caption + low visual confidence', raw_source, source_file, i)
            else:
                log_list.append("  → Tier 0V failed completely — flagging for human review")
                out = build_out(row, vid_id, market, track,
                               {'needs_human_review': True, 'narrative': '', 'confidence': 0},
                               'tier0_skipped', 'review', 0, ['Vague caption, no visual signal'],
                               'Caption too vague — visual analysis also failed', raw_source, source_file, i)
            results.append(out)
            if on_row_done:
                on_row_done(i + 1, len(df), out, out.get('tier_used', 'tier0_skipped'))
            time.sleep(delay_seconds)
            continue

        log_list.append("  → Tier 1 (cover image)...")
        prompt    = build_prompt(row)
        cover_url = get_cover_url(row)
        if cover_url:
            try:
                img_bytes = download_image_bytes(cover_url, apify_token)
                contents  = [prompt, gtypes.Part.from_bytes(data=img_bytes, mime_type='image/jpeg')]
            except:
                contents = [prompt]
        else:
            contents = [prompt]

        result = call_gemini(contents, gemini_key)
        result = apply_dance_guardrails(result, row)
        result['tier_used'] = 'tier1_cover'
        status, score, issues = validate(result)

        if status == 'review' or result.get('confidence', 0) < 0.75:
            log_list.append("  → Tier 2A (3 video frames)...")
            video_url = get_video_url(row)
            if video_url:
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        video_path = os.path.join(tmp, f'{vid_id}.mp4')
                        download_video(video_url, video_path, apify_token)

                        # Tier 2A: fast default pass using 3 frames.
                        frame_paths = extract_frames(video_path, os.path.join(tmp, 'frames_3'), FRAME_POINTS_3)
                        contents2 = [prompt]
                        for fp in frame_paths:
                            with open(fp, 'rb') as f:
                                contents2.append(gtypes.Part.from_bytes(data=f.read(), mime_type='image/jpeg'))
                        result2 = call_gemini(contents2, gemini_key)
                        result2 = apply_dance_guardrails(result2, row)
                        result2['tier_used'] = 'tier2a_3frames'
                        status2, score2, issues2 = validate(result2)
                        if score2 >= score or result.get('parse_error'):
                            result, status, score, issues = result2, status2, score2, issues2

                        # Tier 2B: adaptive motion refinement.
                        # Only run the slower 9-frame pass when the content is likely motion-heavy
                        # or the 3-frame result is still weak. This is designed to help KR/Dance
                        # without slowing every PH-style Lip Sync / Relationship / Quote post.
                        should_refine_motion = (
                            # Avoid spending 9-frame calls on every genuine PH-style Lip Sync.
                            # Refine when there are dance/choreography cues, an initial Dance/Fitness/Cover label,
                            # or the 3-frame result is still weak/invalid.
                            _row_has_motion_cues(row)
                            or _result_has_dance_visual_cues(result2)
                            or any(x in set(result2.get('creative_type', [])) for x in ['Dance', 'Fitness', 'Cover'])
                            or status2 == 'review'
                            or result2.get('confidence', 0) < 0.75
                        )
                        if should_refine_motion:
                            log_list.append("  → Tier 2B (adaptive 9-frame motion refinement)...")
                            frame_paths_9 = extract_frames(video_path, os.path.join(tmp, 'frames_9'), FRAME_POINTS_9)
                            contents9 = [prompt + "\n\nMotion-aware refinement: analyse the sequence of frames carefully. If full-body choreography or repeated body movement is visible across frames, prioritise Dance over Lip Sync or Relationship. Use Lip Sync only when mouth/face performance is the main action and there is little/no choreography."]
                            for fp in frame_paths_9:
                                with open(fp, 'rb') as f:
                                    contents9.append(gtypes.Part.from_bytes(data=f.read(), mime_type='image/jpeg'))
                            result9 = call_gemini(contents9, gemini_key)
                            result9 = apply_dance_guardrails(result9, row)
                            result9['tier_used'] = 'tier2b_9frames_adaptive'
                            status9, score9, issues9 = validate(result9)
                            # Prefer 9-frame result only when it is clearly stronger or fixes a failed/low-confidence result.
                            if (
                                score9 > score
                                or result.get('parse_error')
                                or (status != 'pass' and status9 == 'pass')
                                or (result9.get('confidence', 0) >= result.get('confidence', 0) + 0.10)
                            ):
                                result, status, score, issues = result9, status9, score9, issues9

                        # Tier 2C: full-video fallback, used only for unresolved motion-heavy ambiguity.
                        # This is slower and consumes more quota, so it is deliberately conservative.
                        if _should_try_video_fallback(row, result, status):
                            log_list.append("  → Tier 2C (full video fallback, motion ambiguity only)...")
                            video_prompt = prompt + "\n\nUse the full video to resolve motion ambiguity. If choreography is visible over time, choose Dance over Lip Sync."
                            resultv = call_gemini_video_file(video_path, video_prompt, gemini_key)
                            resultv = apply_dance_guardrails(resultv, row)
                            resultv['tier_used'] = 'tier2c_full_video'
                            statusv, scorev, issuesv = validate(resultv)
                            # Prefer full-video result when it passes validation and is at least as strong,
                            # or when it fixes a low-confidence/review result.
                            if (
                                not resultv.get('parse_error')
                                and (
                                    scorev > score
                                    or (status != 'pass' and statusv == 'pass')
                                    or (resultv.get('confidence', 0) >= max(0.75, result.get('confidence', 0) + 0.05))
                                )
                            ):
                                result, status, score, issues = resultv, statusv, scorev, issuesv
                except Exception as e:
                    log_list.append(f"  → Tier 2 failed: {e}")

        final_conf  = result.get('confidence', 0)
        needs_human = (
            result.get('needs_human_review', False) or
            status == 'review' or final_conf == 0 or
            not result.get('narrative') or
            result.get('narrative') in ['?', 'null', 'None']
        )
        tier3_reason = (
            'conf=0 or parse error after Tier 2' if needs_human and final_conf == 0 else
            'low confidence after Tier 2' if needs_human and final_conf < 0.75 else
            'validation failed' if needs_human else ''
        )
        out = build_out(row, vid_id, market, track, result,
                       result.get('tier_used',''), status, score, issues, tier3_reason, raw_source, source_file, i)
        results.append(out)
        row_summary = f"  → {result.get('narrative','?')} | {result.get('creative_type',[])} | {final_conf:.0%} | {status}"
        log_list.append(row_summary)
        if on_row_done:
            on_row_done(i + 1, len(df), out, result.get('tier_used', ''))
        time.sleep(delay_seconds)
    return pd.DataFrame(results)

# ══════════════════════════════════════════════════════════
# TOP NAVBAR (session state routing)
# ══════════════════════════════════════════════════════════
PAGES = ["Home", "Batch Filter", "Upload & Tag", "Review Flagged", "Summary", "Export"]
if 'page' not in st.session_state:
    st.session_state.page = "Home"

# Render full navbar with brand + nav buttons inline via JS trick
page = st.session_state.page

st.markdown("""
<style>
/* Navbar row alignment */
div.navbar-row > div[data-testid="stHorizontalBlock"] {
    background: #1e1b4b;
    border-radius: 10px;
    padding: 8px 16px;
    align-items: center;
    gap: 4px;
}
div.navbar-row button {
    border-radius: 6px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    height: 36px !important;
    padding: 0 10px !important;
    border: none !important;
    white-space: nowrap;
}
div.navbar-row button[kind="secondary"] {
    background: transparent !important;
    color: #a5b4fc !important;
}
div.navbar-row button[kind="secondary"]:hover {
    background: #3730a3 !important;
    color: white !important;
}
div.navbar-row button[kind="primary"] {
    background: #4f46e5 !important;
    color: white !important;
}
div.navbar-row > div[data-testid="stHorizontalBlock"] > div:first-child {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="navbar-row">', unsafe_allow_html=True)
brand, *btn_cols = st.columns([2.2, 1.0, 1.15, 1.15, 1.35, 1.0, 0.9])
with brand:
    st.markdown(
        "<p style='color:white;font-weight:700;font-size:15px;margin:0;line-height:36px;padding-left:4px'>"
        "TikTok Tagging</p>",
        unsafe_allow_html=True
    )
for col, p in zip(btn_cols, PAGES):
    with col:
        btn_type = "primary" if page == p else "secondary"
        if st.button(p, key=f"nav_{p}", type=btn_type, use_container_width=True):
            st.session_state.page = p
            st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# API Keys in a compact expander
with st.expander("API Keys", expanded=(st.session_state.gemini_key == '')):
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        gemini_key = st.text_input("Gemini API Key", type="password",
                                   value=st.session_state.gemini_key,
                                   label_visibility="collapsed",
                                   placeholder="Gemini API Key")
    with c2:
        apify_token = st.text_input("Apify Token", type="password",
                                    value=st.session_state.apify_token,
                                    label_visibility="collapsed",
                                    placeholder="Apify Token")
    with c3:
        if st.button("Save Keys", type="primary"):
            st.session_state.gemini_key  = gemini_key
            st.session_state.apify_token = apify_token
            st.success("Saved")

if not st.session_state.master_df.empty:
    df = st.session_state.master_df
    flagged = int(df['needs_human_review'].sum())
    st.caption(f"{len(df)} rows  ·  {df['track'].nunique()} track(s)  ·  {flagged} need review")

# ══════════════════════════════════════════════════════════
# HOME
# ══════════════════════════════════════════════════════════
if page == "Home":
    st.markdown("""
    <div class='page-header'>
        <h1>TikTok Content Tagging Pipeline</h1>
        <p>UMG Music Marketing &nbsp;·&nbsp; SEA + KR Markets</p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.master_df.empty:
        st.markdown("""
        <div class='section-card'>
            <h3>Getting Started</h3>
            <ol style='color:#374151;font-size:14px;line-height:2'>
                <li>Start at <strong>Batch Filter</strong> — upload the tracklist and MelodyIQ CSVs, filter the rows you want, then send the filtered report into tagging</li>
                <li>Enter your <strong>Gemini</strong> and <strong>Apify</strong> API keys above</li>
                <li>Go to <strong>Upload &amp; Tag</strong> — use the filtered MelodyIQ report as the source of truth, then run Apify + AI tagging</li>
                <li>Repeat for each track / market</li>
                <li>Go to <strong>Review Flagged</strong> — manually tag any posts the AI couldn't handle</li>
                <li>Go to <strong>Export</strong> — download the final CSV</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)
    else:
        df = st.session_state.master_df
        total     = len(df)
        ai_tagged = (df['validation_status'] == 'pass').sum()
        flagged   = int(df['needs_human_review'].sum())
        avg_conf  = df[df['confidence'] > 0]['confidence'].mean()

        st.markdown(f"""
        <div class='metric-row'>
            <div class='metric-card'><div class='val'>{total}</div><div class='lbl'>Total Posts</div></div>
            <div class='metric-card'><div class='val green'>{ai_tagged}</div><div class='lbl'>AI Tagged ({int(ai_tagged/total*100)}%)</div></div>
            <div class='metric-card'><div class='val indigo'>{int(ai_tagged/total*100)}%</div><div class='lbl'>Automation Rate</div></div>
            <div class='metric-card'><div class='val amber'>{flagged}</div><div class='lbl'>Need Review</div></div>
            <div class='metric-card'><div class='val'>{avg_conf:.0%}</div><div class='lbl'>Avg Confidence</div></div>
            <div class='metric-card'><div class='val'>{df['track'].nunique()}</div><div class='lbl'>Tracks</div></div>
        </div>
        """, unsafe_allow_html=True)

        # ── Filters ───────────────────────────────────────────
        fc1, fc2, fc3 = st.columns([2, 2, 2])
        with fc1:
            track_opts = ['All'] + sorted(df['track'].dropna().unique().tolist())
            sel_track  = st.selectbox("Filter by Track", track_opts, key="home_track_filter")
        with fc2:
            status_opts = ['All', 'Pass', 'Needs Review']
            sel_status  = st.selectbox("Filter by Status", status_opts, key="home_status_filter")
        with fc3:
            tier_opts = ['All'] + sorted(df['tier_used'].dropna().unique().tolist()) if 'tier_used' in df.columns else ['All']
            sel_tier  = st.selectbox("Filter by Tier", tier_opts, key="home_tier_filter")

        view_df = df.copy()
        if sel_track != 'All':
            view_df = view_df[view_df['track'] == sel_track]
        if sel_status == 'Pass':
            view_df = view_df[view_df['needs_human_review'] == False]
        elif sel_status == 'Needs Review':
            view_df = view_df[view_df['needs_human_review'] == True]
        if sel_tier != 'All' and 'tier_used' in view_df.columns:
            view_df = view_df[view_df['tier_used'] == sel_tier]

        st.markdown(f"<p style='font-size:12px;color:#64748b;margin:4px 0 12px'>Showing {len(view_df)} of {len(df)} rows</p>", unsafe_allow_html=True)

        # ── Legend ────────────────────────────────────────────
        st.markdown("""
        <div style='display:flex;gap:16px;margin-bottom:14px;flex-wrap:wrap'>
            <span style='font-size:12px;color:#475569'>
                <span style='display:inline-block;width:10px;height:10px;border-radius:2px;background:#ecfdf5;border:1px solid #6ee7b7;margin-right:4px'></span>AI Pass
            </span>
            <span style='font-size:12px;color:#475569'>
                <span style='display:inline-block;width:10px;height:10px;border-radius:2px;background:#fffbeb;border:1px solid #fcd34d;margin-right:4px'></span>Needs Review
            </span>
            <span style='font-size:12px;color:#475569'>● Score /5 &nbsp;·&nbsp; Confidence bar &nbsp;·&nbsp; Tier pill &nbsp;·&nbsp; Issues &amp; Reasoning shown inline</span>
        </div>
        """, unsafe_allow_html=True)

        # ── Rich table ────────────────────────────────────────
        TIER_COLORS = {
            'tier1_cover':         ('#eef2ff', '#4338ca', 'T1 Cover'),
            'tier2_frames':        ('#f0fdf4', '#047857', 'T2 Frames'),
            'tier0_visual_frames': ('#fdf4ff', '#7e22ce', 'T0V Frames'),
            'tier0_visual_cover':  ('#fdf4ff', '#7e22ce', 'T0V Cover'),
            'tier0_skipped':       ('#fef2f2', '#dc2626', 'T0 Skip'),
        }

        def tier_pill(tier):
            bg, fg, label = TIER_COLORS.get(tier, ('#f1f5f9', '#475569', tier or '—'))
            return f"<span style='background:{bg};color:{fg};border-radius:999px;padding:2px 9px;font-size:11px;font-weight:700;white-space:nowrap'>{label}</span>"

        def conf_bar(conf):
            pct  = int((conf or 0) * 100)
            color = '#059669' if pct >= 75 else '#d97706' if pct >= 50 else '#dc2626'
            return f"""
            <div style='display:flex;align-items:center;gap:6px'>
                <div style='flex:1;background:#e2e8f0;border-radius:999px;height:6px;min-width:60px'>
                    <div style='width:{pct}%;background:{color};border-radius:999px;height:6px'></div>
                </div>
                <span style='font-size:12px;font-weight:700;color:{color};min-width:30px'>{pct}%</span>
            </div>"""

        def score_badge(score, status):
            bg  = '#ecfdf5' if status == 'pass' else '#fef2f2'
            fg  = '#047857' if status == 'pass' else '#dc2626'
            return f"<span style='background:{bg};color:{fg};border-radius:6px;padding:3px 8px;font-size:12px;font-weight:800'>{score}/5</span>"

        def issues_html(issues_str, reasoning):
            parts = []
            if issues_str and issues_str.strip():
                for iss in issues_str.split(' | '):
                    parts.append(f"<span style='background:#fef2f2;color:#dc2626;border-radius:4px;padding:1px 6px;font-size:11px;margin-right:3px'>⚠ {iss.strip()}</span>")
            if reasoning and str(reasoning).strip() and reasoning not in ['', 'nan']:
                parts.append(f"<span style='color:#64748b;font-size:11px;font-style:italic'>💬 {str(reasoning).strip()}</span>")
            return '<br>'.join(parts) if parts else "<span style='color:#94a3b8;font-size:11px'>—</span>"

        # Header row
        st.markdown("""
        <div style='display:grid;grid-template-columns:1.8fr 1.2fr 1.5fr 1.2fr 1fr 1.3fr 0.7fr 1.5fr;gap:8px;
                    padding:8px 12px;background:#f1f5f9;border-radius:8px;margin-bottom:4px'>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Creator / Caption</span>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Track / Market</span>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Narrative · Creative Type</span>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Content Details</span>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Confidence</span>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Issues / Reasoning</span>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Score</span>
            <span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Tier</span>
        </div>
        """, unsafe_allow_html=True)

        import html as _home_html
        rows_html = []
        for _, r in view_df.head(200).iterrows():
            is_review = bool(r.get('needs_human_review', False))
            row_bg    = '#fffbeb' if is_review else '#ffffff'
            border    = '#fcd34d' if is_review else '#e2e8f0'

            raw_caption = str(r.get('caption', '') or '')
            caption_short = raw_caption[:80] + ('...' if len(raw_caption) > 80 else '')
            creator       = str(r.get('creator', '') or '-').strip() or '-'
            raw_handle    = str(r.get('creator_handle', '') or '').strip()
            raw_display   = str(r.get('creator_display', '') or '').strip()
            # Old cached rows may have handle/display swapped. TikTok handles are usually
            # ASCII usernames without spaces; display names often contain spaces or local scripts.
            def _looks_like_tiktok_handle(x):
                return bool(re.fullmatch(r'@?[A-Za-z0-9._]{2,32}', str(x).strip()))
            if raw_handle and raw_display and (not _looks_like_tiktok_handle(raw_handle)) and _looks_like_tiktok_handle(raw_display):
                raw_handle, raw_display = raw_display, raw_handle
            if not raw_handle and _looks_like_tiktok_handle(creator):
                raw_handle = creator
            if not raw_display and creator and creator != raw_handle:
                raw_display = creator
            tiktok_url    = str(r.get('tiktok_url', '') or '').strip()
            narrative     = str(r.get('Narrative', '') or '-')
            ct            = str(r.get('Creative Type', '') or '-')
            raw_cd        = str(r.get('Content Details', '') or '-')
            cd            = raw_cd[:90] + ('...' if len(raw_cd) > 90 else '')
            track         = str(r.get('track', '') or '-')
            market        = str(r.get('market', '') or '-')
            conf          = r.get('confidence', 0) or 0
            score         = r.get('validation_score', 0) or 0
            status        = str(r.get('validation_status', '') or '')
            tier          = str(r.get('tier_used', '') or '')
            issues        = str(r.get('validation_issues', '') or '')
            reasoning     = str(r.get('reasoning', '') or '')

            # Escape all user / AI generated text before inserting into HTML.
            # Otherwise captions or model outputs containing <div>, backticks, etc.
            # can break Streamlit markdown and show raw HTML as a code block.
            handle_clean = raw_handle.lstrip('@') if raw_handle else ''
            creator_main = f"@{handle_clean}" if handle_clean else creator
            creator_e = _home_html.escape(creator_main)
            display_e = _home_html.escape(raw_display) if raw_display and raw_display != raw_handle and raw_display != handle_clean else ''
            caption_e = _home_html.escape(caption_short)
            narrative_e = _home_html.escape(narrative)
            ct_e = _home_html.escape(ct)
            cd_e = _home_html.escape(cd)
            track_e = _home_html.escape(track)
            market_e = _home_html.escape(market)
            url_e = _home_html.escape(tiktok_url, quote=True)

            link_html = (
                f"<a href='{url_e}' target='_blank' style='font-size:11px;color:#4f46e5;font-weight:700;text-decoration:none'>Watch TikTok ↗</a>"
                if tiktok_url else "<span style='font-size:11px;color:#94a3b8'>No TikTok link</span>"
            )

            creator_block = (
                f"<div style='font-size:13px;font-weight:700;color:#1e293b'>{creator_e}</div>"
                + (f"<div style='font-size:11px;color:#64748b;margin-top:1px'>{display_e}</div>" if display_e else "")
            )
            rows_html.append(
                f"<div style='display:grid;grid-template-columns:1.8fr 1.2fr 1.5fr 1.2fr 1fr 1.3fr 0.7fr 1.5fr;gap:8px;"
                f"padding:12px;background:{row_bg};border:1px solid {border};border-radius:8px;margin-bottom:6px;align-items:start'>"
                f"<div>"
                f"{creator_block}"
                f"<div style='font-size:11px;color:#64748b;margin-top:2px'>{caption_e}</div>"
                f"<div style='margin-top:4px'>{link_html}</div>"
                f"</div>"
                f"<div>"
                f"<div style='font-size:12px;font-weight:600;color:#1e293b'>{track_e}</div>"
                f"<div style='font-size:11px;color:#64748b'>{market_e}</div>"
                f"</div>"
                f"<div>"
                f"<div style='font-size:12px;font-weight:700;color:#4f46e5'>{narrative_e}</div>"
                f"<div style='font-size:11px;color:#475569;margin-top:2px'>{ct_e}</div>"
                f"</div>"
                f"<div style='font-size:11px;color:#334155'>{cd_e}</div>"
                f"<div>{conf_bar(conf)}</div>"
                f"<div>{issues_html(_home_html.escape(issues), _home_html.escape(reasoning))}</div>"
                f"<div>{score_badge(score, status)}</div>"
                f"<div>{tier_pill(tier)}</div>"
                f"</div>"
            )

        st.markdown(''.join(rows_html), unsafe_allow_html=True)
        if len(view_df) > 200:
            st.caption(f"Showing first 200 of {len(view_df)} rows. Use filters above to narrow down.")

# ══════════════════════════════════════════════════════════
# UPLOAD & TAG
# ══════════════════════════════════════════════════════════
elif page == "Upload & Tag":
    st.markdown("""
    <div class='page-header'>
        <h1>Upload &amp; Tag</h1>
        <p>Upload Apify JSON exports, name each track, then run the AI tagging pipeline.</p>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.gemini_key or not st.session_state.apify_token:
        st.markdown("<div class='warn-banner'>⚠️ Enter your API keys above before continuing.</div>", unsafe_allow_html=True)
        st.stop()

    # ── Step 0: Source report from Batch Filter or manual upload ─────────────────────
    st.markdown("""
    <div class='section-card' style='margin-bottom:16px'>
        <h3>Step 0 — Source MelodyIQ / Tracking Report</h3>
        <p style='font-size:13px;color:#64748b;margin:0 0 14px'>
            If you already completed <strong>Batch Filter</strong>, the filtered output is used automatically here.
            You can still upload another CSV/XLSX below if you want to replace it manually. The app uses the
            <strong>Country / Market</strong> column as the source of truth.
        </p>
    """, unsafe_allow_html=True)

    if not st.session_state.original_df.empty:
        source_note = "Batch Filter output" if not st.session_state.get('batch_filter_df', pd.DataFrame()).empty else "Uploaded original report"
        st.markdown(
            f"<div class='info-banner'>✅ Using <strong>{source_note}</strong> as the source report · "
            f"{len(st.session_state.original_df)} rows. Upload another file below only if you want to replace it.</div>",
            unsafe_allow_html=True
        )

    original_file = st.file_uploader(
        "Upload another original CSV / XLSX report (optional)",
        type=["csv", "xlsx", "xls"],
        key="original_master_uploader"
    )
    if original_file is not None:
        try:
            original_df, original_kind = _read_report_global(original_file)
            original_url_col = _detect_url_col_global(original_df)
            original_market_col = _detect_market_col_global(original_df)
            if not original_url_col:
                st.error("Could not find a Link / URL column in the original report.")
            elif not original_market_col:
                st.error("Could not find a Country / Market column in the original report.")
            else:
                st.session_state.original_df = original_df.copy()
                st.session_state.original_url_col = original_url_col
                st.session_state.original_market_map = _build_original_market_map(original_df, original_url_col, original_market_col)
                st.success(f"Original report loaded: {len(original_df)} rows · Link column: {original_url_col} · Market column: {original_market_col}")
        except Exception as e:
            st.error(f"Could not read original report: {e}")
    elif not st.session_state.original_df.empty:
        st.info(f"Original report already loaded: {len(st.session_state.original_df)} rows · Market will come from this file.")
    else:
        st.warning("Recommended: upload the original report first. If skipped, market will fall back to JSON locationCreated.")
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Step 1A: Run Apify inside this app ─────────────────
    st.markdown("""
    <div class='section-card' style='margin-bottom:16px'>
        <h3>Step 1A — Run Apify Scraper Inside This App</h3>
        <p style='font-size:13px;color:#64748b;margin:0 0 14px'>
            This mode reads the <strong>Link</strong> column from the original MelodyIQ report, groups rows by
            <strong>Country + Artist - Sound</strong>, runs the existing Apify TikTok Scraper using <code>postURLs</code>,
            then sends the returned records into the same AI tagging pipeline.
        </p>
    """, unsafe_allow_html=True)

    if st.session_state.original_df.empty:
        st.markdown("<div class='warn-banner'>Upload the original report above to enable built-in Apify scraping.</div>", unsafe_allow_html=True)
    else:
        orig_df = st.session_state.original_df.copy()
        url_col_api = st.session_state.get('original_url_col') or _detect_url_col_global(orig_df)
        market_col_api = _detect_market_col_global(orig_df)
        track_col_api = _detect_track_col_global(orig_df)

        if not url_col_api or not track_col_api:
            st.error("Could not detect required columns for Apify mode. Need at least Link and Artist - Sound / Track columns.")
            st.caption(f"Available columns: {', '.join(orig_df.columns.astype(str).tolist())}")
        else:
            batches = _build_excel_track_batches(orig_df, market_col_api, track_col_api, url_col_api)
            total_links_api = sum(b['link_count'] for b in batches)
            st.markdown(f"""
            <div class='metric-row' style='margin-bottom:12px'>
                <div class='metric-card'><div class='val'>{len(orig_df)}</div><div class='lbl'>Original Rows</div></div>
                <div class='metric-card'><div class='val'>{len(batches)}</div><div class='lbl'>Track Batches</div></div>
                <div class='metric-card'><div class='val indigo'>{total_links_api}</div><div class='lbl'>TikTok Links</div></div>
                <div class='metric-card'><div class='val'>{url_col_api}</div><div class='lbl'>Link Column</div></div>
            </div>
            """, unsafe_allow_html=True)

            if batches:
                preview_batches = pd.DataFrame([
                    {'Country': b['country'], 'Artist - Sound': b['track'], 'Original Rows': b['rows'], 'Links': b['link_count']}
                    for b in batches
                ])
                with st.expander("Detected track batches", expanded=False):
                    st.dataframe(preview_batches, use_container_width=True, hide_index=True)

                api_mode_col1, api_mode_col2 = st.columns([2, 1])
                with api_mode_col1:
                    selected_batch_labels = [f"{b['country']} · {b['track']} ({b['link_count']} links)" for b in batches]
                    run_scope_api = st.radio(
                        "Apify run scope",
                        ["Run all detected tracks", "Run one selected track"],
                        horizontal=True,
                        key="apify_run_scope"
                    )
                    if run_scope_api == "Run one selected track":
                        selected_label_api = st.selectbox("Select track", selected_batch_labels, key="apify_selected_track")
                        api_run_batches = [batches[selected_batch_labels.index(selected_label_api)]]
                    else:
                        api_run_batches = batches
                with api_mode_col2:
                    api_delay = st.slider(
                        "AI delay after scrape",
                        min_value=0,
                        max_value=10,
                        value=1,
                        key="apify_ai_delay",
                        help="Delay between Gemini calls after Apify returns records."
                    )

                run_api_disabled = (not st.session_state.apify_token or not st.session_state.gemini_key or not api_run_batches)
                if run_api_disabled:
                    st.caption("Enter both Gemini and Apify keys before running Apify mode.")

                if st.button("🚀 Run Apify + AI Tagging", type="primary", disabled=run_api_disabled, use_container_width=True, key="run_apify_inside_app"):
                    all_results = []
                    progress_bar = st.progress(0)
                    status_box = st.empty()
                    log_box = st.empty()
                    log_lines = []

                    for batch_i, batch in enumerate(api_run_batches):
                        status_box.markdown(
                            f"<div class='info-banner'>Running Apify for <strong>{batch['country']} · {batch['track']}</strong> "
                            f"({batch['link_count']} links) — batch {batch_i+1} of {len(api_run_batches)}</div>",
                            unsafe_allow_html=True
                        )
                        try:
                            items = run_apify_tiktok_scraper_api(batch['links'], st.session_state.apify_token)
                        except Exception as e:
                            st.error(f"Apify failed for {batch['track']}: {e}")
                            continue

                        # Cache raw records so Review page can recover URLs, cover images and metrics.
                        for rec in items:
                            if isinstance(rec, dict):
                                rid = str(rec.get('id', ''))
                                if rid:
                                    st.session_state.raw_records[rid] = rec
                        st.session_state.staged_files.append({
                            'name': f"apify_api_{batch['country']}_{batch['track']}",
                            'records': items,
                            'track': batch['track'],
                            'market': batch['country'],
                            'has_video': True,
                            'tagged': True,
                        })

                        log_lines.append(f"Apify returned {len(items)} item(s) for {batch['track']}.")
                        log_box.code('\n'.join(log_lines[-8:]))

                        def on_api_row_done(row_num, total, out, tier_used):
                            overall = (batch_i + (row_num / max(total, 1))) / max(len(api_run_batches), 1)
                            progress_bar.progress(min(overall, 1.0))

                        result_df = run_pipeline(
                            items,
                            batch['track'],
                            st.session_state.gemini_key,
                            st.session_state.apify_token,
                            log_lines,
                            delay_seconds=api_delay,
                            on_row_done=on_api_row_done,
                            source_file=f"apify_api_{batch['country']}_{batch['track']}"
                        )
                        if not result_df.empty:
                            result_df['market'] = batch['country']
                            all_results.append(result_df)

                    progress_bar.progress(1.0)
                    status_box.empty()

                    if all_results:
                        combined = pd.concat(all_results, ignore_index=True)
                        combined = _apply_original_market_to_results(combined)
                        if st.session_state.master_df.empty:
                            st.session_state.master_df = combined.copy()
                        else:
                            existing_ids = set(st.session_state.master_df['id'].astype(str))
                            new_rows = combined[~combined['id'].astype(str).isin(existing_ids)]
                            st.session_state.master_df = pd.concat([st.session_state.master_df, new_rows], ignore_index=True)
                        st.session_state.master_df = _apply_original_market_to_results(st.session_state.master_df)
                        st.session_state.has_tagged_results = True
                        st.session_state.review_idx = 0

                        passed = int((combined['validation_status'] == 'pass').sum())
                        flagged = int(combined['needs_human_review'].sum())
                        st.success(f"Done — Apify + AI completed. {len(combined)} rows · {passed} AI tagged · {flagged} flagged for review.")
                        st.balloons()
                    else:
                        st.warning("No rows were returned/tagged. Check Apify run status or try one track first.")
            else:
                st.warning("No TikTok links detected in the original report.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class='info-banner'>
        Manual JSON upload is still available below as a fallback if Apify API mode fails or you want to test downloaded JSON files.
    </div>
    """, unsafe_allow_html=True)

    # ── Step 1: Upload mode toggle + uploader ──────────────
    st.markdown("""
    <div class='section-card' style='margin-bottom:16px'>
        <h3>Step 1 — Upload JSON Files</h3>
        <p style='font-size:13px;color:#64748b;margin:0 0 14px'>
            Use <strong>Apify TikTok Scraper</strong> JSON exports. Each file = one track.
            Enable the Apify video download add-on before scraping so
            <code style='background:#f1f5f9;padding:1px 5px;border-radius:4px'>mediaUrls</code> or
            <code style='background:#f1f5f9;padding:1px 5px;border-radius:4px'>videoMeta.downloadAddr</code> is present.
        </p>
    """, unsafe_allow_html=True)

    upload_mode = st.radio(
        "Upload mode",
        ["Single file (one track)", "Multiple files (batch)"],
        horizontal=True,
        label_visibility="collapsed",
        key="upload_mode"
    )
    accept_multiple = (upload_mode == "Multiple files (batch)")

    st.markdown("""
    <style>
    /* Collapse the gap Streamlit puts between radio and uploader */
    div[data-testid="stFileUploaderDropzone"] { margin-top: 4px; }
    </style>
    """, unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "upload_zone",
        type=['json'],
        accept_multiple_files=accept_multiple,
        label_visibility="collapsed",
        key=f"file_uploader_{st.session_state.uploader_version}"
    )
    st.markdown("</div>", unsafe_allow_html=True)   # close section-card

    # Normalise to list
    if uploaded_files is None:
        uploaded_files = []
    elif not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]

    # ── Parse newly uploaded files into session state ──────
    # This runs only when new files are dropped; after a rerun the
    # staged_files list in session state keeps the data alive even
    # after the file_uploader widget clears.
    if uploaded_files:
        existing_names = {s['name'] for s in st.session_state.staged_files}
        for f in uploaded_files:
            if f.name not in existing_names:
                try:
                    f.seek(0)
                    raw = json.load(f)
                    records = raw if isinstance(raw, list) else raw.get('items', [raw])
                    df_tmp = pd.json_normalize(records)
                    market = df_tmp['locationCreated'].iloc[0] if 'locationCreated' in df_tmp.columns else 'UNKNOWN'
                    has_media    = 'mediaUrls' in df_tmp.columns and df_tmp['mediaUrls'].apply(lambda x: isinstance(x, list) and len(x) > 0).any()
                    has_download = 'videoMeta.downloadAddr' in df_tmp.columns and df_tmp['videoMeta.downloadAddr'].fillna('').astype(str).ne('').any()
                    has_video    = bool(has_media or has_download)
                    st.session_state.staged_files.append({
                        'name': f.name,
                        'records': records,
                        'track': '',
                        'market': market,
                        'has_video': has_video,
                        'tagged': False,
                    })
                    # Store raw records keyed by post ID for review page lookups
                    for rec in records:
                        rid = str(rec.get('id', ''))
                        if rid:
                            st.session_state.raw_records[rid] = rec
                except Exception as e:
                    st.error(f"Could not read {f.name}: {e}")

    staged = st.session_state.staged_files

    if not staged:
        st.markdown("""
        <div class='workflow-strip'>
            <div class='workflow-step'><strong>1. Upload</strong>Apify JSON file(s)</div>
            <div class='workflow-step'><strong>2. Name</strong>One track per file</div>
            <div class='workflow-step'><strong>3. Check</strong>Video links detected</div>
            <div class='workflow-step'><strong>4. Run</strong>Cover first, frames if needed</div>
            <div class='workflow-step'><strong>5. Review</strong>Fix any flagged rows</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # ── Step 2: File table (reads from session state) ──────
    st.markdown("""
    <div class='section-card'>
        <h3>Step 2 — Name Each Track</h3>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class='file-row header'>
        <div>File</div><div>Track Name</div><div>Market</div><div>Posts</div><div>Status</div><div></div>
    </div>
    """, unsafe_allow_html=True)

    file_configs = []
    remove_name = None
    for i, staged_f in enumerate(staged):
        is_tagged = staged_f.get('tagged', False)
        if is_tagged:
            status_label = "✓ Tagged"
            status_class = "status-ok"
        elif staged_f['has_video']:
            status_label = "Ready"
            status_class = "status-ok"
        else:
            status_label = "No video links"
            status_class = "status-warn"

        cols = st.columns([2.2, 2.3, 1.0, 0.8, 1.2, 0.4])
        with cols[0]:
            opacity = "opacity:0.5;" if is_tagged else ""
            st.markdown(f"<div class='file-name' style='padding:6px 0;{opacity}'>{staged_f['name']}</div>", unsafe_allow_html=True)
        with cols[1]:
            if is_tagged:
                st.markdown(f"<div class='small-muted' style='padding:8px 0;opacity:0.6'>{staged_f['track']}</div>", unsafe_allow_html=True)
            else:
                track_name = st.text_input(
                    f"track_{i}",
                    value=staged_f['track'],
                    placeholder="e.g. Bruno Mars - Risk It All",
                    key=f"track_{i}",
                    label_visibility="collapsed"
                )
                st.session_state.staged_files[i]['track'] = track_name
        with cols[2]:
            st.markdown(f"<div class='small-muted' style='padding:8px 0'>{staged_f['market']}</div>", unsafe_allow_html=True)
        with cols[3]:
            st.markdown(f"<div class='small-muted' style='padding:8px 0'>{len(staged_f['records'])}</div>", unsafe_allow_html=True)
        with cols[4]:
            st.markdown(f"<span class='status-pill {status_class}'>{status_label}</span>", unsafe_allow_html=True)
        with cols[5]:
            if not is_tagged:
                if st.button("✕", key=f"remove_file_{staged_f['name']}", help="Remove this file"):
                    remove_name = staged_f['name']

        if not is_tagged:
            track_name = st.session_state.staged_files[i]['track']
            file_configs.append({
                'records': staged_f['records'],
                'track': track_name,
                'n': len(staged_f['records']),
                'market': staged_f['market'],
                'has_video': staged_f['has_video'],
                'name': staged_f['name'],
                'staged_idx': i,
            })

    if remove_name is not None:
        removed_files = [f for f in st.session_state.staged_files if f['name'] == remove_name]
        if removed_files:
            for rec in removed_files[0].get('records', []):
                rid = str(rec.get('id', ''))
                if rid:
                    st.session_state.raw_records.pop(rid, None)
        st.session_state.staged_files = [
            f for f in st.session_state.staged_files
            if f['name'] != remove_name
        ]
        st.session_state.uploader_version += 1
        st.rerun()

    already_tagged = sum(1 for s in staged if s.get('tagged', False))
    untagged_count = len(staged) - already_tagged

    btn_c1, btn_c2 = st.columns([2, 1])
    with btn_c1:
        if already_tagged:
            st.markdown(
                f"<div style='font-size:12px;color:#059669;padding:6px 0'>"
                f"✓ {already_tagged} file(s) already tagged — won't be re-run. "
                f"{untagged_count} new file(s) queued.</div>",
                unsafe_allow_html=True
            )
    with btn_c2:
        if st.button("✕ Clear all files", key="clear_staged"):
            st.session_state.staged_files = []
            st.session_state.uploader_version += 1
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)  # close section-card

    # ── Step 3: Run settings ───────────────────────────────
    if not file_configs:
        st.markdown("""
        <div class='info-banner'>
            ✓ All uploaded files have already been tagged. Upload a new JSON above to tag more tracks.
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    st.markdown("<div class='section-card'><h3>Step 3 — Run Settings</h3>", unsafe_allow_html=True)

    # Batch mode selector (only useful for multi-file uploads)
    if len(file_configs) > 1:
        mode_options = ["Process all uploaded files", "Process one selected file"]
        process_mode = st.radio(
            "Processing scope",
            mode_options,
            horizontal=True,
        )
        if process_mode == "Process one selected file":
            selectable = [
                f"{i+1}. {c['track'] or '(unnamed)'} — {c['market']} — {c['n']} posts"
                for i, c in enumerate(file_configs)
            ]
            selected_label = st.selectbox("Select file to process", selectable)
            run_configs = [file_configs[selectable.index(selected_label)]]
        else:
            run_configs = file_configs
    else:
        process_mode = "Process all uploaded files"
        run_configs  = file_configs

    total_posts  = sum(c['n'] for c in run_configs)
    video_ready  = sum(1 for c in run_configs if c['has_video'])
    selected_named    = all(c['track'].strip() for c in run_configs)
    selected_readable = all(c['market'] != 'ERROR' and c['n'] > 0 for c in run_configs)

    # Recolour the slider thumb/track to indigo so it matches the app theme
    st.markdown("""
    <style>
    [data-testid="stSlider"] > div > div > div > div { background: #4f46e5 !important; }
    [data-testid="stSlider"] > div > div > div > div > div { background: #4f46e5 !important; border-color: #4f46e5 !important; }
    [data-testid="stSlider"] [role="slider"] { background: #4f46e5 !important; border-color: #4f46e5 !important; box-shadow: 0 0 0 4px #eef2ff !important; }
    </style>
    """, unsafe_allow_html=True)

    col_delay, col_summary = st.columns([1.3, 2.7], gap="large")
    with col_delay:
        st.markdown("<p style='font-size:12px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px'>API Delay (seconds)</p>", unsafe_allow_html=True)
        delay = st.slider(
            "delay_slider", 0, 10, 1,
            label_visibility="collapsed",
            help="Free tier: use 5–10 s · Paid quota: 1–2 s"
        )
        tier_hint = "🐢 Free tier — consider 5–10 s" if delay < 3 else "✓ Good for paid quota"
        st.caption(tier_hint)
    with col_summary:
        est_min = max(1, int(total_posts * (delay + 2) / 60))
        st.markdown(f"""
        <div class='run-panel'>
            <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:10px'>
                <div><div class='big'>{len(run_configs)}</div><div class='label'>Files</div></div>
                <div><div class='big'>{total_posts}</div><div class='label'>Posts</div></div>
                <div><div class='big'>{video_ready}/{len(run_configs)}</div><div class='label'>Video Links</div></div>
                <div><div class='big'>~{est_min}m</div><div class='label'>Est. Time</div></div>
            </div>
            <div class='small-muted'>Tier 0V: visual-only for vague captions · Tier 1: cover image · Tier 2A: 3 frames · Tier 2B: adaptive 9-frame refinement</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)  # close section-card

    # Warnings
    if not selected_named:
        st.markdown("<div class='warn-banner'>⚠️ Enter a track name for every file before running.</div>", unsafe_allow_html=True)
    if video_ready < len(run_configs):
        st.markdown("<div class='warn-banner'>⚠️ One or more files have no video links — frame tagging (Tier 2) won't be available for those rows.</div>", unsafe_allow_html=True)

    run_label = "▶  Run All Files" if len(run_configs) > 1 else "▶  Run"
    if st.button(run_label, type="primary", disabled=(not selected_named or not selected_readable), use_container_width=True):
        all_results = []

        # ── Live progress UI ────────────────────────────────
        st.markdown("""
        <style>
        .live-row {
            display: grid;
            grid-template-columns: 36px 1fr 90px 90px 80px;
            gap: 10px;
            align-items: center;
            padding: 7px 12px;
            border-radius: 7px;
            font-size: 13px;
            margin-bottom: 3px;
            background: white;
            border: 1px solid #e2e8f0;
        }
        .live-row .row-num { color: #94a3b8; font-size: 11px; font-weight: 700; text-align: right; }
        .live-row .row-caption { color: #334155; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .live-row .row-narrative { color: #4f46e5; font-weight: 600; font-size: 12px; }
        .live-row .row-tier { color: #64748b; font-size: 11px; }
        .live-row .row-status-pass { color: #059669; font-weight: 700; font-size: 11px; }
        .live-row .row-status-review { color: #d97706; font-weight: 700; font-size: 11px; }
        .live-header {
            display: grid;
            grid-template-columns: 36px 1fr 90px 90px 80px;
            gap: 10px;
            padding: 6px 12px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            color: #94a3b8;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 4px;
        }
        </style>
        """, unsafe_allow_html=True)

        progress_bar  = st.progress(0)
        track_label   = st.empty()
        log_container = st.container()

        completed_rows_html = []
        log_placeholder     = log_container.empty()

        TIER_LABELS = {
            'tier0_skipped':        'Skipped',
            'tier0_visual_frames':  '0V Frames',
            'tier0_visual_cover':   '0V Cover',
            'tier1_cover':          'Cover',
            'tier2_frames':         'Frames',
            'tier3_human':          'Human',
        }

        def render_log(rows_html, current_label=""):
            header = "<div class='live-header'><div>#</div><div>Caption</div><div>Narrative</div><div>Tier</div><div>Status</div></div>"
            current = f"<div class='live-row' style='background:#eef2ff;border-color:#818cf8'><div class='row-num'>⏳</div><div class='row-caption' style='color:#4f46e5'>{current_label}</div><div></div><div></div><div></div></div>" if current_label else ""
            log_placeholder.markdown(
                f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px;margin-top:8px'>"
                f"{header}{''.join(rows_html)}{current}</div>",
                unsafe_allow_html=True
            )

        for batch_i, config in enumerate(run_configs):
            total_in_batch = config['n']
            track_label.markdown(
                f"<div class='info-banner' style='margin-top:8px'>Processing <strong>{config['track']}</strong> "
                f"— {batch_i+1} of {len(run_configs)} file(s) · {total_in_batch} posts</div>",
                unsafe_allow_html=True
            )
            completed_rows_html = []
            render_log(completed_rows_html, "Starting…")

            records  = config['records']   # already parsed into session state
            log_list = []

            def on_row_done(row_num, total, out, tier_used):
                caption   = str(out.get('caption', ''))[:45] + ('…' if len(str(out.get('caption',''))) > 45 else '')
                narrative = out.get('Narrative') or '—'
                tier      = TIER_LABELS.get(tier_used, tier_used)
                status    = out.get('validation_status', 'review')
                conf      = out.get('confidence', 0)
                status_cls = 'row-status-pass' if status == 'pass' else 'row-status-review'
                status_txt = f"✓ {conf:.0%}" if status == 'pass' else f"⚠ Review"
                completed_rows_html.append(
                    f"<div class='live-row'>"
                    f"<div class='row-num'>{row_num}</div>"
                    f"<div class='row-caption'>{caption or '(no caption)'}</div>"
                    f"<div class='row-narrative'>{narrative}</div>"
                    f"<div class='row-tier'>{tier}</div>"
                    f"<div class='{status_cls}'>{status_txt}</div>"
                    f"</div>"
                )
                next_label = f"Processing {row_num + 1} of {total}…" if row_num < total else ""
                render_log(completed_rows_html, next_label)
                # Update overall progress bar
                overall = (batch_i + (row_num / total)) / len(run_configs)
                progress_bar.progress(min(overall, 1.0))

            result_df = run_pipeline(
                records, config['track'],
                st.session_state.gemini_key,
                st.session_state.apify_token,
                log_list,
                delay_seconds=delay,
                on_row_done=on_row_done,
                source_file=config.get('name', '')
            )
            all_results.append(result_df)

        progress_bar.progress(1.0)
        track_label.empty()
        log_placeholder.empty()
        combined = pd.concat(all_results, ignore_index=True)
        combined = _apply_original_market_to_results(combined)

        # Mark processed staged files as tagged so they won't re-run
        processed_names = {c['name'] for c in run_configs}
        for i, sf in enumerate(st.session_state.staged_files):
            if sf['name'] in processed_names:
                st.session_state.staged_files[i]['tagged'] = True

        if st.session_state.master_df.empty:
            st.session_state.master_df = combined.copy()
        else:
            existing_ids = set(st.session_state.master_df['id'].astype(str))
            new_rows = combined[~combined['id'].astype(str).isin(existing_ids)]
            st.session_state.master_df = pd.concat(
                [st.session_state.master_df, new_rows], ignore_index=True
            )

        # Persist tagged results explicitly. Streamlit reruns when switching pages,
        # so Review Flagged must read from session_state, not upload-page locals.
        st.session_state.master_df = _apply_original_market_to_results(st.session_state.master_df)
        st.session_state.has_tagged_results = True
        st.session_state.review_idx = 0

        passed  = (combined['validation_status'] == 'pass').sum()
        flagged = int(combined['needs_human_review'].sum())
        st.success(f"Done — {passed} AI tagged · {flagged} flagged for review across {len(run_configs)} track(s).")
        st.balloons()

        st.markdown("<div class='section-card'><h3>Results by Track</h3>", unsafe_allow_html=True)
        summary = combined.groupby('track').agg(
            Posts=('id','count'),
            AI_Tagged=('validation_status', lambda x: (x=='pass').sum()),
            Flagged=('needs_human_review','sum'),
            Avg_Conf=('confidence','mean')
        ).reset_index()
        summary['Automation %'] = (summary['AI_Tagged']/summary['Posts']*100).round(1).astype(str)+'%'
        summary['Avg_Conf']     = summary['Avg_Conf'].apply(lambda x: f'{x:.0%}')
        st.dataframe(summary, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'><h3>Full Results</h3>", unsafe_allow_html=True)
        show = [c for c in ['market','track','creator','caption','tiktok_url','plays','likes','shares','saves','comments',
                            'Narrative','Creative Type','Content Details','confidence',
                            'tier_used','needs_human_review'] if c in combined.columns]
        st.dataframe(combined[show], use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# REVIEW FLAGGED
# ══════════════════════════════════════════════════════════
elif page == "Review Flagged":
    st.markdown("""
    <div class='page-header'>
        <h1>Review Flagged Posts</h1>
        <p>Manually tag posts the AI couldn't handle with sufficient confidence</p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.master_df.empty:
        st.info("No data loaded. Go to Upload & Tag first.")
        st.stop()

    # Repair metadata for ALL rows before computing flagged/pending.
    # This makes every pending item use the uploaded JSON as the source of truth.
    _repair_review_metadata_in_master_df()

    df      = st.session_state.master_df
    # Pending review should include ALL rows still marked needs_human_review, even if Gemini filled a weak Narrative.
    pending = df[(df['needs_human_review'] == True) & (df.get('review_action', pd.Series([''] * len(df), index=df.index)).fillna('') != 'REMOVE')].copy()
    # Reviewed rows are rows manually saved in this page. They are no longer pending, but should still count as reviewed.
    done = df[df.get('tier_used', pd.Series([''] * len(df), index=df.index)).fillna('').isin(['tier3_human', 'removed'])].copy()
    total_flagged_ever = len(pending) + len(done)

    st.markdown(f"""
    <div class='metric-row'>
        <div class='metric-card'><div class='val amber'>{total_flagged_ever}</div><div class='lbl'>Total Flagged</div></div>
        <div class='metric-card'><div class='val green'>{len(done)}</div><div class='lbl'>Reviewed</div></div>
        <div class='metric-card'><div class='val'>{len(pending)}</div><div class='lbl'>Pending</div></div>
    </div>
    """, unsafe_allow_html=True)

    if len(pending) == 0:
        st.success("All flagged posts have been reviewed.")
        st.stop()

    # clamp index
    idx = st.session_state.review_idx % len(pending)
    row = pending.iloc[idx]

    # progress + navigation controls
    progress_pct = idx / len(pending) if len(pending) > 1 else 1.0
    st.progress(progress_pct)

    nav_col1, nav_col2, nav_col3 = st.columns([1, 6, 1])
    with nav_col1:
        if st.button("← Previous", disabled=(idx == 0)):
            st.session_state.review_idx = max(0, st.session_state.review_idx - 1)
            st.rerun()
    with nav_col2:
        st.markdown(f"<p style='text-align:center;color:#64748b;font-size:13px;margin:6px 0'>Row {idx+1} of {len(pending)}</p>", unsafe_allow_html=True)
    with nav_col3:
        if st.button("Skip →"):
            st.session_state.review_idx += 1
            st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.4, 1.6], gap="large")

    import math as _math
    def _safe_int(val, default=0):
        # int(float(v)) handles pandas float-cast integers (e.g. 12345.0)
        try:
            if val is None: return default
            if isinstance(val, float) and _math.isnan(val): return default
            return int(float(val))
        except (ValueError, TypeError):
            return default
    def _safe_str(val):
        if val is None: return ''
        if isinstance(val, float) and _math.isnan(val): return ''
        return str(val).strip()

    # Look up the original uploaded JSON record by post ID.
    # This fixes the issue where the first flagged row shows metrics/link,
    # but the second flagged row falls back to 0/no URL.
    row_id = _norm_post_id(row.get('id', ''))
    raw_idx = rebuild_raw_records_index()
    raw_rec = raw_idx.get(row_id, {})

    # Strong fallback: find the exact original JSON row using source_file + source_row_num.
    # This handles every flagged item, even when ID lookup fails or Streamlit reruns after Save & Next.
    if not raw_rec:
        try:
            sf_name = _safe_str(row.get('source_file', ''))
            rn = _safe_int(row.get('source_row_num'), -1)
            for sf in st.session_state.get('staged_files', []):
                if _safe_str(sf.get('name', '')) == sf_name and 0 <= rn < len(sf.get('records', [])):
                    candidate = sf.get('records', [])[rn]
                    if isinstance(candidate, dict):
                        raw_rec = candidate
                        break
        except Exception:
            raw_rec = {}

    # Last fallback: search all uploaded JSON records by public TikTok URL if present.
    if not raw_rec:
        current_url = _safe_str(row.get('tiktok_url', ''))
        if current_url:
            for sf in st.session_state.get('staged_files', []):
                for candidate in sf.get('records', []):
                    if isinstance(candidate, dict) and current_url in [_safe_str(candidate.get('webVideoUrl')), _safe_str(candidate.get('submittedVideoUrl'))]:
                        raw_rec = candidate
                        break
                if raw_rec:
                    break

    # Extra fallback: v16 stores the key fields in master_df, but some rows can still
    # lose raw metadata after reruns. Use the embedded normalized source row too.
    embedded_raw = {}
    try:
        raw_json_val = _safe_str(row.get('_raw_row_json', ''))
        if raw_json_val:
            embedded_raw = json.loads(raw_json_val)
    except Exception:
        embedded_raw = {}

    def _nested_video_meta(src, key):
        vm = src.get('videoMeta', {}) if isinstance(src, dict) else {}
        if isinstance(vm, dict):
            return vm.get(key, '')
        return ''

    plays  = _safe_int(row.get('plays')  or embedded_raw.get('playCount')  or raw_rec.get('playCount')  or 0)
    likes  = _safe_int(row.get('likes')  or embedded_raw.get('diggCount')  or raw_rec.get('diggCount')  or 0)
    shares = _safe_int(row.get('shares') or embedded_raw.get('shareCount') or raw_rec.get('shareCount') or 0)
    saves  = _safe_int(row.get('saves')  or embedded_raw.get('collectCount') or raw_rec.get('collectCount') or 0)
    comments = _safe_int(row.get('comments') or embedded_raw.get('commentCount') or raw_rec.get('commentCount') or 0)
    reason = _safe_str(row.get('tier3_reason', '')) or _safe_str(row.get('validation_issues', '')) or 'unknown'

    # Public URL for opening TikTok. Do NOT use video_url here; that is an Apify download link.
    url = (
        _safe_str(row.get('tiktok_url'))
        or _safe_str(embedded_raw.get('webVideoUrl'))
        or _safe_str(embedded_raw.get('submittedVideoUrl'))
        or _safe_str(raw_rec.get('webVideoUrl'))
        or _safe_str(raw_rec.get('submittedVideoUrl'))
        or _safe_str(row.get('webVideoUrl'))
        or ''
    )
    # Cover image: use stored output first, then raw JSON fallback.
    cover_url = (
        _safe_str(row.get('cover_url'))
        or _safe_str(embedded_raw.get('videoMeta.originalCoverUrl'))
        or _safe_str(embedded_raw.get('videoMeta.coverUrl'))
        or _safe_str(_nested_video_meta(embedded_raw, 'originalCoverUrl'))
        or _safe_str(_nested_video_meta(embedded_raw, 'coverUrl'))
        or _safe_str(raw_rec.get('videoMeta', {}).get('originalCoverUrl', '') if isinstance(raw_rec.get('videoMeta'), dict) else '')
        or _safe_str(raw_rec.get('videoMeta', {}).get('coverUrl', '') if isinstance(raw_rec.get('videoMeta'), dict) else '')
        or _safe_str(row.get('videoMeta.originalCoverUrl'))
        or _safe_str(row.get('videoMeta.coverUrl'))
        or ''
    )
    # ── Col 1: Cover image ─────────────────────────────────
    with col1:
        if cover_url:
            try:
                st.image(cover_url, use_container_width=True)
            except Exception:
                st.markdown("""
                <div style='background:#f1f5f9;border-radius:10px;height:280px;
                display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:13px'>
                ⚠ Cover unavailable</div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style='background:#f1f5f9;border-radius:10px;height:280px;
            display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:13px'>
            No cover image</div>""", unsafe_allow_html=True)
        if url:
            st.link_button("▶ Watch on TikTok", url, use_container_width=True)
        else:
            st.markdown("<p style='font-size:11px;color:#94a3b8;text-align:center;margin-top:6px'>No TikTok URL available</p>", unsafe_allow_html=True)

    # ── Col 2: Post metadata ───────────────────────────────
    import html as _html
    def _e(v): return _html.escape(str(v)) if v and not (isinstance(v, float) and _math.isnan(v)) else ''

    _handle  = _e(row.get('creator_handle', ''))
    _display = _e(row.get('creator_display', ''))
    _creator = _e(row.get('creator', '—'))
    _market  = _e(row.get('market', '—'))
    _track   = _e(row.get('track', '—'))
    _caption = _e(row.get('caption', '') or '(empty)')
    _reason  = _e(reason or 'Unknown')

    _creator_html = (
        f"@{_handle}"
        + (f'<span style="color:#64748b;font-size:12px"> · {_display}</span>'
           if _display and _display != _handle else '')
    ) if _handle else _creator

    with col2:
        st.markdown(f"""
        <div class='post-card'>
            <div class='label'>Creator</div>
            <div class='value'>{_creator_html}</div>
            <div class='label'>Market &nbsp;·&nbsp; Track</div>
            <div class='value'>{_market} &nbsp;·&nbsp; {_track}</div>
            <div class='label'>Caption</div>
            <div class='value' style='white-space:pre-wrap'>{_caption}</div>
            <hr class='divider'>
            <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px'>
                <div><div style='font-size:16px;font-weight:800;color:#1e1b4b'>{plays:,}</div><div style='font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Plays</div></div>
                <div><div style='font-size:16px;font-weight:800;color:#1e1b4b'>{likes:,}</div><div style='font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Likes</div></div>
                <div><div style='font-size:16px;font-weight:800;color:#1e1b4b'>{shares:,}</div><div style='font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.05em'>Shares</div></div>
            </div>
            <div class='label'>Flagged reason</div>
            <div style='font-size:13px;color:#b45309;font-weight:500'>{_reason}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <style>
        /* Force all widget labels on this page to be dark and visible */
        [data-testid="stWidgetLabel"] > label,
        [data-testid="stWidgetLabel"] p,
        .stSelectbox label, .stMultiSelect label, .stTextArea label {
            color: #1e293b !important;
            font-size: 12px !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: .05em !important;
        }
        /* Light background on inputs */
        [data-testid="stSelectbox"] > div > div,
        [data-testid="stMultiSelect"] > div > div {
            background: white !important;
            border: 1px solid #e2e8f0 !important;
            color: #1e293b !important;
        }
        [data-testid="stTextArea"] textarea {
            background: white !important;
            border: 1px solid #e2e8f0 !important;
            color: #1e293b !important;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown("<div class='section-card'><h3>Review Action</h3>", unsafe_allow_html=True)
        row_error_code = _safe_str(embedded_raw.get('errorCode')) or _safe_str(raw_rec.get('errorCode')) or _safe_str(row.get('validation_issues', ''))
        default_action = "Remove / Ignore from final export" if "POST_NOT_FOUND" in row_error_code or "PRIVATE" in row_error_code.upper() else "Keep & Tag"
        action_key = f"review_action_choice_{row_id}"
        if action_key not in st.session_state:
            st.session_state[action_key] = default_action

        st.markdown("""
        <div style='font-size:11px;color:#64748b;font-weight:800;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px'>
            What should happen to this post?
        </div>
        """, unsafe_allow_html=True)

        act_col1, act_col2 = st.columns(2, gap="small")
        with act_col1:
            if st.button("✅ Keep & Tag", key=f"keep_action_{row_id}", use_container_width=True,
                         type="primary" if st.session_state[action_key] == "Keep & Tag" else "secondary"):
                st.session_state[action_key] = "Keep & Tag"
                st.rerun()
        with act_col2:
            if st.button("🗑️ Remove / Ignore", key=f"remove_action_{row_id}", use_container_width=True,
                         type="primary" if st.session_state[action_key] == "Remove / Ignore from final export" else "secondary"):
                st.session_state[action_key] = "Remove / Ignore from final export"
                st.rerun()

        review_action = st.session_state[action_key]

        if review_action == "Remove / Ignore from final export":
            st.markdown(
                "<div class='warn-banner'>This post will be excluded from the final export. Use this for deleted, private, unavailable, or wrong-link posts.</div>",
                unsafe_allow_html=True
            )
            remove_reason = st.text_input(
                "Removal reason",
                value=row_error_code or "Post unavailable / not found",
                key=f"remove_reason_{row_id}"
            )
            if st.button("Confirm Remove & Next", type="primary", use_container_width=True, key=f"remove_btn_{row_id}"):
                mid = st.session_state.master_df[st.session_state.master_df['id'] == row['id']].index[0]
                st.session_state.master_df.at[mid, 'review_action'] = 'REMOVE'
                st.session_state.master_df.at[mid, 'remove_reason'] = remove_reason
                st.session_state.master_df.at[mid, 'needs_human_review'] = False
                st.session_state.master_df.at[mid, 'tier_used'] = 'removed'
                st.session_state.review_idx = 0
                if action_key in st.session_state:
                    del st.session_state[action_key]
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            st.stop()

        st.markdown(
            "<div class='info-banner'>Selected action: <strong>Keep & Tag</strong>. Fill the tags below, then save.</div>",
            unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'><h3>Fill in the tags</h3>", unsafe_allow_html=True)

        # ── AI Suggest button ──────────────────────────────
        ai_suggest_key = f"ai_suggest_{row['id']}"
        ai_result_key  = f"ai_result_{row['id']}"

        if st.button("🤖 AI Suggest", use_container_width=True, key=ai_suggest_key,
                     help="Let Gemini analyse the cover image and video frames and pre-fill the tags"):
            from google.genai import types as gtypes_review
            gemini_key_r  = st.session_state.gemini_key
            apify_token_r = st.session_state.apify_token
            if not gemini_key_r:
                st.error("Enter your Gemini API key above first.")
            else:
                with st.spinner("Asking Gemini…"):
                    # Prefer the original TikTok scraper record because it contains hashtags, musicMeta, mediaUrls, etc.
                    source_row = raw_rec if raw_rec else (embedded_raw if embedded_raw else row)
                    suggest_prompt = build_prompt(source_row) + "\n\nNote: this post was flagged because the AI could not determine tags with sufficient confidence on the first pass. Look carefully at all visual evidence."
                    contents_suggest = [suggest_prompt]
                    # Try cover image
                    s_cover = get_cover_url(source_row) or row.get('cover_url', '')
                    if s_cover:
                        try:
                            img_b = download_image_bytes(s_cover, apify_token_r)
                            contents_suggest.append(gtypes_review.Part.from_bytes(data=img_b, mime_type='image/jpeg'))
                        except Exception:
                            pass
                    # Try video frames using raw Apify media URL, not the public TikTok link.
                    s_video = get_video_url(source_row) or row.get('video_url', '')
                    if s_video:
                        try:
                            with tempfile.TemporaryDirectory() as tmp:
                                video_path = os.path.join(tmp, f"review_{row['id']}.mp4")
                                download_video(s_video, video_path, apify_token_r)
                                frame_paths = extract_frames(video_path, os.path.join(tmp, 'frames'))
                                for fp in frame_paths:
                                    with open(fp, 'rb') as f:
                                        contents_suggest.append(gtypes_review.Part.from_bytes(data=f.read(), mime_type='image/jpeg'))
                        except Exception:
                            pass
                    suggest_result = call_gemini(contents_suggest, gemini_key_r)
                    suggest_result = apply_dance_guardrails(suggest_result, source_row)
                    st.session_state[ai_result_key] = suggest_result

        # Pre-fill defaults from AI suggestion if available
        ai_prefill = st.session_state.get(ai_result_key, {})
        prefill_narrative = ai_prefill.get('narrative', '') if ai_prefill and not ai_prefill.get('parse_error') else ''
        prefill_ct_raw    = ai_prefill.get('creative_type', []) if ai_prefill and not ai_prefill.get('parse_error') else []
        prefill_ct        = [x for x in prefill_ct_raw if x in ALLOWED_SET][:2]
        prefill_cd        = ai_prefill.get('content_details', '') if ai_prefill and not ai_prefill.get('parse_error') else ''

        if ai_prefill and not ai_prefill.get('parse_error'):
            conf_hint = ai_prefill.get('confidence', 0)
            reason_hint = ai_prefill.get('reasoning', '')
            st.markdown(
                f"<div class='info-banner' style='margin-bottom:10px'>🤖 AI suggestion: "
                f"<strong>{prefill_narrative}</strong> · "
                f"<strong>{', '.join(prefill_ct) or '—'}</strong> · "
                f"{conf_hint:.0%} confidence<br>"
                f"<span style='font-size:12px;color:#64748b'>{reason_hint}</span></div>",
                unsafe_allow_html=True
            )
        elif ai_prefill and ai_prefill.get('parse_error'):
            st.markdown("<div class='warn-banner'>⚠️ AI suggestion failed — fill in manually.</div>", unsafe_allow_html=True)

        # Resolve selectbox index for pre-fill.
        # Narrative supports two flexible options:
        # - Custom: show a text input and save what the reviewer types.
        # - Other: save the literal value "Other" without requiring typing.
        narr_options = [''] + NARRATIVE_OPTIONS
        if prefill_narrative in narr_options:
            narr_default = prefill_narrative
        elif prefill_narrative:
            narr_default = 'Custom'
        else:
            narr_default = ''
        narr_idx = narr_options.index(narr_default) if narr_default in narr_options else 0

        narrative_choice = st.selectbox("Narrative", narr_options, index=narr_idx, key=f"review_narrative_{row_id}")
        custom_narrative_value = ''
        if narrative_choice == 'Custom':
            custom_narrative_value = st.text_input(
                "Type custom narrative",
                value=(prefill_narrative if prefill_narrative and prefill_narrative not in NARRATIVE_OPTIONS else ''),
                key=f"review_narrative_custom_{row_id}"
            ).strip()
            narrative = custom_narrative_value
        else:
            narrative = narrative_choice

        creative_type   = st.multiselect("Creative Type (max 2)", ALLOWED_CREATIVE_TYPES,
                                         default=prefill_ct, max_selections=2, key=f"review_ct_{row_id}")
        content_details = st.text_area("Content Details",
                                       value=prefill_cd,
                                       placeholder="Describe what happens in the video and its visual aesthetic...",
                                       height=120, key=f"review_details_{row_id}")

        # If market is unknown in the reviewed row, let the reviewer fill it here.
        current_market = _safe_str(row.get('market', ''))
        market_unknown = current_market.lower() in ['', 'unknown', 'nan', 'none', '—', '-']
        final_market = current_market
        market_custom_value = ''
        if market_unknown:
            st.markdown(
                "<div class='warn-banner'>⚠️ Market is unknown for this row. Please select or type the market before saving.</div>",
                unsafe_allow_html=True
            )
            market_options = ['', 'MY', 'PH', 'ID', 'SG', 'TH', 'VN', 'KR', 'TW', 'JP', 'Other']
            market_choice = st.selectbox("Market", market_options, index=0, key=f"review_market_{row_id}")
            if market_choice == 'Other':
                market_custom_value = st.text_input(
                    "Type market",
                    key=f"review_market_custom_{row_id}"
                ).strip().upper()
                final_market = market_custom_value
            else:
                final_market = market_choice


        # If the scraper returned a URL-only/error row, metrics may be missing.
        # Let the reviewer fill the engagement numbers manually from TikTok.
        needs_manual_metrics = (
            str(row.get('tier_used', '')).strip() == 'scraper_exception'
            or bool(row.get('manual_metrics_required', False))
            or (plays == 0 and likes == 0 and shares == 0 and comments == 0)
        )
        manual_plays = plays
        manual_likes = likes
        manual_shares = shares
        manual_saves = saves
        manual_comments = comments
        if needs_manual_metrics:
            st.markdown(
                "<div class='warn-banner'>⚠️ Metrics were not captured by the scraper. Open the TikTok link and fill them manually before saving.</div>",
                unsafe_allow_html=True
            )
            mc1, mc2 = st.columns(2)
            with mc1:
                manual_plays = st.number_input("Plays", min_value=0, value=int(plays), step=1, key=f"manual_plays_{row_id}")
                manual_likes = st.number_input("Likes", min_value=0, value=int(likes), step=1, key=f"manual_likes_{row_id}")
                manual_comments = st.number_input("Comments", min_value=0, value=int(comments), step=1, key=f"manual_comments_{row_id}")
            with mc2:
                manual_shares = st.number_input("Shares", min_value=0, value=int(shares), step=1, key=f"manual_shares_{row_id}")
                manual_saves = st.number_input("Saves", min_value=0, value=int(saves), step=1, key=f"manual_saves_{row_id}")

        if st.button("Save & Next", type="primary", use_container_width=True):
            if narrative_choice == 'Custom' and not custom_narrative_value:
                st.error("Please type a custom narrative, or choose Other/NA if you do not want to type one.")
            elif market_unknown and not final_market:
                st.error("Please select or type the market before saving.")
            elif not narrative or not creative_type or not content_details:
                st.error("Please fill in all three tag fields before saving.")
            elif needs_manual_metrics and int(manual_plays) == 0 and int(manual_likes) == 0 and int(manual_shares) == 0:
                st.error("Please fill in the TikTok metrics, or confirm the post truly has 0 plays, 0 likes, and 0 shares.")
            else:
                mid = st.session_state.master_df[
                    st.session_state.master_df['id'] == row['id']
                ].index[0]
                st.session_state.master_df.at[mid, 'Narrative']          = narrative
                st.session_state.master_df.at[mid, 'Creative Type']      = ', '.join(creative_type)
                st.session_state.master_df.at[mid, 'Content Details']    = content_details
                if final_market:
                    st.session_state.master_df.at[mid, 'market'] = final_market
                st.session_state.master_df.at[mid, 'plays']              = int(manual_plays)
                st.session_state.master_df.at[mid, 'likes']              = int(manual_likes)
                st.session_state.master_df.at[mid, 'shares']             = int(manual_shares)
                st.session_state.master_df.at[mid, 'saves']              = int(manual_saves)
                st.session_state.master_df.at[mid, 'comments']           = int(manual_comments)
                st.session_state.master_df.at[mid, 'review_action']      = 'KEEP'
                st.session_state.master_df.at[mid, 'needs_human_review'] = False
                st.session_state.master_df.at[mid, 'tier_used']          = 'tier3_human'
                st.session_state.review_idx = 0
                # Clear AI suggestion state for this row
                if ai_result_key in st.session_state:
                    del st.session_state[ai_result_key]
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════
elif page == "Summary":
    import plotly.express as px
    import plotly.graph_objects as go

    st.markdown("""
    <div class='page-header'>
        <h1>Dashboard</h1>
        <p>Performance overview across markets, tracks, narratives and creative types</p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.master_df.empty:
        st.info("No data loaded yet.")
        st.stop()

    df = st.session_state.master_df

    # ── Filters ───────────────────────────────────────────
    with st.expander("Filters", expanded=False):
        fc1, fc2 = st.columns(2)
        markets = ["All"] + sorted(df['market'].dropna().unique().tolist())
        tracks  = ["All"] + sorted(df['track'].dropna().unique().tolist())
        sel_mkt = fc1.selectbox("Market", markets)
        sel_trk = fc2.selectbox("Track",  tracks)

    dff = df.copy()
    if sel_mkt != "All":
        dff = dff[dff['market'] == sel_mkt]
    if sel_trk != "All":
        dff = dff[dff['track'] == sel_trk]

    total     = len(dff)
    ai_tagged = int((dff['validation_status'] == 'pass').sum())
    flagged   = int(dff['needs_human_review'].sum())
    avg_conf  = dff[dff['confidence'] > 0]['confidence'].mean() if total else 0
    tot_plays  = int(dff['plays'].sum()) if 'plays' in dff.columns else 0
    tot_likes  = int(dff['likes'].sum()) if 'likes' in dff.columns else 0
    avg_plays  = int(tot_plays / total) if total else 0

    # ── KPI row ───────────────────────────────────────────
    st.markdown(f"""
    <div class='metric-row'>
        <div class='metric-card'><div class='val'>{total}</div><div class='lbl'>Total Posts</div></div>
        <div class='metric-card'><div class='val green'>{ai_tagged}</div><div class='lbl'>AI Tagged</div></div>
        <div class='metric-card'><div class='val indigo'>{int(ai_tagged/total*100) if total else 0}%</div><div class='lbl'>Automation Rate</div></div>
        <div class='metric-card'><div class='val amber'>{flagged}</div><div class='lbl'>Need Review</div></div>
        <div class='metric-card'><div class='val'>{avg_conf:.0%}</div><div class='lbl'>Avg Confidence</div></div>
        <div class='metric-card'><div class='val'>{tot_plays:,}</div><div class='lbl'>Total Plays</div></div>
        <div class='metric-card'><div class='val'>{avg_plays:,}</div><div class='lbl'>Avg Plays / Post</div></div>
    </div>
    """, unsafe_allow_html=True)

    INDIGO_PALETTE = ['#4f46e5','#818cf8','#6366f1','#a5b4fc','#3730a3','#c7d2fe','#312e81','#e0e7ff']
    MARKET_COLORS = {
        'MY': '#2563EB',
        'PH': '#F59E0B',
        'SG': '#10B981',
        'TH': '#EF4444',
        'VN': '#8B5CF6',
        'KR': '#EC4899',
        'ID': '#14B8A6',
        'UNKNOWN': '#64748B',
    }

    # ── Market / Country Overview ──────────────────────────
    st.markdown("<div class='section-card'><h3>Market / Country Overview</h3>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:13px;color:#64748b;margin:-8px 0 14px'>High-level comparison by market: scale, engagement, automation rate, and dominant content themes.</p>", unsafe_allow_html=True)

    if not dff.empty and 'market' in dff.columns:
        market_agg = {
            'Posts': ('id', 'count'),
            'AI_Tagged': ('validation_status', lambda x: (x == 'pass').sum()),
            'Flagged': ('needs_human_review', 'sum'),
            'Avg_Confidence': ('confidence', 'mean'),
        }
        if 'plays' in dff.columns:
            market_agg['Total_Plays'] = ('plays', 'sum')
        if 'likes' in dff.columns:
            market_agg['Total_Likes'] = ('likes', 'sum')
        if 'shares' in dff.columns:
            market_agg['Total_Shares'] = ('shares', 'sum')
        if 'comments' in dff.columns:
            market_agg['Total_Comments'] = ('comments', 'sum')

        market_summary = dff.groupby('market').agg(**market_agg).reset_index()
        market_summary['Automation %'] = (market_summary['AI_Tagged'] / market_summary['Posts'] * 100).round(1).astype(str) + '%'
        market_summary['Avg_Confidence'] = market_summary['Avg_Confidence'].apply(lambda x: f'{x:.0%}' if x == x else '—')

        if 'Total_Plays' in market_summary.columns:
            market_summary['Avg Plays/Post'] = (market_summary['Total_Plays'] / market_summary['Posts']).round(0).fillna(0).astype(int)
        if 'Total_Likes' in market_summary.columns and 'Total_Plays' in market_summary.columns:
            market_summary['Like Rate'] = (market_summary['Total_Likes'] / market_summary['Total_Plays']).apply(lambda x: f'{x:.1%}' if x == x and x != float('inf') else '—')
        if 'Total_Shares' in market_summary.columns and 'Total_Plays' in market_summary.columns:
            market_summary['Share Rate'] = (market_summary['Total_Shares'] / market_summary['Total_Plays']).apply(lambda x: f'{x:.1%}' if x == x and x != float('inf') else '—')

        # Top narrative per market
        if 'Narrative' in dff.columns:
            narr_market = dff[dff['Narrative'].notna() & (dff['Narrative'] != '')]
            if not narr_market.empty:
                top_narr_market = narr_market.groupby('market')['Narrative'].agg(
                    lambda x: x.value_counts().index[0] if len(x) else '—'
                ).reset_index().rename(columns={'Narrative': 'Top Narrative'})
                market_summary = market_summary.merge(top_narr_market, on='market', how='left')

        # Top creative type per market
        if 'Creative Type' in dff.columns:
            ct_market = dff[dff['Creative Type'].notna() & (dff['Creative Type'] != '')].copy()
            if not ct_market.empty:
                ct_market = ct_market.assign(**{'Creative Type': ct_market['Creative Type'].str.split(', ')}).explode('Creative Type')
                top_ct_market = ct_market.groupby('market')['Creative Type'].agg(
                    lambda x: x.value_counts().index[0] if len(x) else '—'
                ).reset_index().rename(columns={'Creative Type': 'Top Creative Type'})
                market_summary = market_summary.merge(top_ct_market, on='market', how='left')

        # Friendly column order
        order_cols = [
            'market', 'Posts', 'Total_Plays', 'Avg Plays/Post', 'Total_Likes', 'Total_Shares',
            'Like Rate', 'Share Rate', 'Top Narrative', 'Top Creative Type',
            'Automation %', 'Avg_Confidence', 'Flagged'
        ]
        order_cols = [c for c in order_cols if c in market_summary.columns]
        market_summary = market_summary.sort_values(
            'Total_Plays' if 'Total_Plays' in market_summary.columns else 'Posts',
            ascending=False
        )
        st.dataframe(market_summary[order_cols], use_container_width=True, hide_index=True)
    else:
        st.caption("No market data available yet.")
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Executive Insights ─────────────────────────────────
    def _fmt_pct(x):
        try:
            if pd.isna(x) or x == float('inf'):
                return '—'
            return f'{x:.1%}'
        except Exception:
            return '—'

    def _safe_num_col(frame, col):
        if col in frame.columns:
            return pd.to_numeric(frame[col], errors='coerce').fillna(0)
        return pd.Series([0] * len(frame), index=frame.index)

    dff['_plays_num'] = _safe_num_col(dff, 'plays')
    dff['_likes_num'] = _safe_num_col(dff, 'likes')
    dff['_shares_num'] = _safe_num_col(dff, 'shares')
    dff['_comments_num'] = _safe_num_col(dff, 'comments')
    dff['_saves_num'] = _safe_num_col(dff, 'saves')
    dff['_engagement_num'] = dff['_likes_num'] + dff['_shares_num'] + dff['_comments_num'] + dff['_saves_num']

    st.markdown("<div class='section-card'><h3>Executive Snapshot</h3>", unsafe_allow_html=True)
    insight_items = []

    if 'Creative Type' in dff.columns and not dff.empty:
        ct_tmp = dff[dff['Creative Type'].notna() & (dff['Creative Type'].astype(str).str.strip() != '')].copy()
        if not ct_tmp.empty:
            ct_tmp = ct_tmp.assign(**{'Creative Type': ct_tmp['Creative Type'].astype(str).str.split(', ')}).explode('Creative Type')
            ct_counts = ct_tmp['Creative Type'].value_counts()
            if not ct_counts.empty:
                top_ct = ct_counts.index[0]
                top_ct_share = ct_counts.iloc[0] / max(len(ct_tmp), 1)
                insight_items.append(f"<strong>{top_ct}</strong> is the leading creative type ({top_ct_share:.0%} of tagged labels).")

    if 'Narrative' in dff.columns and not dff.empty:
        narr_counts = dff['Narrative'].dropna().astype(str).str.strip()
        narr_counts = narr_counts[narr_counts != ''].value_counts()
        if not narr_counts.empty:
            insight_items.append(f"Top narrative: <strong>{narr_counts.index[0]}</strong> ({int(narr_counts.iloc[0])} post(s)).")

    if 'market' in dff.columns and not dff.empty:
        market_counts = dff['market'].dropna().astype(str).value_counts()
        if not market_counts.empty:
            insight_items.append(f"Largest market sample: <strong>{market_counts.index[0]}</strong> ({int(market_counts.iloc[0])} post(s)).")

    if dff['_plays_num'].sum() > 0 and 'Creative Type' in dff.columns:
        perf_tmp = dff[dff['Creative Type'].notna() & (dff['Creative Type'].astype(str).str.strip() != '')].copy()
        if not perf_tmp.empty:
            perf_tmp = perf_tmp.assign(**{'Creative Type': perf_tmp['Creative Type'].astype(str).str.split(', ')}).explode('Creative Type')
            perf_grp = perf_tmp.groupby('Creative Type').agg(Posts=('id', 'count'), Avg_Plays=('_plays_num', 'mean')).reset_index()
            perf_grp = perf_grp[perf_grp['Posts'] >= 2].sort_values('Avg_Plays', ascending=False)
            if not perf_grp.empty:
                insight_items.append(f"Best average plays by format: <strong>{perf_grp.iloc[0]['Creative Type']}</strong> ({int(perf_grp.iloc[0]['Avg_Plays']):,} avg plays).")

    if not insight_items:
        insight_items.append("Add tagged rows to generate trend highlights automatically.")

    st.markdown(
        "<div class='info-banner'><ul style='margin:0;padding-left:18px;line-height:1.8'>" +
        ''.join(f"<li>{x}</li>" for x in insight_items[:5]) +
        "</ul></div>",
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Row 1: clearer, limited charts ─────────────────────
    c1, c2 = st.columns(2, gap="large")

    with c1:
        st.markdown("<div class='section-card'><h3>Engagement by Market</h3>", unsafe_allow_html=True)
        st.markdown("<p style='font-size:13px;color:#64748b;margin:-8px 0 14px'>Total likes, comments, shares and saves by market.</p>", unsafe_allow_html=True)
        if not dff.empty and 'market' in dff.columns:
            eng_market = dff.groupby('market').agg(
                Likes=('_likes_num', 'sum'),
                Comments=('_comments_num', 'sum'),
                Shares=('_shares_num', 'sum'),
                Saves=('_saves_num', 'sum'),
                Total_Engagement=('_engagement_num', 'sum'),
                Posts=('id', 'count')
            ).reset_index()
            eng_market = eng_market[eng_market['Total_Engagement'] > 0].copy()
            if not eng_market.empty:
                eng_long = eng_market.melt(
                    id_vars=['market', 'Posts', 'Total_Engagement'],
                    value_vars=['Likes', 'Comments', 'Shares', 'Saves'],
                    var_name='Engagement Type',
                    value_name='Count'
                )
                eng_long = eng_long[eng_long['Count'] > 0]
                order_eng = eng_market.sort_values('Total_Engagement', ascending=True)['market'].tolist()
                ENGAGEMENT_COLORS = {
                    'Likes': '#2563EB',
                    'Comments': '#10B981',
                    'Shares': '#F59E0B',
                    'Saves': '#8B5CF6',
                }
                fig_eng = px.bar(
                    eng_long,
                    x='Count',
                    y='market',
                    color='Engagement Type',
                    orientation='h',
                    barmode='stack',
                    template='plotly_white',
                    color_discrete_map=ENGAGEMENT_COLORS,
                    category_orders={'market': order_eng},
                    labels={'Count': 'Total Engagement', 'market': 'Market'}
                )
                fig_eng.update_layout(
                    margin=dict(l=0, r=0, t=4, b=0),
                    height=max(300, len(order_eng) * 58),
                    yaxis_title='',
                    xaxis_title='Total Engagement',
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    font=dict(color='#334155', size=12),
                    yaxis=dict(tickfont=dict(color='#334155')),
                    xaxis=dict(tickfont=dict(color='#334155')),
                    legend=dict(orientation='h', y=1.08, font=dict(color='#334155'), title='')
                )
                fig_eng.update_traces(marker_line_width=0)
                st.plotly_chart(fig_eng, use_container_width=True)

                eng_table = eng_market.copy().sort_values('Total_Engagement', ascending=False)
                for col in ['Likes', 'Comments', 'Shares', 'Saves', 'Total_Engagement']:
                    eng_table[col] = eng_table[col].apply(lambda x: f'{int(x):,}')
                eng_table = eng_table.rename(columns={'market': 'Market', 'Total_Engagement': 'Total Engagement'})
                st.dataframe(eng_table[['Market', 'Posts', 'Likes', 'Comments', 'Shares', 'Saves', 'Total Engagement']], use_container_width=True, hide_index=True)
            else:
                st.caption("No engagement data yet.")
        else:
            st.caption("No market / engagement data yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown("<div class='section-card'><h3>Creative Type Mix</h3>", unsafe_allow_html=True)
        st.markdown("<p style='font-size:13px;color:#64748b;margin:-8px 0 14px'>Sorted by total posts, so dominant content formats are obvious.</p>", unsafe_allow_html=True)
        ct_exp = dff[dff['Creative Type'].notna() & (dff['Creative Type'].astype(str).str.strip() != '')].copy() if 'Creative Type' in dff.columns else pd.DataFrame()
        if not ct_exp.empty:
            ct_exp = ct_exp.assign(**{'Creative Type': ct_exp['Creative Type'].astype(str).str.split(', ')}).explode('Creative Type')
            ct_grp = ct_exp.groupby(['Creative Type', 'market']).size().reset_index(name='Posts')
            total_ct = ct_grp.groupby('Creative Type')['Posts'].sum().sort_values(ascending=True)
            keep_ct = total_ct.tail(12).index.tolist()
            ct_grp = ct_grp[ct_grp['Creative Type'].isin(keep_ct)]
            order2 = ct_grp.groupby('Creative Type')['Posts'].sum().sort_values().index.tolist()
            fig2 = px.bar(ct_grp, x='Posts', y='Creative Type', color='market', orientation='h',
                          barmode='stack', template='plotly_white',
                          color_discrete_map=MARKET_COLORS,
                          category_orders={'Creative Type': order2},
                          labels={'Posts': 'Posts', 'market': 'Market'})
            fig2.update_layout(margin=dict(l=0, r=0, t=4, b=0),
                               height=max(300, len(order2) * 32), yaxis_title='', xaxis_title='Posts',
                               plot_bgcolor='white', paper_bgcolor='white',
                               font=dict(color='#334155', size=12),
                               yaxis=dict(tickfont=dict(color='#334155')),
                               xaxis=dict(tickfont=dict(color='#334155')),
                               legend=dict(orientation='h', y=1.08, font=dict(color='#334155'), title=''))
            fig2.update_traces(marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.caption("No creative type data yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Row 2: performance, not just counts ───────────────
    c3, c4 = st.columns(2, gap="large")

    with c3:
        st.markdown("<div class='section-card'><h3>Engagement Rate by Creative Type</h3>", unsafe_allow_html=True)
        st.markdown("<p style='font-size:13px;color:#64748b;margin:-8px 0 14px'>Shows which formats perform better, not only which formats appear more often.</p>", unsafe_allow_html=True)
        er_src = dff[dff['Creative Type'].notna() & (dff['Creative Type'].astype(str).str.strip() != '')].copy() if 'Creative Type' in dff.columns else pd.DataFrame()
        if not er_src.empty and er_src['_plays_num'].sum() > 0:
            er_src = er_src.assign(**{'Creative Type': er_src['Creative Type'].astype(str).str.split(', ')}).explode('Creative Type')
            er_grp = er_src.groupby('Creative Type').agg(
                Posts=('id', 'count'),
                Plays=('_plays_num', 'sum'),
                Engagement=('_engagement_num', 'sum')
            ).reset_index()
            er_grp = er_grp[(er_grp['Posts'] >= 2) & (er_grp['Plays'] > 0)].copy()
            er_grp['Engagement Rate'] = er_grp['Engagement'] / er_grp['Plays']
            er_grp = er_grp.sort_values('Engagement Rate', ascending=True).tail(10)
            if not er_grp.empty:
                fig_er = px.bar(er_grp, x='Engagement Rate', y='Creative Type', orientation='h',
                                template='plotly_white', text=er_grp['Engagement Rate'].apply(lambda x: f'{x:.1%}'),
                                hover_data={'Posts': True, 'Plays': ':,', 'Engagement': ':,', 'Engagement Rate': ':.1%'})
                fig_er.update_layout(margin=dict(l=0, r=0, t=4, b=0),
                                     height=max(300, len(er_grp) * 34), yaxis_title='', xaxis_title='Engagement Rate',
                                     plot_bgcolor='white', paper_bgcolor='white',
                                     font=dict(color='#334155', size=12),
                                     yaxis=dict(tickfont=dict(color='#334155')),
                                     xaxis=dict(tickfont=dict(color='#334155'), tickformat='.0%'))
                fig_er.update_traces(marker_line_width=0, textposition='outside')
                st.plotly_chart(fig_er, use_container_width=True)
            else:
                st.caption("Need at least 2 posts per creative type to show this chart.")
        else:
            st.caption("No plays / engagement data yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    with c4:
        st.markdown("<div class='section-card'><h3>Market Content Mix</h3>", unsafe_allow_html=True)
        st.markdown("<p style='font-size:13px;color:#64748b;margin:-8px 0 14px'>Top creative type per market with share of posts.</p>", unsafe_allow_html=True)
        mix_src = dff[dff['Creative Type'].notna() & (dff['Creative Type'].astype(str).str.strip() != '')].copy() if 'Creative Type' in dff.columns else pd.DataFrame()
        if not mix_src.empty and 'market' in mix_src.columns:
            mix_src = mix_src.assign(**{'Creative Type': mix_src['Creative Type'].astype(str).str.split(', ')}).explode('Creative Type')
            mix = mix_src.groupby(['market', 'Creative Type']).size().reset_index(name='Posts')
            totals = mix.groupby('market')['Posts'].transform('sum')
            mix['Share'] = mix['Posts'] / totals
            top_mix = mix.sort_values(['market', 'Posts'], ascending=[True, False]).groupby('market').head(3).copy()
            top_mix['Share'] = top_mix['Share'].apply(lambda x: f'{x:.0%}')
            top_mix = top_mix.rename(columns={'market': 'Market'})
            st.dataframe(top_mix[['Market', 'Creative Type', 'Posts', 'Share']], use_container_width=True, hide_index=True)
        else:
            st.caption("No market / creative type data yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Row 3: Track Leaderboard (full width) ─────────────
    st.markdown("<div class='section-card'><h3>Track Leaderboard by Plays</h3>", unsafe_allow_html=True)
    if 'plays' in dff.columns and dff['_plays_num'].sum() > 0:
        leaderboard = dff.groupby(['market', 'track']).agg(
            Total_Plays=('_plays_num', 'sum'),
            Posts=('id', 'count'),
            Avg_Plays=('_plays_num', 'mean'),
            Total_Engagement=('_engagement_num', 'sum')
        ).reset_index()
        leaderboard['Avg_Plays'] = leaderboard['Avg_Plays'].round(0)
        leaderboard['Engagement Rate'] = leaderboard['Total_Engagement'] / leaderboard['Total_Plays'].replace(0, pd.NA)
        leaderboard['label'] = leaderboard['track'].astype(str).str[:45]
        leaderboard = leaderboard.sort_values('Total_Plays', ascending=True).tail(20)
        fig_lb = px.bar(
            leaderboard, x='Total_Plays', y='label', orientation='h',
            color='market', template='plotly_white',
            color_discrete_map=MARKET_COLORS,
            hover_data={'market': True, 'Posts': True, 'Avg_Plays': ':,.0f', 'Total_Plays': ':,.0f', 'Engagement Rate': ':.1%', 'label': False},
            labels={'label': '', 'Total_Plays': 'Total Plays', 'market': 'Market'}
        )
        fig_lb.update_layout(
            margin=dict(l=0, r=0, t=4, b=0), height=max(360, len(leaderboard) * 34),
            xaxis_title='Total Plays', yaxis_title='',
            plot_bgcolor='white', paper_bgcolor='white',
            font=dict(color='#334155', size=12),
            yaxis=dict(tickfont=dict(color='#334155')),
            xaxis=dict(tickfont=dict(color='#334155')),
            legend=dict(orientation='h', y=1.04, font=dict(color='#334155'), title='')
        )
        fig_lb.update_traces(marker_line_width=0)
        st.plotly_chart(fig_lb, use_container_width=True)
    else:
        st.caption("No plays data yet.")
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Row 4: Market & Track ranked table ───────────────────────────────
    has_plays = '_plays_num' in dff.columns and dff['_plays_num'].sum() > 0
    has_likes = '_likes_num' in dff.columns and dff['_likes_num'].sum() > 0

    st.markdown("<div class='section-card'><h3>Track Performance by Market</h3>", unsafe_allow_html=True)
    mkt_agg = dict(
        Posts=('id', 'count'),
        AI_Tagged=('validation_status', lambda x: (x == 'pass').sum()),
        Flagged=('needs_human_review', 'sum'),
        Avg_Confidence=('confidence', 'mean'),
    )
    if has_plays:
        mkt_agg['Total_Plays'] = ('_plays_num', 'sum')
        mkt_agg['Total_Engagement'] = ('_engagement_num', 'sum')
    if has_likes:
        mkt_agg['Total_Likes'] = ('_likes_num', 'sum')

    mkt = dff.groupby(['market', 'track']).agg(**mkt_agg).reset_index()

    if has_plays:
        mkt['Avg_Plays'] = (mkt['Total_Plays'] / mkt['Posts']).round(0).astype(int)
        mkt['Engagement Rate'] = (mkt['Total_Engagement'] / mkt['Total_Plays']).apply(_fmt_pct)
    if has_plays and has_likes:
        mkt['Like_Rate'] = (mkt['Total_Likes'] / mkt['Total_Plays']).apply(_fmt_pct)

    rank_col = 'Total_Plays' if has_plays else 'Posts'
    mkt['Rank'] = mkt.groupby('market')[rank_col].rank(ascending=False, method='min').astype(int)
    mkt = mkt.sort_values(['market', 'Rank'])
    mkt['Automation'] = (mkt['AI_Tagged'] / mkt['Posts'] * 100).round(1).astype(str) + '%'
    mkt['Avg_Confidence'] = mkt['Avg_Confidence'].apply(lambda x: f'{x:.0%}' if x == x else '—')

    display_cols = ['Rank', 'market', 'track', 'Posts', 'Total_Plays', 'Avg_Plays',
                    'Total_Likes', 'Like_Rate', 'Engagement Rate', 'Automation', 'Avg_Confidence', 'Flagged']
    display_cols = [c for c in display_cols if c in mkt.columns]
    st.dataframe(mkt[display_cols], use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Row 5: What's Working — top narrative per track ───────────────────
    if 'Narrative' in dff.columns and has_plays:
        narr_track = dff[dff['Narrative'].notna() & (dff['Narrative'].astype(str).str.strip() != '')].copy()
        if not narr_track.empty:
            st.markdown("<div class='section-card'><h3>What's Working — Top Narrative per Track</h3>", unsafe_allow_html=True)
            st.markdown("<p style='font-size:13px;color:#64748b;margin:-8px 0 14px'>For each market + track, the narrative that drives the highest average plays.</p>", unsafe_allow_html=True)

            narr_grp = narr_track.groupby(['market', 'track', 'Narrative']).agg(
                Posts=('id', 'count'),
                Avg_Plays=('_plays_num', 'mean'),
                Total_Plays=('_plays_num', 'sum'),
            ).reset_index()
            narr_grp['Avg_Plays'] = narr_grp['Avg_Plays'].round(0).astype(int)

            top_narr = narr_grp.loc[
                narr_grp.groupby(['market', 'track'])['Avg_Plays'].idxmax()
            ].sort_values(['market', 'Total_Plays'], ascending=[True, False]).reset_index(drop=True)

            top_narr = top_narr[['market', 'track', 'Narrative', 'Posts', 'Avg_Plays', 'Total_Plays']]
            top_narr.columns = ['Market', 'Track', 'Top Narrative', 'Posts w/ Narrative', 'Avg Plays', 'Total Plays']
            st.dataframe(top_narr, use_container_width=True, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# BATCH FILTER
# ══════════════════════════════════════════════════════════
elif page == "Batch Filter":
    import streamlit as st
    import pandas as pd
    import re
    import io
    import tempfile
    from datetime import timedelta
    from pathlib import Path

    try:
        from rapidfuzz import fuzz
    except Exception:
        fuzz = None




    # -----------------------------
    # UI styling
    # -----------------------------

    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1280px;
        }
        .hero-card {
            padding: 1.5rem 1.75rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #f6f8ff 0%, #eef6ff 50%, #fff7ed 100%);
            border: 1px solid #e5e7eb;
            margin-bottom: 1.25rem;
        }
        .hero-title {
            font-size: 2.15rem;
            line-height: 1.15;
            font-weight: 800;
            color: #111827;
            margin: 0 0 0.35rem 0;
        }
        .hero-subtitle {
            font-size: 1rem;
            color: #4b5563;
            margin: 0;
        }
        .section-card {
            padding: 1.25rem 1.35rem;
            border-radius: 18px;
            border: 1px solid #e5e7eb;
            background: #ffffff;
            margin-bottom: 1.15rem;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
            color: #111827 !important;
        }
        .section-card h1,
        .section-card h2,
        .section-card h3,
        .section-card h4,
        .section-card p,
        .section-card span,
        .section-card label {
            color: #111827 !important;
        }
        .section-card h3 {
            font-size: 1.45rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            margin-bottom: 0.35rem;
        }
        .step-badge {
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            background: #eef2ff;
            color: #3730a3;
            font-size: 0.8rem;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }
        .small-note {
            color: #4b5563 !important;
            font-size: 0.9rem;
        }
        .stFileUploader label, .stNumberInput label, .stSlider label, .stCheckbox label, .stTextInput label {
            font-weight: 700 !important;
        }
        div.stButton > button:first-child {
            border-radius: 999px;
            min-height: 3rem;
            font-weight: 700;
        }
        div[data-testid="stDownloadButton"] button {
            border-radius: 999px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------
    # Helpers
    # -----------------------------

    def clean_number(x):
        if pd.isna(x):
            return 0
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x).strip().replace(',', '').replace('%', '')
        if s.lower() in ['', 'nan', 'none', 'null', '-']:
            return 0
        try:
            return int(float(s))
        except Exception:
            return 0


    def parse_date_series(s):
        # First normal parse, then dayfirst fallback.
        out = pd.to_datetime(s, errors='coerce')
        if out.isna().mean() > 0.5:
            out2 = pd.to_datetime(s, errors='coerce', dayfirst=True)
            if out2.notna().sum() > out.notna().sum():
                out = out2
        return out


    def parse_single_date(x):
        d = pd.to_datetime(x, errors='coerce')
        if pd.isna(d):
            d = pd.to_datetime(x, errors='coerce', dayfirst=True)
        return d


    def detect_col(df, candidates):
        norm = {str(c).strip().lower(): c for c in df.columns}
        for cand in candidates:
            key = cand.strip().lower()
            if key in norm:
                return norm[key]
        # fuzzy-ish contains fallback
        for c in df.columns:
            cl = str(c).strip().lower()
            for cand in candidates:
                ck = cand.strip().lower()
                if ck and ck in cl:
                    return c
        return None


    def normalize_text(s):
        s = str(s or '')
        # split CamelCase: ReallyLikeYou -> Really Like You
        s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)
        s = s.replace('&', ' and ')
        s = re.sub(r'[_\-\/\(\)\[\]\{\}\.,:;!\?]+', ' ', s)
        s = re.sub(r'[^A-Za-z0-9가-힣一-龥ぁ-んァ-ン ]+', ' ', s)
        s = s.lower()
        # common cleanup
        s = s.replace('posts tiktok', ' ')
        s = s.replace('post tiktok', ' ')
        s = re.sub(r'\b20\d{2}\b|\b\d{1,2}\b', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s


    def filename_match_text(filename):
        name = Path(filename).stem
        name = re.sub(r'^\d{4}[-_]?\d{1,2}[-_]?\d{1,2}[_\- ]*', '', name)
        name = re.sub(r'[_\- ]*posts?[_\- ]*tiktok.*$', '', name, flags=re.I)
        return normalize_text(name)


    def track_match_text(artist_sound):
        return normalize_text(artist_sound)


    def score_match(file_text, track_text):
        if not file_text or not track_text:
            return 0
        if fuzz:
            return max(
                fuzz.token_set_ratio(file_text, track_text),
                fuzz.token_sort_ratio(file_text, track_text),
                fuzz.partial_ratio(file_text, track_text),
            )
        # fallback token overlap
        ft = set(file_text.split())
        tt = set(track_text.split())
        if not ft or not tt:
            return 0
        return int(100 * len(ft & tt) / max(len(ft), len(tt)))


    def read_table(uploaded):
        name = uploaded.name.lower()
        if name.endswith('.csv'):
            return pd.read_csv(uploaded)
        return pd.read_excel(uploaded)


    def find_best_track(file_name, track_df, artist_col):
        ft = filename_match_text(file_name)
        best_idx, best_score = None, -1
        for idx, row in track_df.iterrows():
            score = score_match(ft, track_match_text(row.get(artist_col, '')))
            if score > best_score:
                best_score = score
                best_idx = idx
        return best_idx, best_score, ft


    def country_alias(x):
        s = str(x or '').strip().lower()
        aliases = {
            'kr': 'KR', 'korea': 'KR', 'south korea': 'KR', 'kor': 'KR',
            'id': 'Indonesia', 'indonesia': 'Indonesia',
            'my': 'Malaysia', 'malaysia': 'Malaysia',
            'ph': 'Philippines', 'philippines': 'Philippines',
            'sg': 'Singapore', 'singapore': 'Singapore',
            'th': 'Thailand', 'thailand': 'Thailand',
            'vn': 'Vietnam', 'vietnam': 'Vietnam', 'viet nam': 'Vietnam',
        }
        return aliases.get(s, str(x or '').strip())


    def kol_size(country, followers):
        c = country_alias(country)
        f = clean_number(followers)
        if c == 'KR':
            return ''

        # Thresholds are upper limits, not lower bounds.
        # Example for Malaysia:
        #   <= 10,000 = Nano
        #   <= 100,000 = Micro
        #   <= 1,000,000 = Macro
        #   > 1,000,000 = Mega
        thresholds = {
            'Indonesia': [
                (1000, 'Buzzer'), (10000, 'Nano'), (50000, 'Micro'),
                (200000, 'Medium'), (1000000, 'Macro')
            ],
            'Malaysia': [
                (10000, 'Nano'), (100000, 'Micro'), (1000000, 'Macro')
            ],
            'Philippines': [
                (10000, 'Nano'), (100000, 'Micro'), (2000000, 'Macro')
            ],
            'Singapore': [
                (10000, 'Nano'), (30000, 'Micro'), (100000, 'Medium'),
                (500000, 'Macro')
            ],
            'Thailand': [
                (1000, 'Buzzer'), (10000, 'Nano'), (100000, 'Micro'),
                (500000, 'Medium'), (1000000, 'Macro'), (5000000, 'Mega')
            ],
            'Vietnam': [
                (1000, 'Buzzer'), (10000, 'Nano'), (100000, 'Micro'),
                (500000, 'Medium'), (1000000, 'Macro'), (5000000, 'Mega')
            ],
        }

        for cutoff, label in thresholds.get(c, []):
            if f <= cutoff:
                return label

        top_labels = {
            'Indonesia': 'Mega',
            'Malaysia': 'Mega',
            'Philippines': 'Mega',
            'Singapore': 'Mega',
            'Thailand': 'Super Mega',
            'Vietnam': 'Super Mega',
        }
        return top_labels.get(c, '')

    def extract_video_id(url):
        s = str(url or '')
        m = re.search(r'/video/(\d+)', s)
        if m:
            return m.group(1)
        m = re.search(r'(?:item_id|aweme_id|share_item_id|modal_id)[=:](\d+)', s)
        return m.group(1) if m else ''


    def first_number_from_keys(obj, keys):
        if not isinstance(obj, dict):
            return 0
        for key in keys:
            value = obj.get(key)
            num = clean_number(value)
            if num > 0:
                return num
        return 0


    def extract_tiktok_username_from_url(url):
        s = str(url or '')
        m = re.search(r'tiktok\.com/@([^/?#]+)', s)
        return m.group(1).strip().lower() if m else ''


    def extract_author_username(item):
        if not isinstance(item, dict):
            return ''
        author = item.get('authorMeta') if isinstance(item.get('authorMeta'), dict) else {}
        author2 = item.get('author') if isinstance(item.get('author'), dict) else {}
        for value in [
            author.get('name'), author.get('nickName'), author.get('uniqueId'), author.get('username'),
            author2.get('uniqueId'), author2.get('username'), item.get('author'), item.get('authorName'),
            extract_tiktok_username_from_url(item.get('webVideoUrl') or item.get('submittedVideoUrl') or item.get('url'))
        ]:
            value = str(value or '').strip().lstrip('@')
            if value:
                return value.lower()
        return ''


    def extract_author_followers(item):
        if not isinstance(item, dict):
            return 0
        author = item.get('authorMeta') if isinstance(item.get('authorMeta'), dict) else {}
        author2 = item.get('author') if isinstance(item.get('author'), dict) else {}
        stats = item.get('stats') if isinstance(item.get('stats'), dict) else {}
        return max(
            first_number_from_keys(author, ['fans', 'followers', 'followerCount', 'fansCount']),
            first_number_from_keys(author2, ['fans', 'followers', 'followerCount', 'fansCount']),
            first_number_from_keys(stats, ['followerCount', 'followers']),
            first_number_from_keys(item, ['authorFans', 'authorFollowers', 'followerCount', 'followers'])
        )


    def run_apify_for_saves(links, token):
        from apify_client import ApifyClient
        client = ApifyClient(token)
        run_input = {
            'postURLs': links,
            'resultsPerPage': len(links),
            'shouldDownloadVideos': False,
            'shouldDownloadCovers': False,
            'shouldDownloadSlideshowImages': False,
            'shouldDownloadAvatars': False,
            'shouldDownloadMusicCovers': False,
            'commentsPerPost': 0,
            'topLevelCommentsPerPost': 0,
            'maxRepliesPerComment': 0,
            'excludePinnedPosts': False,
            'scrapeRelatedSearchWords': False,
            'scrapeRelatedVideos': False,
            'proxyCountryCode': 'None',
        }
        run = client.actor('clockworks/tiktok-scraper').call(run_input=run_input)
        dataset_id = run.get('defaultDatasetId') if isinstance(run, dict) else getattr(run, 'default_dataset_id', None)
        items = list(client.dataset(dataset_id).iterate_items()) if dataset_id else []

        saves_by_video = {}
        followers_by_video = {}
        followers_by_username = {}

        for item in items:
            vid = str(item.get('id') or extract_video_id(item.get('webVideoUrl') or item.get('submittedVideoUrl') or item.get('url')))
            saves = clean_number(item.get('collectCount', item.get('stats', {}).get('collectCount', 0) if isinstance(item.get('stats'), dict) else 0))
            followers = extract_author_followers(item)
            username = extract_author_username(item)

            if vid:
                saves_by_video[vid] = saves
                if followers > 0:
                    followers_by_video[vid] = followers
            if username and followers > 0:
                followers_by_username[username] = followers

        return {
            'saves_by_video': saves_by_video,
            'followers_by_video': followers_by_video,
            'followers_by_username': followers_by_username,
        }


    def pct(num, den):
        den = clean_number(den)
        num = clean_number(num)
        if den <= 0:
            return ''
        return f'{num / den:.2%}'


    def process_one(melody_df, track_row, cols, top_n=20, window_days=7):
        country = track_row.get(cols['track_country'], '')
        label = track_row.get(cols['track_label'], '') if cols['track_label'] else ''
        artist_sound = track_row.get(cols['track_artist'], '')
        viral_date_raw = track_row.get(cols['track_viral'], '')
        repertoire = track_row.get(cols['track_repertoire'], '') if cols['track_repertoire'] else ''
        viral_date = parse_single_date(viral_date_raw)
        if pd.isna(viral_date):
            raise ValueError(f'Could not parse viral date: {viral_date_raw}')

        date_col = cols['date']
        country_col = cols['country']
        username_col = cols['username']
        followers_col = cols['followers']
        link_col = cols['link']
        views_col = cols['views']
        likes_col = cols['likes']
        comments_col = cols['comments']
        shares_col = cols['shares']

        df = melody_df.copy()
        df['_parsed_date'] = parse_date_series(df[date_col])
        df['_country_norm'] = df[country_col].apply(country_alias)
        target_country = country_alias(country)

        start = viral_date - timedelta(days=window_days)
        end = viral_date + timedelta(days=window_days)

        before = len(df)
        df = df[df['_country_norm'].astype(str).str.lower() == str(target_country).lower()].copy()
        after_country = len(df)
        df = df[(df['_parsed_date'] >= start) & (df['_parsed_date'] <= end)].copy()
        after_date = len(df)

        df['_likes_num'] = df[likes_col].apply(clean_number)
        df['_comments_num'] = df[comments_col].apply(clean_number)
        df['_shares_num'] = df[shares_col].apply(clean_number)
        df['_ranking_score'] = df['_likes_num'] + df['_comments_num'] + df['_shares_num']
        df = df.sort_values('_ranking_score', ascending=False).head(top_n).copy()

        rows = []
        for _, r in df.iterrows():
            views = clean_number(r.get(views_col))
            likes = clean_number(r.get(likes_col))
            comments = clean_number(r.get(comments_col))
            shares = clean_number(r.get(shares_col))
            saves = 0
            followers = clean_number(r.get(followers_col))
            rows.append({
                'Country': country,
                'Label': label,
                'Artist - Sound': artist_sound,
                '2026 Viral Date': viral_date.strftime('%Y-%m-%d'),
                'Repertoire': repertoire,
                'Date': r.get(date_col, ''),
                'Username': r.get(username_col, ''),
                'Followers': followers,
                'KOL Size': kol_size(country, followers),
                'Link': r.get(link_col, ''),
                'Views': views,
                'Likes': likes,
                'Comments': comments,
                'Shares': shares,
                'Saves': saves,
                'Total Engagement': likes + comments + shares + saves,
                'Engagement Rate': pct(likes + comments + shares + saves, views),
                'Likes Rate': pct(likes, views),
                'Comments Rate': pct(comments, views),
                'Shares Rate': pct(shares, views),
                'Saves Rate': pct(saves, views),
                '_video_id': extract_video_id(r.get(link_col, '')),
            })
        out = pd.DataFrame(rows)
        stats = {'original': before, 'country': after_country, 'date': after_date, 'selected': len(out)}
        return out, stats


    def apply_saves(out_df, token):
        if out_df.empty:
            return out_df
        links = out_df['Link'].dropna().astype(str).tolist()
        apify_data = run_apify_for_saves(links, token)
        save_map = apify_data.get('saves_by_video', {}) if isinstance(apify_data, dict) else apify_data
        followers_by_video = apify_data.get('followers_by_video', {}) if isinstance(apify_data, dict) else {}
        followers_by_username = apify_data.get('followers_by_username', {}) if isinstance(apify_data, dict) else {}

        out = out_df.copy()
        for idx, row in out.iterrows():
            vid = str(row.get('_video_id') or extract_video_id(row.get('Link')))
            saves = clean_number(save_map.get(vid, 0))
            out.at[idx, 'Saves'] = saves

            followers = clean_number(row.get('Followers'))
            if followers <= 0:
                username = str(row.get('Username') or '').strip().lstrip('@').lower()
                followers = clean_number(followers_by_video.get(vid, 0))
                if followers <= 0 and username:
                    followers = clean_number(followers_by_username.get(username, 0))
                if followers <= 0:
                    url_username = extract_tiktok_username_from_url(row.get('Link'))
                    followers = clean_number(followers_by_username.get(url_username, 0))
                if followers > 0:
                    out.at[idx, 'Followers'] = followers
                    out.at[idx, 'KOL Size'] = kol_size(row.get('Country'), followers)

            total = clean_number(row.get('Likes')) + clean_number(row.get('Comments')) + clean_number(row.get('Shares')) + saves
            views = clean_number(row.get('Views'))
            out.at[idx, 'Total Engagement'] = total
            out.at[idx, 'Engagement Rate'] = pct(total, views)
            out.at[idx, 'Saves Rate'] = pct(saves, views)
        return out


    def excel_sheet_country_code(country):
        c = country_alias(country)
        code_map = {
            'Indonesia': 'ID',
            'Malaysia': 'MY',
            'Philippines': 'PH',
            'Singapore': 'SG',
            'Thailand': 'TH',
            'Vietnam': 'VN',
            'KR': 'KR',
        }
        return code_map.get(c, str(country or '').strip()[:10] or 'Unknown')


    def safe_sheet_name(name):
        # Excel sheet names cannot contain these characters and must be <= 31 chars.
        name = re.sub(r'[\\/*?:\[\]]+', ' ', str(name or 'Sheet')).strip()
        return name[:31] or 'Sheet'


    def write_output_sheet(writer, df, sheet_name):
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions

        # Keep the workbook readable without over-wide columns.
        for col_cells in ws.columns:
            header = str(col_cells[0].value or '')
            max_len = len(header)
            for cell in col_cells[1:]:
                max_len = max(max_len, len(str(cell.value or '')))
            width = min(max(max_len + 2, 10), 45)
            ws.column_dimensions[col_cells[0].column_letter].width = width


    def to_excel_bytes(df):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            # Keep market order consistent everywhere: MY, PH, SG, TH, VN, KR, then ID/others.
            preferred_order = ['MY', 'PH', 'SG', 'TH', 'VN', 'KR', 'ID']
            work = df.copy()
            work['_sheet_code'] = work['Country'].apply(excel_sheet_country_code)
            work['_market_order'] = work['_sheet_code'].apply(
                lambda x: preferred_order.index(x) if x in preferred_order else 999
            )
            work = work.sort_values(['_market_order', '_sheet_code'], kind='stable')

            # First tab: all rows sorted by market order.
            write_output_sheet(writer, work.drop(columns=['_sheet_code', '_market_order']), 'All Post Data')

            # Additional tabs: one per country in the same market order.
            country_codes = list(work['_sheet_code'].dropna().astype(str).unique())
            country_codes = sorted(country_codes, key=lambda x: (preferred_order.index(x) if x in preferred_order else 999, x))

            used_names = {'All Post Data'}
            for code in country_codes:
                country_df = work[work['_sheet_code'] == code].drop(columns=['_sheet_code', '_market_order'])
                base_name = safe_sheet_name(f'({code}) Post Data')
                sheet_name = base_name
                n = 2
                while sheet_name in used_names:
                    suffix = f' {n}'
                    sheet_name = safe_sheet_name(base_name[:31-len(suffix)] + suffix)
                    n += 1
                used_names.add(sheet_name)
                write_output_sheet(writer, country_df, sheet_name)
        return buf.getvalue()

    FINAL_COLUMNS = [
        'Country', 'Label', 'Artist - Sound', '2026 Viral Date', 'Repertoire',
        'Date', 'Username', 'Followers', 'KOL Size', 'Link',
        'Views', 'Likes', 'Comments', 'Shares', 'Saves', 'Total Engagement',
        'Engagement Rate', 'Likes Rate', 'Comments Rate', 'Shares Rate', 'Saves Rate'
    ]

    # -----------------------------
    # UI
    # -----------------------------

    st.markdown(
        '''
        <div class="hero-card">
            <div class="hero-title">MelodyIQ Batch Filter</div>
            <p class="hero-subtitle">Upload a tracklist and MelodyIQ CSVs, then filter by country and viral-date window, rank the top posts, and export clean post-data tabs by market.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    with st.expander('How it works', expanded=False):
        st.markdown('''
        **1. Match files:** Each MelodyIQ CSV is matched to the closest tracklist row using the filename.  
        **2. Filter rows:** Rows are filtered by market and viral date window.  
        **3. Rank posts:** Posts are ranked by **Likes + Comments + Shares** and limited to Top N.  
        **4. KOL size:** KOL labels use threshold-as-limit rules, with KR left blank.  
        **5. Export:** XLSX includes **All Post Data** plus separate market tabs.
        ''')

    st.markdown('<div class="section-card"><span class="step-badge">Step 1</span><h3 style="margin-top:0;color:#111827!important">Upload files</h3>', unsafe_allow_html=True)
    file_col1, file_col2 = st.columns(2)
    with file_col1:
        track_file = st.file_uploader('Tracklist CSV/XLSX', type=['csv', 'xlsx', 'xls'])
    with file_col2:
        melody_files = st.file_uploader('MelodyIQ CSV files', type=['csv'], accept_multiple_files=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card"><span class="step-badge">Step 2</span><h3 style="margin-top:0;color:#111827!important">Processing settings</h3>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        top_n = st.number_input('Top N posts per file', min_value=1, max_value=100, value=20)
    with c2:
        window_days = st.number_input('Viral date window, days before/after', min_value=0, max_value=60, value=7)
    with c3:
        match_threshold = st.slider('Auto-match threshold', min_value=50, max_value=100, value=75)

    fetch_saves = st.checkbox('Fetch Saves from Apify after Top N selection', value=False)
    apify_token = ''
    if fetch_saves:
        apify_token = st.text_input('Apify Token', type='password')
    st.markdown('<p class="small-note">Tip: keep the threshold at 75 unless filenames are very different from track names.</p></div>', unsafe_allow_html=True)

    if not track_file or not melody_files:
        st.info('Upload a tracklist and at least one MelodyIQ CSV to continue.')
        st.stop()

    try:
        track_df = read_table(track_file)
    except Exception as e:
        st.error(f'Could not read tracklist: {e}')
        st.stop()

    track_country = detect_col(track_df, ['Country', 'Market'])
    track_label = detect_col(track_df, ['Label'])
    track_artist = detect_col(track_df, ['Artist - Sound', 'Artist-Sound', 'Artist Sound', 'Sound', 'Track'])
    track_viral = detect_col(track_df, ['2026 Viral Date', 'Viral Date', 'viral_date'])
    track_repertoire = detect_col(track_df, ['Repertoire'])

    missing_track = []
    for name, col in [('Country', track_country), ('Artist - Sound', track_artist), ('2026 Viral Date', track_viral)]:
        if not col:
            missing_track.append(name)
    if missing_track:
        st.error('Tracklist missing required columns: ' + ', '.join(missing_track))
        st.write('Detected columns:', list(track_df.columns))
        st.stop()

    st.markdown('<div class="section-card"><span class="step-badge">Step 3</span><h3 style="margin-top:0">Match preview</h3>', unsafe_allow_html=True)
    preview = []
    file_data = []
    for f in melody_files:
        try:
            df = pd.read_csv(f)
            f.seek(0)
            best_idx, best_score, file_text = find_best_track(f.name, track_df, track_artist)
            matched = best_score >= match_threshold
            matched_track = track_df.loc[best_idx, track_artist] if best_idx is not None else ''
            preview.append({
                'File': f.name,
                'Filename text': file_text,
                'Matched Track': matched_track if matched else '',
                'Score': best_score,
                'Status': 'Matched' if matched else 'Needs check',
            })
            file_data.append({'file': f, 'df': df, 'best_idx': best_idx, 'score': best_score, 'matched': matched})
        except Exception as e:
            preview.append({'File': f.name, 'Filename text': '', 'Matched Track': '', 'Score': 0, 'Status': f'Error: {e}'})

    preview_df = pd.DataFrame(preview)
    st.dataframe(preview_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if any(not x.get('matched') for x in file_data):
        st.warning('Some files are below the match threshold. Lower the threshold or rename files before processing.')

    if st.button('Process files', type='primary'):
        all_outputs = []
        summaries = []
        progress = st.progress(0)
        status = st.empty()

        for i, item in enumerate(file_data):
            if not item['matched']:
                summaries.append({'File': item['file'].name, 'Track': '', 'Status': 'Skipped - unmatched'})
                continue
            f = item['file']
            df = item['df']
            track_row = track_df.loc[item['best_idx']]
            status.write(f'Processing {f.name} → {track_row.get(track_artist)}')

            date_col = detect_col(df, ['Date', 'Post Date', 'Created Date', 'createTimeISO'])
            country_col = detect_col(df, ['Country', 'Market', 'Region'])
            username_col = detect_col(df, ['Username', 'User', 'Creator', 'authorMeta.name'])
            followers_col = detect_col(df, ['Followers', 'Follower Count', 'authorMeta.fans'])
            link_col = detect_col(df, ['Link', 'URL', 'TikTok Link', 'Video URL', 'webVideoUrl', 'submittedVideoUrl'])
            views_col = detect_col(df, ['Views', 'Plays', 'playCount'])
            likes_col = detect_col(df, ['Likes', 'diggCount'])
            comments_col = detect_col(df, ['Comments', 'commentCount'])
            shares_col = detect_col(df, ['Shares', 'shareCount'])

            missing = [n for n, c in {
                'Date': date_col, 'Country': country_col, 'Username': username_col,
                'Followers': followers_col, 'Link': link_col, 'Views': views_col,
                'Likes': likes_col, 'Comments': comments_col, 'Shares': shares_col
            }.items() if not c]
            if missing:
                summaries.append({'File': f.name, 'Track': track_row.get(track_artist), 'Status': 'Skipped - missing ' + ', '.join(missing)})
                continue

            cols = {
                'track_country': track_country, 'track_label': track_label,
                'track_artist': track_artist, 'track_viral': track_viral,
                'track_repertoire': track_repertoire,
                'date': date_col, 'country': country_col, 'username': username_col,
                'followers': followers_col, 'link': link_col, 'views': views_col,
                'likes': likes_col, 'comments': comments_col, 'shares': shares_col,
            }
            try:
                out, stats = process_one(df, track_row, cols, top_n=int(top_n), window_days=int(window_days))
                summaries.append({
                    'File': f.name,
                    'Track': track_row.get(track_artist),
                    'Original Rows': stats['original'],
                    'After Country': stats['country'],
                    'After Date': stats['date'],
                    'Selected': stats['selected'],
                    'Status': 'OK'
                })
                all_outputs.append(out)
            except Exception as e:
                summaries.append({'File': f.name, 'Track': track_row.get(track_artist), 'Status': f'Error: {e}'})
            progress.progress((i + 1) / len(file_data))

        if not all_outputs:
            st.error('No outputs generated.')
            st.dataframe(pd.DataFrame(summaries), use_container_width=True, hide_index=True)
            st.stop()

        combined = pd.concat(all_outputs, ignore_index=True)

        if fetch_saves:
            if not apify_token:
                st.warning('Apify token missing, so Saves were not fetched.')
            else:
                try:
                    status.write('Fetching Saves from Apify for selected Top rows only...')
                    combined = apply_saves(combined, apify_token)
                except Exception as e:
                    st.error(f'Apify Saves enrichment failed: {e}')

        final_df = combined[FINAL_COLUMNS].copy()

        # Make Batch Filter the first step of the full tagging workflow.
        # The filtered MelodyIQ output becomes the original report used by Upload & Tag.
        st.session_state.original_df = final_df.copy()
        st.session_state.original_url_col = 'Link'
        st.session_state.original_market_map = _build_original_market_map(final_df, 'Link', 'Country')
        st.session_state.batch_filter_df = final_df.copy()

        status.empty()
        progress.empty()

        st.success(f'Done. Output rows: {len(final_df)}')
        st.markdown(
            "<div class='info-banner'>Filtered MelodyIQ rows are now loaded as the source report for <strong>Upload &amp; Tag</strong>. Continue there to run Apify + AI tagging.</div>",
            unsafe_allow_html=True
        )
        if st.button('Continue to Upload & Tag', type='primary', use_container_width=True, key='batch_continue_upload_tag'):
            st.session_state.page = 'Upload & Tag'
            st.rerun()
        st.markdown('<div class="section-card"><span class="step-badge">Results</span><h3 style="margin-top:0">Processing summary</h3>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(summaries), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.subheader('Preview')
        st.dataframe(final_df.head(50), use_container_width=True, hide_index=True)

        csv_bytes = final_df.to_csv(index=False).encode('utf-8-sig')
        xlsx_bytes = to_excel_bytes(final_df)

        d1, d2 = st.columns(2)
        with d1:
            st.download_button('Download CSV', csv_bytes, file_name='melodyiq_filtered_top20.csv', mime='text/csv', use_container_width=True)
        with d2:
            st.download_button('Download XLSX', xlsx_bytes, file_name='melodyiq_filtered_top20.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)

# ══════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════
elif page == "Export":
    st.markdown("""
    <div class='page-header'>
        <h1>Export</h1>
        <p>Upload your MelodyIQ report to append AI tags and download the final CSV</p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.master_df.empty:
        st.info("No data loaded yet.")
        st.stop()

    df      = st.session_state.master_df
    total   = len(df)
    flagged = int(df['needs_human_review'].sum())
    done    = total - flagged

    st.markdown(f"""
    <div class='metric-row'>
        <div class='metric-card'><div class='val'>{total}</div><div class='lbl'>Total Rows</div></div>
        <div class='metric-card'><div class='val green'>{done}</div><div class='lbl'>Complete</div></div>
        <div class='metric-card'><div class='val amber'>{flagged}</div><div class='lbl'>Still Flagged</div></div>
    </div>
    """, unsafe_allow_html=True)

    if flagged > 0:
        st.markdown(f"<div class='warn-banner'>⚠️ {flagged} row(s) still flagged — tag them in Review Flagged first, or they will export with empty tag fields.</div>", unsafe_allow_html=True)

    export_base_df = df[df.get('review_action', pd.Series([''] * len(df), index=df.index)).fillna('') != 'REMOVE'].copy()
    removed_count = len(df) - len(export_base_df)
    if removed_count > 0:
        st.markdown(f"<div class='info-banner'>ℹ️ {removed_count} post(s) marked Remove / Ignore will be excluded from the final export.</div>", unsafe_allow_html=True)

    export_df = export_base_df.sort_values(
        ['market', 'track', 'needs_human_review'],
        ascending=[True, True, False]
    )

    # ── MelodyIQ / Original Spreadsheet merge ─────────────────────────────
    st.markdown("""
    <div class='section-card'>
        <h3>Merge Back to Original Spreadsheet</h3>
        <p style='font-size:13px;color:#64748b;margin:0 0 16px'>
            Upload the original MelodyIQ / tracking report. The app will match rows by TikTok <strong>video ID</strong>
            extracted from <strong>Link</strong>, with normalized URL fallback, and append the AI-generated
            <strong>Narrative</strong>, <strong>Creative Type</strong>, and
            <strong>Content Details</strong> columns while preserving the original file structure.
        </p>
    """, unsafe_allow_html=True)

    melody_file = st.file_uploader(
        "Upload original CSV / XLSX report (optional if already uploaded on Upload & Tag)",
        type=["csv", "xlsx", "xls"],
        key="melody_uploader"
    )

    def _norm_url_for_merge(v):
        """Normalize TikTok URLs enough for fallback matching without changing display values."""
        if pd.isna(v):
            return ""
        s = str(v).strip()
        if not s or s.lower() in {"nan", "none", "null"}:
            return ""
        s = s.split("?")[0].strip().rstrip("/")
        # Convert mobile/short domain variants only when obvious.
        s = s.replace("https://m.tiktok.com/", "https://www.tiktok.com/")
        s = s.replace("http://m.tiktok.com/", "https://www.tiktok.com/")
        s = s.replace("http://www.tiktok.com/", "https://www.tiktok.com/")
        return s

    def _extract_tiktok_video_id(v):
        """Extract stable TikTok video ID from URL-like text.

        Full URL strings can differ between MelodyIQ and scraper output
        because of query params, mobile domains, or submitted/web URL fields.
        The numeric TikTok video ID is the most reliable merge key.
        """
        if pd.isna(v):
            return ""
        s = str(v).strip()
        if not s or s.lower() in {"nan", "none", "null"}:
            return ""

        m = re.search(r"/video/(\d+)", s)
        if m:
            return m.group(1)

        for pat in [r"[?&](?:item_id|share_item_id|aweme_id|modal_id)=(\d+)", r"(?:item_id|share_item_id|aweme_id|modal_id)[=:](\d+)"]:
            m = re.search(pat, s)
            if m:
                return m.group(1)

        if re.fullmatch(r"\d{10,}", s):
            return s
        return ""

    def _merge_key_from_url_or_id(url_val, id_val=""):
        """Prefer TikTok video ID; fallback to normalized URL for unusual cases."""
        vid = _extract_tiktok_video_id(url_val) or _extract_tiktok_video_id(id_val)
        if vid:
            return f"video:{vid}"
        norm = _norm_url_for_merge(url_val)
        return f"url:{norm}" if norm else ""

    def _read_original_report(uploaded_file):
        name = uploaded_file.name.lower()
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file), "csv"
        return pd.read_excel(uploaded_file), "xlsx"

    # Final Excel export must keep the Batch Filter workbook structure.
    # It should NOT create a single random "Tagged Output" sheet.
    # It writes All Post Data first, then market tabs in the exact order:
    # (MY), (PH), (SG), (TH), (VN), (KR).
    # Row order from the source Batch Filter output is preserved; the only
    # structural change is adding/updating Narrative, Creative Type and
    # Content Details.
    FINAL_MARKET_ORDER = ['MY', 'PH', 'SG', 'TH', 'VN', 'KR']

    def _export_country_code(v):
        s = str(v or '').strip()
        sl = s.lower()
        aliases = {
            'my': 'MY', 'malaysia': 'MY',
            'ph': 'PH', 'philippines': 'PH',
            'sg': 'SG', 'singapore': 'SG',
            'th': 'TH', 'thailand': 'TH',
            'vn': 'VN', 'vietnam': 'VN', 'viet nam': 'VN',
            'kr': 'KR', 'korea': 'KR', 'south korea': 'KR', 'kor': 'KR',
        }
        return aliases.get(sl, s)

    def _format_export_sheet(writer, sheet_name):
        ws = writer.sheets[sheet_name]
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for col_cells in ws.columns:
            header = str(col_cells[0].value or '')
            max_len = len(header)
            for cell in col_cells[1:]:
                max_len = max(max_len, len(str(cell.value or '')))
            ws.column_dimensions[col_cells[0].column_letter].width = min(max(max_len + 2, 10), 45)

    def _to_excel_bytes(out_df):
        buffer = io.BytesIO()

        work = out_df.copy()
        if 'Country' in work.columns:
            work['_export_market_code'] = work['Country'].apply(_export_country_code)
        elif 'market' in work.columns:
            work['_export_market_code'] = work['market'].apply(_export_country_code)
        else:
            work['_export_market_code'] = ''

        helper_cols = ['_export_market_code']
        clean_all = work.drop(columns=helper_cols, errors='ignore')

        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Preserve the source row order exactly for All Post Data.
            clean_all.to_excel(writer, index=False, sheet_name='All Post Data')
            _format_export_sheet(writer, 'All Post Data')

            # Always create market tabs in this exact order. Empty markets still
            # get a tab with headers so the workbook layout is stable.
            for code in FINAL_MARKET_ORDER:
                tab_df = work[work['_export_market_code'] == code].drop(columns=helper_cols, errors='ignore')
                sheet_name = f'({code}) Post Data'
                tab_df.to_excel(writer, index=False, sheet_name=sheet_name)
                _format_export_sheet(writer, sheet_name)

        return buffer.getvalue()

    if melody_file or not st.session_state.original_df.empty:
        try:
            if melody_file:
                melody_df, file_kind = _read_original_report(melody_file)
            else:
                melody_df, file_kind = st.session_state.original_df.copy(), 'session_original'

            # Auto-detect URL column. The team's file normally uses "Link".
            url_col = None
            for candidate in [
                'Link', 'link', 'TikTok Link', 'Tiktok Link', 'URL', 'url',
                'Video URL', 'video_url', 'tiktok_url', 'submittedVideoUrl', 'webVideoUrl'
            ]:
                if candidate in melody_df.columns:
                    url_col = candidate
                    break

            if url_col is None and st.session_state.get('original_url_col') in melody_df.columns:
                url_col = st.session_state.get('original_url_col')

            if url_col is None:
                st.error(f"Could not find a URL column. Available columns: {', '.join(melody_df.columns.astype(str).tolist())}")
            else:
                # Build AI output lookup from the tagged JSON/App results.
                ai_cols = export_df.copy()
                ai_cols['merge_key'] = ai_cols.apply(lambda r: _merge_key_from_url_or_id(r.get('tiktok_url', ''), r.get('id', '')), axis=1)
                ai_cols = ai_cols[ai_cols['merge_key'] != ''].copy()

                # If the same TikTok video appears more than once, keep the first non-flagged / highest-confidence row.
                sort_cols = []
                if 'needs_human_review' in ai_cols.columns:
                    ai_cols['_review_sort'] = ai_cols['needs_human_review'].astype(int)
                    sort_cols.append('_review_sort')
                if 'confidence' in ai_cols.columns:
                    ai_cols['_confidence_sort'] = pd.to_numeric(ai_cols['confidence'], errors='coerce').fillna(0)
                    ai_cols = ai_cols.sort_values(sort_cols + ['_confidence_sort'], ascending=[True]*len(sort_cols) + [False])
                ai_lookup = ai_cols.drop_duplicates('merge_key', keep='first').set_index('merge_key')

                out_df = melody_df.copy()
                out_df['_merge_key'] = out_df[url_col].apply(lambda v: _merge_key_from_url_or_id(v))

                # Reviewer removals should be removed from the final workbook, not just left blank.
                # Example: POST_NOT_FOUND_OR_PRIVATE rows that the reviewer chose to ignore.
                removed_keys = set()
                try:
                    removed_source = df[df.get('review_action', pd.Series([''] * len(df), index=df.index)).fillna('') == 'REMOVE'].copy()
                    if not removed_source.empty:
                        removed_source['_merge_key'] = removed_source.apply(
                            lambda r: _merge_key_from_url_or_id(r.get('tiktok_url', ''), r.get('id', '')),
                            axis=1
                        )
                        removed_keys = set(removed_source.loc[removed_source['_merge_key'] != '', '_merge_key'].astype(str))
                except Exception:
                    removed_keys = set()

                removed_original_mask = out_df['_merge_key'].astype(str).isin(removed_keys) & (out_df['_merge_key'] != '')
                removed_original_count = int(removed_original_mask.sum())
                if removed_original_count > 0:
                    out_df = out_df.loc[~removed_original_mask].copy()

                # Add/overwrite only the three tagging columns. If they already exist, update them.
                tag_cols = ['Narrative', 'Creative Type', 'Content Details']
                for col in tag_cols:
                    if col not in out_df.columns:
                        out_df[col] = ""
                    if col in ai_lookup.columns:
                        mapped = out_df['_merge_key'].map(ai_lookup[col])
                        # Update only matched values, preserve existing original values for unmatched rows.
                        out_df[col] = mapped.combine_first(out_df[col])

                # Optional QA fields for internal checking only.
                include_qa = st.checkbox(
                    "Include QA columns (confidence, tier, validation status)",
                    value=False,
                    help="Leave unchecked for the clean final tagging file."
                )
                qa_cols = {
                    'AI Confidence': 'confidence',
                    'AI Tier Used': 'tier_used',
                    'AI Validation Status': 'validation_status',
                    'AI Needs Review': 'needs_human_review'
                }
                if include_qa:
                    for out_col, src_col in qa_cols.items():
                        if src_col in ai_lookup.columns:
                            out_df[out_col] = out_df['_merge_key'].map(ai_lookup[src_col])

                matched_mask = out_df['_merge_key'].isin(ai_lookup.index) & (out_df['_merge_key'] != '')
                matched = int(matched_mask.sum())
                unmatched_mask = (out_df['_merge_key'] != '') & (~matched_mask)
                unmatched = int(unmatched_mask.sum())
                blank_url = int((out_df['_merge_key'] == '').sum())

                matched_keys = out_df.loc[matched_mask, '_merge_key'].astype(str)
                matched_video = int(matched_keys.str.startswith('video:').sum())
                matched_url_fallback = int(matched_keys.str.startswith('url:').sum())

                original_keys = set(out_df.loc[out_df['_merge_key'] != '', '_merge_key'].astype(str))
                ai_keys = set(ai_lookup.index.astype(str))
                tagged_not_in_original = len(ai_keys - original_keys - removed_keys)

                unmatched_preview = out_df.loc[unmatched_mask, [url_col, '_merge_key']].head(20).copy()
                unmatched_preview = unmatched_preview.rename(columns={url_col: 'Original Link', '_merge_key': 'Merge Key'})

                # Scraper coverage diagnostics: separate scraper acquisition gaps from merge problems.
                # Missing from scraper = original links that have no returned JSON/app result after removals.
                coverage_original_linked = int((out_df['_merge_key'] != '').sum())
                coverage_scraped_or_reviewed = matched
                coverage_missing = unmatched
                coverage_blank_links = blank_url
                coverage_removed = removed_original_count
                coverage_json_rows = int(len(ai_lookup))

                scraper_error_count = 0
                scraper_error_preview = pd.DataFrame()
                try:
                    error_mask = (
                        ai_lookup.get('tier_used', pd.Series('', index=ai_lookup.index)).fillna('').astype(str).str.contains('scraper_exception', case=False, na=False)
                        | ai_lookup.get('reasoning', pd.Series('', index=ai_lookup.index)).fillna('').astype(str).str.contains('POST_NOT_FOUND|PRIVATE|unavailable|scraper', case=False, na=False)
                        | ai_lookup.get('validation_issues', pd.Series('', index=ai_lookup.index)).fillna('').astype(str).str.contains('POST_NOT_FOUND|PRIVATE|unavailable|scraper', case=False, na=False)
                    )
                    scraper_error_count = int(error_mask.sum())
                    error_cols = [c for c in ['track', 'market', 'tiktok_url', 'reasoning', 'validation_issues'] if c in ai_lookup.columns]
                    if error_cols:
                        scraper_error_preview = ai_lookup.loc[error_mask, error_cols].reset_index(drop=True).head(20)
                except Exception:
                    scraper_error_count = 0
                    scraper_error_preview = pd.DataFrame()

                out_df = out_df.drop(columns=['_merge_key'])

                # Reposition the three tag columns after Province if possible, otherwise after Link.
                cols = list(out_df.columns)
                for c in tag_cols:
                    if c in cols:
                        cols.remove(c)
                insert_after = 'Province' if 'Province' in cols else url_col
                insert_at = cols.index(insert_after) + 1 if insert_after in cols else len(cols)
                cols = cols[:insert_at] + tag_cols + cols[insert_at:]
                out_df = out_df[cols]

                st.markdown("<div style='margin-top:10px'><h4 style='color:#1e1b4b;margin:0 0 10px;font-size:14px'>Scraper Coverage Check</h4></div>", unsafe_allow_html=True)
                st.markdown(f"""
                <div class='metric-row' style='margin-top:8px'>
                    <div class='metric-card'><div class='val'>{coverage_original_linked}</div><div class='lbl'>Original Linked Rows</div></div>
                    <div class='metric-card'><div class='val green'>{coverage_scraped_or_reviewed}</div><div class='lbl'>Returned / Matched</div></div>
                    <div class='metric-card'><div class='val amber'>{coverage_missing}</div><div class='lbl'>Missing from Scraper</div></div>
                    <div class='metric-card'><div class='val'>{scraper_error_count}</div><div class='lbl'>Scraper Error Rows</div></div>
                    <div class='metric-card'><div class='val'>{coverage_removed}</div><div class='lbl'>Removed by Reviewer</div></div>
                    <div class='metric-card'><div class='val'>{len(out_df)}</div><div class='lbl'>Final Export Rows</div></div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<div style='margin-top:10px'><h4 style='color:#1e1b4b;margin:0 0 10px;font-size:14px'>Merge Diagnostics</h4></div>", unsafe_allow_html=True)
                st.markdown(f"""
                <div class='metric-row' style='margin-top:8px'>
                    <div class='metric-card'><div class='val'>{len(out_df)}</div><div class='lbl'>Original Rows After Removal</div></div>
                    <div class='metric-card'><div class='val green'>{matched}</div><div class='lbl'>Matched Total</div></div>
                    <div class='metric-card'><div class='val indigo'>{matched_video}</div><div class='lbl'>Matched by Video ID</div></div>
                    <div class='metric-card'><div class='val'>{matched_url_fallback}</div><div class='lbl'>URL Fallback</div></div>
                    <div class='metric-card'><div class='val amber'>{unmatched}</div><div class='lbl'>Unmatched Original Links</div></div>
                    <div class='metric-card'><div class='val'>{blank_url}</div><div class='lbl'>Blank Links</div></div>
                </div>
                """, unsafe_allow_html=True)

                if scraper_error_count > 0 and not scraper_error_preview.empty:
                    with st.expander("Show scraper error rows", expanded=False):
                        st.dataframe(scraper_error_preview, use_container_width=True, hide_index=True)

                if coverage_removed > 0:
                    st.caption(f"{coverage_removed} original row(s) were removed from the final export because they were marked Remove / Ignore in Review.")

                if tagged_not_in_original > 0:
                    st.caption(f"Note: {tagged_not_in_original} tagged JSON row(s) were not found in the uploaded original workbook. This is okay if you uploaded extra JSONs.")

                if unmatched > 0:
                    st.markdown(f"<div class='warn-banner'>⚠️ {unmatched} linked row(s) in the original workbook had no matching TikTok video ID / URL in the tagged JSON output. They will keep blank tag columns.</div>", unsafe_allow_html=True)
                    with st.expander("Show unmatched original links", expanded=False):
                        st.dataframe(unmatched_preview, use_container_width=True, hide_index=True)

                c1, c2 = st.columns(2)
                with c1:
                    csv_bytes = out_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        "⬇ Download Final CSV",
                        data=csv_bytes,
                        file_name="final_tagged_melodyiq.csv",
                        mime="text/csv",
                        type="primary",
                        use_container_width=True,
                    )
                with c2:
                    xlsx_bytes = _to_excel_bytes(out_df)
                    st.download_button(
                        "⬇ Download Final XLSX",
                        data=xlsx_bytes,
                        file_name="final_tagged_melodyiq.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

                st.markdown("<div style='margin-top:16px'><p style='font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.05em'>Preview — first 10 rows</p></div>", unsafe_allow_html=True)
                preview_cols = [c for c in [url_col, 'Narrative', 'Creative Type', 'Content Details'] if c in out_df.columns]
                st.dataframe(out_df[preview_cols].head(10), use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Merge failed: {e}")

    st.markdown("</div>", unsafe_allow_html=True)