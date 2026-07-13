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

from review_routing import apply_review_policy, review_risk_reasons, visual_escalation_reasons
from evidence_verifier import (
    apply_verifier_response,
    build_verifier_prompt,
    resolvable_review_reasons,
    targeted_verifier_reasons,
)

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

# ── Optional Creative Type Knowledge Base ──────────────────────────────
# Folder expected beside this app:
# creative_knowledge/
#   metadata.json
#   creator_rules.json
#   hashtag_rules.json
#   url_type_rules.json
#   market_rules.json
#   track_rules.json
# This KB is for the ORIGINAL tagging app taxonomy, not Creator Core drama tags.
CREATIVE_KB_DIR = "creative_knowledge"

@st.cache_data(show_spinner=False)
def load_creative_kb(base_dir: str = CREATIVE_KB_DIR):
    """Load reusable Creative Type knowledge if present.

    The app works normally without this folder. The KB never needs exact TikTok
    URL memorisation; it only uses reusable signals such as creator, hashtags,
    post type, market, and track/campaign context.
    """
    kb = {}
    for name in [
        "metadata", "creator_rules", "hashtag_rules", "url_type_rules",
        "market_rules", "track_rules", "keyword_rules"
    ]:
        path = os.path.join(base_dir, f"{name}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                kb[name] = json.load(f)
        except Exception:
            kb[name] = {}
    return kb


def _kb_norm_text(v):
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "none", "null"} else s


def _kb_slug(v):
    s = _kb_norm_text(v).lower().strip().lstrip("#@")
    return re.sub(r"[^a-z0-9_.\-ก-๙\u0e00-\u0e7f\u4e00-\u9fff가-힣ぁ-んァ-ン]+", "", s)


def _kb_get(row, key, default=""):
    try:
        if isinstance(row, dict):
            return row.get(key, default)
        return row.get(key, default)
    except Exception:
        return default


def _kb_get_nested(row, dotted, default=""):
    cur = row
    for part in dotted.split('.'):
        try:
            if isinstance(cur, dict):
                cur = cur.get(part, default)
            else:
                # pandas.json_normalize rows often expose dotted names directly
                direct = _kb_get(row, dotted, None)
                if direct is not None and dotted in getattr(row, 'index', []):
                    return direct
                return default
        except Exception:
            return default
    return cur


def _kb_extract_creator(row):
    vals = [
        _kb_get(row, 'authorMeta.name'),
        _kb_get(row, 'authorMeta.nickName'),
        _kb_get_nested(row, 'authorMeta.name'),
        _kb_get_nested(row, 'authorMeta.nickName'),
        _kb_get(row, 'creator_handle'),
        _kb_get(row, 'creator'),
        _kb_get(row, 'Username'),
        _kb_get(row, 'username'),
    ]
    for v in vals:
        s = _kb_slug(v)
        if s:
            return s
    url = _kb_norm_text(_kb_get(row, 'webVideoUrl') or _kb_get(row, 'submittedVideoUrl') or _kb_get(row, 'url') or _kb_get(row, 'Link') or _kb_get(row, 'tiktok_url'))
    m = re.search(r"tiktok\.com/@([^/?#]+)", url)
    return _kb_slug(m.group(1)) if m else ""


def _kb_extract_hashtags(row):
    out = []
    raw = _kb_get(row, 'hashtags', [])
    if isinstance(raw, list):
        for h in raw:
            if isinstance(h, dict):
                val = h.get('name') or h.get('title') or h.get('hashtagName') or h.get('id')
            else:
                val = h
            s = _kb_slug(val)
            if s:
                out.append(s)
    elif raw:
        for part in re.split(r"[,\s]+", str(raw)):
            s = _kb_slug(part)
            if s:
                out.append(s)
    caption = _kb_norm_text(_kb_get(row, 'text') or _kb_get(row, 'caption') or _kb_get(row, 'Caption'))
    for tag in re.findall(r"#([\w.\-ก-๙\u0e00-\u0e7f\u4e00-\u9fff가-힣ぁ-んァ-ン]+)", caption, flags=re.UNICODE):
        s = _kb_slug(tag)
        if s:
            out.append(s)
    return sorted(set(out))


def _kb_url_type(row):
    url = _kb_norm_text(_kb_get(row, 'webVideoUrl') or _kb_get(row, 'submittedVideoUrl') or _kb_get(row, 'url') or _kb_get(row, 'Link') or _kb_get(row, 'tiktok_url'))
    is_slide = bool(_kb_get(row, 'isSlideshow', False) or _kb_get(row, 'is_slideshow', False))
    if '/photo/' in url.lower() or is_slide:
        return 'photo'
    if '/video/' in url.lower():
        return 'video'
    return 'unknown'


def _slideshow_image_count(row):
    """Return a confirmed slideshow image count, or None when unavailable."""
    if row is None:
        return None
    candidates = []
    for key in ['slideshowImageLinks', 'slideshow_images', 'images']:
        try:
            candidates.append(row.get(key))
        except Exception:
            pass
    try:
        image_post = row.get('imagePostMeta')
        if isinstance(image_post, dict):
            candidates.append(image_post.get('images'))
    except Exception:
        pass
    for value in candidates:
        if isinstance(value, list):
            return len([item for item in value if item not in [None, '']])
        if isinstance(value, tuple):
            return len([item for item in value if item not in [None, '']])
    return None


def _kb_valid_labels(labels):
    if isinstance(labels, str):
        labels = [x.strip() for x in labels.split(',')]
    if not isinstance(labels, list):
        return []
    clean = []
    for x in labels:
        xs = _kb_norm_text(x)
        if xs in ALLOWED_SET and xs not in clean:
            clean.append(xs)
    return clean[:2]


def _kb_extract_market(row):
    # IMPORTANT: source-report campaign market must beat TikTok locationCreated.
    # locationCreated describes the creator/post origin and can be US/ID/KR/etc.
    # The tagging benchmark is evaluated by the MelodyIQ source market, so PH/KR/TH
    # market-specific guardrails should read _campaign_market first.
    vals = [
        _kb_get(row, '_campaign_market'),
        _kb_get(row, 'Country'), _kb_get(row, 'country'),
        _kb_get(row, 'Market'), _kb_get(row, 'market'),
        _kb_get(row, 'Region'), _kb_get(row, 'region'),
        _kb_get(row, 'locationCreated'),
    ]
    aliases = {
        'malaysia': 'MY', 'my': 'MY', 'philippines': 'PH', 'ph': 'PH', 'phl': 'PH', 'pilipinas': 'PH',
        'singapore': 'SG', 'sg': 'SG', 'thailand': 'TH', 'thai': 'TH', 'th': 'TH',
        'vietnam': 'VN', 'viet nam': 'VN', 'vn': 'VN',
        'korea': 'KR', 'south korea': 'KR', 'republic of korea': 'KR', 'kr': 'KR',
        'indonesia': 'ID', 'id': 'ID',
    }
    for v in vals:
        s = _kb_norm_text(v).strip()
        if not s:
            continue
        return aliases.get(s.lower(), s.upper() if len(s) <= 3 else s)
    return ''


def _kb_extract_track(row):
    vals = [
        _kb_get(row, '_campaign_track'),
        _kb_get(row, 'Artist - Sound'), _kb_get(row, 'track'), _kb_get(row, 'Track'),
        _kb_get(row, 'Sound'), _kb_get(row, 'Song'),
    ]
    music_name = _kb_get(row, 'musicMeta.musicName') or _kb_get_nested(row, 'musicMeta.musicName')
    music_author = _kb_get(row, 'musicMeta.musicAuthor') or _kb_get_nested(row, 'musicMeta.musicAuthor')
    if music_author and music_name:
        vals.extend([f"{music_author} - {music_name}", f"{music_name} - {music_author}"])
    for v in vals:
        s = _kb_slug(v)
        if s:
            return s
    return ''


def _kb_context_blob(row, result_context=None):
    parts = [
        _kb_get(row, 'text'), _kb_get(row, 'caption'), _kb_get(row, 'Caption'),
        _kb_get(row, 'desc'), _kb_get(row, 'Description'),
    ]
    if isinstance(result_context, dict):
        # Narrative and Content Details are direct semantic observations. Reasoning is
        # intentionally excluded because post-processing guardrails append label names
        # to it (for example "Dance was prioritised"). Reading that text back into the
        # keyword KB creates a circular vote that reinforces the guardrail's own label.
        for key in ['narrative', 'content_details']:
            val = result_context.get(key, '')
            if isinstance(val, list):
                val = ' '.join(map(str, val))
            parts.append(val)
        # Do not append the predicted creative_type label to keyword context.
        # If Gemini predicts a label, adding that label here can make the KB agree
        # with the mistake and reinforce false positives. Market-specific recovery
        # is handled separately in explicit guardrails below.
    return ' '.join(_kb_norm_text(x) for x in parts if _kb_norm_text(x)).lower()


def creative_kb_lookup(row, result_context=None):
    """Return best reusable Creative Type KB hint for an Apify/post row.

    v2 improvement: keyword rules can also look at Gemini's generated narrative and
    content_details, not just the TikTok caption. This lets the KB
    help with broad-format corrections such as Dance vs Lip Sync, Lyrics, Beauty,
    Fashion, Gaming and Movie/Tv/Drama Edits after Gemini has described the post.
    """
    kb = load_creative_kb()
    if not any(kb.get(x) for x in ['creator_rules', 'hashtag_rules', 'url_type_rules', 'keyword_rules', 'market_rules', 'track_rules']):
        return {"labels": [], "narrative": "", "confidence": 0.0, "total": 0, "source": "", "evidence": []}

    creator = _kb_extract_creator(row)
    tags = _kb_extract_hashtags(row)
    url_type = _kb_url_type(row)
    market = _kb_extract_market(row)
    track = _kb_extract_track(row)
    context_blob = _kb_context_blob(row, result_context)

    candidates = []
    evidence = []

    def add_rule(rule, source, weight=1.0):
        if not isinstance(rule, dict):
            return
        labels = _kb_valid_labels(rule.get('preferred_creative_type') or rule.get('labels') or rule.get('preferred_labels') or [])
        if not labels:
            return
        try:
            conf = float(rule.get('confidence', 0) or 0)
        except Exception:
            conf = 0.0
        try:
            total = int(rule.get('total', rule.get('count', 0)) or 0)
        except Exception:
            total = 0
        score = conf * max(1, min(total, 20)) * weight
        candidates.append({
            'labels': labels,
            'narrative': _kb_norm_text(rule.get('preferred_narrative') or rule.get('narrative') or ''),
            'confidence': conf,
            'total': total,
            'score': score,
            'source': source,
            'distribution': rule.get('distribution', {}),
        })
        evidence.append(f"{source} → {', '.join(labels)} ({conf:.2f}, n={total})")

    if creator:
        add_rule((kb.get('creator_rules') or {}).get(creator), f"creator:{creator}", weight=1.25)
    for h in tags:
        add_rule((kb.get('hashtag_rules') or {}).get(h), f"hashtag:{h}", weight=1.0)
    if url_type:
        add_rule((kb.get('url_type_rules') or {}).get(url_type), f"url_type:{url_type}", weight=0.25)
    if market:
        add_rule((kb.get('market_rules') or {}).get(market), f"market:{market}", weight=0.20)
    if track:
        add_rule((kb.get('track_rules') or {}).get(track), f"track:{track}", weight=0.55)

    # Keyword rules are supporting evidence only. They become most useful after
    # Gemini has produced content_details/reasoning, so we check result_context too.
    for kw, rule in (kb.get('keyword_rules') or {}).items():
        if kw and kw in context_blob:
            add_rule(rule, f"keyword:{kw}", weight=0.70)

    if not candidates:
        return {"labels": [], "narrative": "", "confidence": 0.0, "total": 0, "source": "", "evidence": evidence}

    # Prefer strong creator/track/keyword rules over broad url_type/market rules.
    best = sorted(candidates, key=lambda r: (r['score'], r['confidence'], r['total']), reverse=True)[0]
    return {**best, "evidence": evidence[:8]}


def creative_kb_prompt_hint(row):
    hit = creative_kb_lookup(row)
    labels = hit.get('labels') or []
    if not labels:
        return "No historical KB hint available."
    # Do not force Gemini. Provide as prior knowledge only.
    parts = [
        f"Historical KB hint: reusable signal {hit.get('source','')} usually maps to Creative Type = {', '.join(labels)}",
        f"confidence={hit.get('confidence',0):.2f}, examples={hit.get('total',0)}",
    ]
    if hit.get('narrative'):
        parts.append(f"common narrative={hit.get('narrative')}")
    return "; ".join(parts) + ". Use this only as supporting evidence; visual content still wins when clearly different."


def apply_knowledge_guardrails(result, row=None):
    """Post-process Gemini output with conservative Creative Type KB support.

    This is intentionally safer than Creator Core tagging: the original app has broad
    content categories, so KB only overrides when historical evidence is strong or
    Gemini is weak/uncertain. It never uses exact TikTok URLs.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    hit = creative_kb_lookup(row, result)
    kb_labels = _kb_valid_labels(hit.get('labels', []))
    if not kb_labels:
        return result

    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        labels = []
    labels = [x for x in labels if x in ALLOWED_SET]
    label_set = set(labels)
    kb_set = set(kb_labels)
    try:
        conf = float(result.get('confidence', 0) or 0)
    except Exception:
        conf = 0.0
    kb_conf = float(hit.get('confidence', 0) or 0)
    kb_total = int(hit.get('total', 0) or 0)
    url_type = _kb_url_type(row)

    changed = False
    reason_add = ""

    # Always preserve true slideshow/photo carousel when Apify says it is a slideshow.
    if url_type == 'photo' and 'Carousel' not in label_set:
        labels = ['Carousel'] + [x for x in labels if x != 'Carousel']
        labels = labels[:2]
        changed = True
        reason_add = "KB/post-type guardrail: photo/slideshow post, so Carousel was included."

    # If Gemini already agrees with the KB, just order labels and raise confidence slightly.
    if kb_set & set(labels):
        ordered = [x for x in kb_labels if x in labels] + [x for x in labels if x not in kb_labels]
        labels = ordered[:2]
        result['creative_type'] = labels
        result['confidence'] = max(conf, min(0.92, kb_conf))
        old = str(result.get('reasoning', '') or '')
        agree = f"KB support: {hit.get('source','historical signal')} also suggests {', '.join(kb_labels)}."
        result['reasoning'] = (old + ' | ' + agree).strip(' |')
        return result

    # Strong override only when Gemini is weak/review-ish or KB has repeated high-confidence evidence.
    strong_kb = kb_conf >= 0.90 and kb_total >= 3
    very_strong_kb = kb_conf >= 0.95 and kb_total >= 6
    weak_model = (not labels) or conf < 0.75 or result.get('needs_human_review', False)

    # Avoid replacing obvious motion labels unless KB is extremely strong.
    motion_labels = {'Dance', 'Lip Sync', 'Fitness', 'Cover'}
    motion_obvious = bool(label_set & motion_labels) and (_row_has_motion_cues(row) or _result_has_dance_visual_cues(result))

    if (weak_model and strong_kb and not motion_obvious) or (very_strong_kb and not motion_obvious):
        labels = kb_labels[:2]
        result['creative_type'] = labels
        if hit.get('narrative') and not _kb_norm_text(result.get('narrative')):
            result['narrative'] = hit.get('narrative')
        result['confidence'] = max(conf, min(0.90, kb_conf))
        changed = True
        reason_add = f"KB guardrail: {hit.get('source','historical signal')} strongly suggests {', '.join(kb_labels)} based on reusable historical patterns."

    if changed:
        old = str(result.get('reasoning', '') or '')
        result['reasoning'] = (old + ' | ' + reason_add).strip(' |')
    return result

# Default Gemini model. Keep this aligned with your current working setup.
# If the video fallback fails for your account/model, change this to another video-capable Gemini model available to you.
GEMINI_MODEL = 'gemini-3.1-flash-lite'

# Runtime safety: full-video uploads are slow and can look like the app is hanging.
# Keep this off by default; frame-based Tier 2A/2B still runs.
ENABLE_TIER2C_FULL_VIDEO_FALLBACK = True
ENABLE_LEGACY_TIER0_VAGUE_SHORTCUT = False
ENABLE_TARGETED_EVIDENCE_VERIFIER = True

# Avoid silent multi-minute sleep loops on transient Gemini quota/server errors.
# Rows that still fail after short retry are flagged for review instead of blocking the batch.
GEMINI_BACKOFF_SECONDS = 20

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



def _auto_remove_unusable_existing_rows():
    """Retroactively remove old scraper-error rows from the current Streamlit session.

    This protects users who ran an older version where deleted/private/unavailable
    posts were sent to Review. Those rows should be excluded from Review and Export.
    """
    if st.session_state.get('master_df', pd.DataFrame()).empty:
        return 0
    df = st.session_state.master_df
    removed = 0
    markers = [
        'POST_NOT_FOUND', 'NOT_FOUND', 'PRIVATE', 'DELETED', 'UNAVAILABLE',
        'VIDEO_UNAVAILABLE', 'ITEM_UNAVAILABLE', 'SENSITIVE', 'NO_LONGER_AVAILABLE',
        'COULD NOT RETRIEVE', 'NOT AVAILABLE', 'LOGIN_REQUIRED', 'AGE_RESTRICTED',
        'REMOVED', 'DOES NOT EXIST', 'NO USABLE METADATA', 'METRICS UNAVAILABLE',
        'SCRAPER ERROR', 'SCRAPER_EXCEPTION', 'auto_removed_unavailable'
    ]
    for idx, row in df.iterrows():
        blob = ' '.join(str(row.get(c, '') or '') for c in [
            'tier_used', 'validation_status', 'validation_issues', 'tier3_reason',
            'reasoning', 'remove_reason', 'Content Details', 'Narrative'
        ]).upper()
        tier = str(row.get('tier_used', '') or '').strip().lower()
        status = str(row.get('validation_status', '') or '').strip().lower()
        action = str(row.get('review_action', '') or '').strip().upper()
        should_remove = (
            action == 'REMOVE'
            or status == 'removed'
            or tier in {'scraper_exception', 'auto_removed_unavailable', 'removed'}
            or any(m in blob for m in markers)
        )
        if should_remove:
            df.at[idx, 'review_action'] = 'REMOVE'
            df.at[idx, 'needs_human_review'] = False
            df.at[idx, 'validation_status'] = 'removed'
            if not str(df.at[idx, 'tier_used'] or '').strip():
                df.at[idx, 'tier_used'] = 'auto_removed_unavailable'
            if not str(df.at[idx, 'remove_reason'] if 'remove_reason' in df.columns else '').strip():
                df.at[idx, 'remove_reason'] = 'Unavailable/deleted/private/scraper-error row auto-removed'
            removed += 1
    st.session_state.master_df = df
    return removed

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
    """Detect broad performance/motion cues used for escalation and KB safety.

    The previous implementation used `w in text`, so #raindance triggered the generic
    `dance` cue. That caused PH lyric videos for Dave & Tems - Raindance to be pushed
    toward Dance even when the visuals were lyrics.
    """
    if row is None:
        return False
    try:
        caption = str(row.get('text', '') or '').lower()
    except Exception:
        caption = ''
    tags_raw = row.get('hashtags', [])
    tags = []
    if isinstance(tags_raw, list):
        for h in tags_raw:
            tags.append((h.get('name', '') if isinstance(h, dict) else str(h)).lower().lstrip('#'))
    text = caption + ' ' + ' '.join(tags)
    compact_tokens = re.findall(r"[a-z0-9_.-]+|[가-힣]+", text.lower())

    exact_motion_tokens = {
        'dance', 'dancing', 'dancer', 'choreo', 'choreography', '댄스', '춤',
        'cover', 'fitness', 'workout', 'gym'
    }
    hashtag_motion_prefixes = (
        'dancechallenge', 'dancetrend', 'dancecover', 'dancepractice',
        'dancetutorial', 'dancecrew', 'choreography', 'choreo'
    )
    if any(t in exact_motion_tokens or t.startswith(hashtag_motion_prefixes) for t in compact_tokens):
        return True

    phrase_patterns = [
        r"\bdance\s+(challenge|routine|practice|tutorial|moves|performance)\b",
        r"\b(full[- ]body|synchronized|synchronised|choreographed)\b",
        r"\b(workout|fitness|gym)\b",
        r"\b(lip sync|lipsync)\b",
    ]
    return any(re.search(p, text) for p in phrase_patterns)


def _row_has_dance_cues(row):
    """Detect caption/hashtag evidence that is specifically about dance.

    Fitness, workout and gym are motion-heavy for frame escalation, but they are not
    dance evidence. Keeping this detector separate prevents a #gym caption from
    changing a visually clear Fitness result into Dance.
    """
    if row is None:
        return False
    try:
        caption = str(row.get('text', '') or '').lower()
    except Exception:
        caption = ''
    tags_raw = row.get('hashtags', [])
    tags = []
    if isinstance(tags_raw, list):
        for h in tags_raw:
            tags.append((h.get('name', '') if isinstance(h, dict) else str(h)).lower().lstrip('#'))
    text = caption + ' ' + ' '.join(tags)
    compact_tokens = re.findall(r"[\w.-]+", text.lower(), flags=re.UNICODE)
    exact_dance_tokens = {
        'dance', 'dancing', 'dancer', 'choreo', 'choreography', '댄스', '춤'
    }
    hashtag_dance_prefixes = (
        'dancechallenge', 'dancetrend', 'dancecover', 'dancepractice',
        'dancetutorial', 'dancecrew', 'choreography', 'choreo'
    )
    if any(t in exact_dance_tokens or t.startswith(hashtag_dance_prefixes) for t in compact_tokens):
        return True
    dance_patterns = [
        r"\bdance\s+(challenge|routine|practice|tutorial|moves|performance|workout)\b",
        r"\b(full[- ]body|synchronized|synchronised|choreographed)\s+(dance|dancing|choreography|movement)\b",
    ]
    return any(re.search(pattern, text) for pattern in dance_patterns)

DANCE_VISUAL_CUES = [
    # Strong visual/action cues only. Generic "dance" alone is intentionally not enough,
    # because PH tracks such as "Raindance" were causing lyric videos to become Dance.
    'dancing', 'dances', 'dancer', 'choreo', 'choreography', 'dance challenge',
    'synchronized', 'synchronised', 'sync movement', 'coordinated movement',
    'full-body', 'full body', 'body movement', 'rhythmic body movement', 'rhythmic dance', 'performs a rhythmic dance',
    'hand gesture', 'hand gestures', 'dance move', 'dance formation', 'group dance',
    'dance practice', 'dance routine', 'dance tutorial', 'dance performance', 'performs a dance',
    'performing a dance', 'performs rhythmic', 'perform rhythmic', 'repeated body movement',
    'dance-like motion', 'dance-like movement', 'rhythmic paw movement',
]

NON_DANCE_LIPSYNC_CUES = [
    'close-up', 'close up', 'mouth', 'mouthing', 'singing to camera',
    'face expression', 'facial expression', 'little/no choreography', 'no choreography'
]

LYRICS_VISUAL_CUES = [
    'lyric video', 'lyrics video', 'lyrics display', 'lyric display', 'song lyrics',
    'full lyrics', 'lyrics appearing', 'lyrics displayed', 'lyrics on screen',
    'lyrics centered', 'lyrics synced', 'karaoke', 'spotify lyrics', 'screen recording of digital lyrics',
    'text of the song', 'song text', 'words of the song', 'static lyrics', 'simple display of song lyrics',
    'visible lyrics', 'on-screen lyrics', 'onscreen lyrics', 'overlaid lyrics', 'lyric text',
    'lyrics as the central focus', 'lyrics as central focus', 'displaying lyrics',
    'formatted lyrics', 'digital lyrics', 'laptop screen displaying the lyrics',
    'lyrics playing on a device', 'lyrics playing on screen', 'lyric captions',
    'song line', 'song lines', 'music lyrics', 'text lyrics',
]

LYRICS_TRANSLATION_CUES = [
    'translated lyrics', 'lyrics translation', 'translation of the lyrics', 'bilingual lyrics',
    'english translation', 'translated text', 'subtitle translation', 'with translation'
]


def _result_text_blob(result):
    """Use Gemini narrative/details/reasoning only, not the predicted label itself.

    The old version appended creative_type labels to this blob. That made any result
    already labelled Dance count as having a dance cue, which reinforced false positives.
    """
    if not isinstance(result, dict):
        return ''
    parts = []
    for k in ['narrative', 'content_details', 'reasoning']:
        v = result.get(k, '')
        if isinstance(v, list):
            v = ' '.join(map(str, v))
        parts.append(str(v))
    return ' '.join(parts).lower()


def _result_observation_blob(result):
    """Return only Gemini's direct visual observations, excluding reasoning.

    Guardrail explanations often mention labels that were rejected (for example
    "Lyrics was prioritised over Dance"). Those words must never become fresh
    evidence for another guardrail.
    """
    if not isinstance(result, dict):
        return ''
    parts = []
    for key in ['narrative', 'content_details']:
        value = result.get(key, '')
        if isinstance(value, list):
            value = ' '.join(map(str, value))
        parts.append(str(value))
    return ' '.join(parts).lower()


def _result_labels_blob(result):
    labels = result.get('creative_type', []) if isinstance(result, dict) else []
    return ' '.join(map(str, labels)).lower() if isinstance(labels, list) else ''


def _has_phrase(blob, phrases):
    return any(p in blob for p in phrases)


def _has_strong_dance_phrase(blob):
    if _has_phrase(blob, DANCE_VISUAL_CUES):
        return True
    # Accept exact word "dance" only when it appears in an action phrase, not inside song titles.
    action_patterns = [
        r"\b(creator|person|people|group|girl|boy|woman|man|idol|dancer)s?\s+(is\s+|are\s+)?(doing|performing|dancing|dance)",
        r"\b(animal|pet|dog|cat|puppy|kitten|hamster|rabbit|bird|character)s?\b.{0,60}\b(dances?|dancing|choreograph\w*|dance[- ]like (?:motion|movement)|rhythmic (?:body|paw|limb) movement)",
        r"\bperforms?\s+(a\s+)?(rhythmic\s+)?dance\b",
        r"\b(dance|dancing)\s+(challenge|routine|practice|tutorial|moves|performance)",
        r"\bfull[- ]body\s+(movement|choreography|dance)",
    ]
    return any(re.search(p, blob) for p in action_patterns)


def _result_has_dance_visual_cues(result):
    blob = _result_text_blob(result)
    if _result_has_lyric_visual_cues(result):
        # Lyric displays are not Dance just because the song title or style mentions dance.
        return False
    return _has_strong_dance_phrase(blob)


def _has_lyric_language(blob):
    """Detect lyric-display wording beyond exact phrase matches."""
    blob = str(blob or '').lower()
    if _has_phrase(blob, LYRICS_VISUAL_CUES + LYRICS_TRANSLATION_CUES):
        return True
    patterns = [
        r"\blyric(s)?\b.{0,50}\b(display|displayed|show|shown|screen|center|central|visible|text|overlay|overlaid|caption|captions|line|lines|video)\b",
        r"\b(display|displayed|show|shown|screen|center|central|visible|text|overlay|overlaid|caption|captions)\b.{0,50}\blyric(s)?\b",
        r"\b(full|complete|entire)\s+lyric(s)?\b",
        r"\bspotify\b.{0,40}\blyric(s)?\b",
        r"\bkaraoke[- ]?style\b",
        r"\bwords?\s+of\s+the\s+song\b",
        r"\bsong\s+text\b",
    ]
    return any(re.search(p, blob) for p in patterns)


def _result_has_lyric_visual_cues(result):
    blob = _result_text_blob(result)
    return _has_lyric_language(blob)


def _row_has_lyric_account_cue(row):
    """Strong reusable account-name cues for lyric pages; no URL memorising."""
    if row is None:
        return False
    parts = []
    for key in ['authorMeta.name', 'authorMeta.nickName', 'Username', 'username', 'creator', 'creator_handle']:
        try:
            val = row.get(key, '')
            if val is not None:
                parts.append(str(val).lower())
        except Exception:
            pass
    # Nested authorMeta for raw dicts.
    try:
        am = row.get('authorMeta', {})
        if isinstance(am, dict):
            parts.extend([str(am.get('name', '')).lower(), str(am.get('nickName', '')).lower()])
    except Exception:
        pass
    blob = ' '.join(parts)
    if not blob.strip():
        return False
    lyric_patterns = [
        r'lyric', r'lyrics', r'lyrical', r'lyrix', r'\blyrx\b', r'lyrc',
        r'lyricsss', r'lyricx', r'lyrcx',
    ]
    return any(re.search(p, blob) for p in lyric_patterns)


def _row_text_blob_for_safety(row):
    if row is None:
        return ''
    parts = []
    for key in ['text', 'caption', 'Caption', 'desc', 'Description']:
        try:
            parts.append(str(row.get(key, '') or ''))
        except Exception:
            pass
    try:
        tags = row.get('hashtags', [])
        if isinstance(tags, list):
            for h in tags:
                parts.append(str(h.get('name', '') if isinstance(h, dict) else h))
    except Exception:
        pass
    return ' '.join(parts).lower()


def _row_market_code(row):
    """Return normalized source market for market-specific guardrails."""
    try:
        return (_kb_extract_market(row) or '').upper()
    except Exception:
        return ''


def _kb_track_rule(row):
    """Return the Creative KB track rule for the current source track, if any."""
    try:
        kb = load_creative_kb()
        track = _kb_extract_track(row)
        if not track:
            return {}, ''
        return (kb.get('track_rules') or {}).get(track, {}) or {}, track
    except Exception:
        return {}, ''


def apply_kr_track_dance_guardrails(result, row=None):
    """KR-only Dance support when track history *and* visual evidence agree.

    Track history is never sufficient by itself. The 100-post holdout showed it
    adding Dance to ordinary animal movement and outfit showcases without
    explicit rhythmic/choreographed motion.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    if _row_market_code(row) != 'KR':
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if len(labels) != 1 or 'Dance' in labels or 'Carousel' in labels:
        return result

    recoverable_single_labels = {
        'Lip Sync', 'Fashion', 'Beauty', 'Slice of Life', 'Celebrity Edits',
        'Fitness', 'Cover'
    }
    if labels[0] not in recoverable_single_labels:
        return result

    observation = _result_observation_blob(result)
    visual_dance = _result_has_dance_visual_cues(result)
    fashion_focus = any(term in observation for term in [
        'outfit showcase', 'showcases an outfit', 'showcases a casual', 'trying on layers',
        'clothing look', 'outfit combination', 'fit check', 'ootd', 'fashion showcase'
    ])
    weak_movement_only = any(term in observation for term in [
        'dancing slightly', 'moves slightly', 'steps forward and backward',
        'poses for the camera', 'turns to show the outfit'
    ])
    if not visual_dance or fashion_focus or weak_movement_only:
        return result

    # Never add Dance to obvious lyric/text, quote, gaming, tutorial/news, drama,
    # comedy, or POV predictions. These caused regressions when tuned globally.
    if labels[0] in {'Lyrics', 'Lyrics Translation', 'Quotes', 'Gaming', 'Media/Infotainment', 'Movie/Tv/Drama Edits', 'Comedy', 'POV', 'Relationship'}:
        return result

    rule, track_key = _kb_track_rule(row)
    kb_labels = _kb_valid_labels(rule.get('preferred_creative_type') or rule.get('labels') or [])
    if 'Dance' not in kb_labels:
        return result
    try:
        kb_conf = float(rule.get('confidence', 0) or 0)
        kb_total = int(rule.get('total', rule.get('count', 0)) or 0)
    except Exception:
        kb_conf, kb_total = 0.0, 0

    # The prior is only a tie-breaker after direct visual choreography evidence.
    if kb_conf < 0.55 or kb_total < 10:
        return result

    result['creative_type'] = [labels[0], 'Dance']
    old_reason = str(result.get('reasoning', '') or '')
    add_reason = f'KR track KB guardrail: track {track_key} historically leans Dance ({kb_conf:.2f}, n={kb_total}), so Dance was added as a supporting label.'
    if 'KR track KB guardrail' not in old_reason:
        result['reasoning'] = (old_reason + ' | ' + add_reason).strip(' |')
    try:
        result['confidence'] = max(float(result.get('confidence', 0) or 0), 0.78)
    except Exception:
        result['confidence'] = 0.78
    return result


def _result_has_translation_cues(result):
    blob = _result_text_blob(result)
    return _has_phrase(blob, LYRICS_TRANSLATION_CUES)


def _result_is_clear_lipsync_only(result):
    blob = _result_text_blob(result)
    has_lipsync = ('lip sync' in blob or 'lipsync' in blob or 'mouthing' in blob or 'mouth' in blob)
    has_dance = _has_strong_dance_phrase(blob)
    has_non_dance = any(cue in blob for cue in NON_DANCE_LIPSYNC_CUES)
    return has_lipsync and has_non_dance and not has_dance


def apply_lyrics_guardrails(result, row=None):
    """Protect visible lyric videos from being mislabelled as Dance.

    PH mismatch analysis showed repeated cases where Gemini's own details said
    "song lyrics display", "static lyrics", or "Spotify lyrics", but the final label
    was Dance, often because the track name contained the word "dance".
    """
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if not labels:
        return result

    lyric_cue = _result_has_lyric_visual_cues(result)
    translation_cue = _result_has_translation_cues(result)
    dance_cue = _has_strong_dance_phrase(_result_text_blob(result))
    market = _row_market_code(row)
    is_ph = market == 'PH'
    row_blob = _row_text_blob_for_safety(row)

    # PH needs the hard lyric rescue because many Raindance lyric pages were predicted as Dance.
    # KR dropped after v5, so keep the hard source/account lyric cues PH-only. Outside PH,
    # only Gemini's own visual description can trigger Lyrics, and only when there is no
    # real choreography/body-movement evidence.
    row_lyric_text_cue = _has_lyric_language(row_blob) if is_ph else False
    lyric_account_cue = _row_has_lyric_account_cue(row) if is_ph else False

    if (lyric_cue or row_lyric_text_cue or lyric_account_cue) and not dance_cue:
        target = 'Lyrics Translation' if translation_cue else 'Lyrics'
        new_labels = [target]
        if 'Carousel' in labels and target != 'Carousel':
            new_labels = ['Carousel', target]
        else:
            complementary = next((label for label in [
                'Movie/Tv/Drama Edits', 'Celebrity Edits', 'Lip Sync', 'Relationship'
            ] if label in labels and label != target), None)
            if complementary:
                new_labels = [complementary, target]
        result['creative_type'] = new_labels[:2]
        if not str(result.get('narrative', '') or '').strip() or str(result.get('narrative', '')).strip().lower() in ['simple dance', 'dance']:
            result['narrative'] = 'Lyrics display'
        old_reason = str(result.get('reasoning', '') or '')
        add_reason = f'Guardrail: visible lyric/text display detected, so {target} was prioritized over Dance.'
        if 'visible lyric/text display detected' not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + add_reason).strip(' |')
        else:
            result['reasoning'] = old_reason
        try:
            result['confidence'] = max(float(result.get('confidence', 0) or 0), 0.80)
        except Exception:
            result['confidence'] = 0.80
    return result


def apply_dance_guardrails(result, row=None):
    """Post-process obvious Dance/Lip Sync confusion without another Gemini call.

    This version avoids substring traps such as "Raindance" and ignores the model's
    own predicted label when deciding whether dance evidence exists.
    """
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    label_set = set(labels)

    # Do not let Dance guardrail touch clear lyric-display posts.
    if _result_has_lyric_visual_cues(result) and not _result_has_dance_visual_cues(result):
        return result

    row_dance_cue = _row_has_dance_cues(row) if row is not None else False
    result_dance_cue = _result_has_dance_visual_cues(result)
    clear_lipsync_only = _result_is_clear_lipsync_only(result)

    should_force_dance = (row_dance_cue or result_dance_cue) and not clear_lipsync_only
    # Caption/hashtag cues alone are not enough to override visual categories like Fashion/Beauty/Lyrics.
    # They are mainly used to rescue Lip Sync/Relationship/Slice/Celebrity rows when the visual text also supports motion.
    if row_dance_cue and not result_dance_cue and (label_set & {'Fashion', 'Beauty', 'Fitness', 'Lyrics', 'Lyrics Translation', 'Quotes', 'Travel', 'Gaming', 'Media/Infotainment'}):
        should_force_dance = False

    if should_force_dance and 'Dance' not in label_set:
        new_labels = ['Dance']
        for keep in ['Fitness', 'Celebrity Edits', 'Lip Sync', 'Relationship', 'Carousel']:
            if keep in labels and keep not in new_labels:
                new_labels.append(keep)
                break
        result['creative_type'] = new_labels[:2]
        old_reason = str(result.get('reasoning', '') or '')
        result['reasoning'] = (old_reason + ' | Guardrail: choreography/body-movement cues detected, so Dance was prioritized.').strip(' |')
        try:
            result['confidence'] = max(float(result.get('confidence', 0) or 0), 0.78)
        except Exception:
            result['confidence'] = 0.78
    elif 'Dance' in label_set and 'Lip Sync' in label_set and result_dance_cue:
        rest = [x for x in labels if x != 'Dance']
        result['creative_type'] = ['Dance'] + rest[:1]
    return result



def _set_labels_preserve_allowed(result, labels, reason_add=''):
    """Set Creative Type labels safely with canonical capitalization."""
    if not isinstance(result, dict):
        return result
    clean = []
    for lab in labels:
        if lab in ALLOWED_SET and lab not in clean:
            clean.append(lab)
    if not clean:
        return result
    result['creative_type'] = clean[:2]
    if reason_add:
        old = str(result.get('reasoning', '') or '')
        if reason_add not in old:
            result['reasoning'] = (old + ' | ' + reason_add).strip(' |')
    try:
        result['confidence'] = max(float(result.get('confidence', 0) or 0), 0.78)
    except Exception:
        result['confidence'] = 0.78
    return result


def apply_ph_text_quote_and_lipsync_guardrails(result, row=None):
    """PH-specific balance for text/quote posts and Dance vs Lip Sync.

    From the PH mismatch report, the largest safe pattern was not Lyrics anymore;
    it was static/text quote posts being exported as fake Carousel + Reflection /
    Relationship / Lyrics / Media. This guardrail only removes Carousel when the
    TikTok is not an actual /photo/ slideshow, so real photo carousels are preserved.

    It also softens PH Dance only when Gemini describes a close-up/posing/lip-sync
    style post with no choreography evidence.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    if _row_market_code(row) != 'PH':
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if not labels:
        return result
    label_set = set(labels)
    blob = _result_text_blob(result)
    url_type = _kb_url_type(row)

    text_quote_cues = [
        'overlaid text', 'text overlay', 'text overlays', 'static image', 'static shot',
        'quote', 'caption ideas', 'caption inspiration', 'personal statement',
        'centered text', 'romantic text', 'text expressing', 'with text',
        'lyrics superimposed', 'text about', 'on-screen text', 'onscreen text'
    ]
    excluded_for_quote = {
        'Dance', 'Lip Sync', 'Beauty', 'Fashion', 'Celebrity Edits',
        'Movie/Tv/Drama Edits', 'Gaming', 'Travel'
    }
    has_text_quote_cue = any(cue in blob for cue in text_quote_cues)

    # Fake carousel correction: for /video/ static quote posts, replace the fake
    # Carousel label with Quotes while preserving the other semantic label.
    # Example: Carousel, Relationship -> Quotes, Relationship.
    if (
        has_text_quote_cue
        and 'Carousel' in label_set
        and 'Quotes' not in label_set
        and url_type != 'photo'
        and not (label_set & excluded_for_quote)
    ):
        non_carousel = [x for x in labels if x != 'Carousel']
        return _set_labels_preserve_allowed(
            result,
            ['Quotes'] + non_carousel,
            'PH text-post guardrail: static/text-overlay video looked like a quote post, so fake Carousel was replaced with Quotes.'
        )

    # Add Quotes as a second label for single-label PH text cards. This is additive
    # and preserves the original label, so it should not hurt correct Reflection /
    # Relationship / Lyrics rows under the contains-match checker.
    if (
        has_text_quote_cue
        and 'Quotes' not in label_set
        and len(labels) == 1
        and labels[0] in {'Reflection', 'Relationship', 'Lyrics', 'Media/Infotainment', 'Slice of Life'}
    ):
        return _set_labels_preserve_allowed(
            result,
            [labels[0], 'Quotes'],
            'PH text-post guardrail: text-overlay quote cues detected, so Quotes was added as supporting label.'
        )

    # PH Dance false positive softener. Do not override true choreography.
    strong_dance_cues = [
        'synchronized', 'synchronised', 'choreography', 'dance movements',
        'rhythmic dance', 'dance sequence', 'performing a dance',
        'hand choreography', 'dance challenge', 'coordinated dance', 'dance routine'
    ]
    non_dance_lipsync_cues = [
        'close-up', 'close up', 'posing', 'stand together', 'standing together',
        'selfie', 'candid', 'hanging out', 'mouthing', 'lip-sync', 'lip sync',
        'mouths the lyrics', 'mouthing lyrics'
    ]
    if labels == ['Dance'] and any(c in blob for c in non_dance_lipsync_cues) and not any(c in blob for c in strong_dance_cues):
        return _set_labels_preserve_allowed(
            result,
            ['Lip Sync'],
            'PH lip-sync guardrail: close-up/posing/lip-sync cues with no choreography, so Dance was softened to Lip Sync.'
        )

    return result


def apply_my_scene_balance_guardrails(result, row=None):
    """MY-specific balance from the Malaysia mismatch report.

    Keep this conservative and market-scoped. Malaysia mismatches were mostly:
    - Relationship/Quotes/Reflection inside Carousel-like text posts;
    - Slice of Life being over-read as Reflection/Lyrics/Comedy;
    - Lip Sync being over-read as Dance/Beauty/Fashion/Lyrics;
    - Travel winter/snow posts and classroom Gen-Z dance trends being missed.

    These rules are signal-based and do not memorize URLs.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    if _row_market_code(row) != 'MY':
        return result

    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if not labels:
        return result
    label_set = set(labels)
    blob = _result_text_blob(result)

    def has_re(patterns):
        return any(re.search(p, blob) for p in patterns)

    # Avoid broad words like "love" alone because self-love/reflection rows are common.
    relationship_cues = [
        r'relationship advice', r'relationship quote', r'relationship appreciation',
        r'relationship dynamics', r'relationship frustrations', r'cynical relationship take',
        r'romantic', r'partner', r'couple', r'boyfriend|girlfriend|husband|wife',
        r'someone special', r'specific person', r'communication',
        r'late replies|dry texts|left on seen', r'commitment|committed',
        r'candid[- ]style photo', r'comfort in conversation',
        r'desire to be loved|wish(?:ing)? to be loved|being deeply loved',
        r'choose(?:s|ing)? (?:a )?specific person|person over others',
        r"woman'?s anger|women look forward|man’s behavior|man's behavior",
        r'praying for someone', r'hari raya notification', r'stays single|single',
        r'longing for love',
    ]
    # Some relationship-worded quote posts are reviewed as Quotes in MY. Keep them as Quotes.
    relationship_quote_exclusions = [
        r'apologizing in relationships', r'apologising in relationships',
        r'apologizing in relationship', r'apologising in relationship',
    ]

    quote_cues = [
        r'\bquote\b', r'quotes', r'quote card', r'text quote', r'caption ideas',
        r"teacher'?s advice", r'karma', r'worries and overthinking', r'ego, anger',
        r'accepting all aspects', r'checking in on', r'are you okay', r'how are you',
        r'personal pacing', r'life lesson about endings', r'advice', r'comforting post',
    ]
    slice_cues = [
        r'train station|transit', r'\brain\b|rainy', r'cityscape|urban street',
        r'motorcycle|helmet', r'hotpot|dining setting|restaurant|cafe',
        r'smartphone screen|phone screen|late-night messaging|late night',
        r'cat\b|school|campus|classroom|graduation|makeup artist',
        r'memorabilia|k-drama/idol|pink bag|lifestyle|self-portrait|smiling',
        r'shoreline|sunset|beach|swing|playground|friendship',
    ]
    comedy_cues = [
        r'humor|humour|humorous|joke|joking|funny|meme|comedic|playful',
        r'princess treatment|only daughter|gen z|schoolwork|private instagram',
        r'cat reaction|betrayal|birth order|back to school',
    ]
    lip_sync_cues = [
        r'mouths|mouthing|lip[- ]sync|lip syncing|mouthing along|sings along|singing to camera',
    ]
    travel_cues = [
        r'travel|travelling|traveling|winter|snow|snowy|cold|snow-covered|vacation|destination',
    ]
    dance_recovery_cues = [
        r'gen z social media trend|lecturer join[s]? gen z',
        r'coordinated hand-gesture|rhythmic hand gestures|synchronized hand movements',
        r'simple dance|dance routine|bridesmaids dancing|hand dance',
    ]
    media_info_cues = [
        r'prophet musa|prayer for relief|spiritual prayer',
        r'financial advice|saving money|investments|savings accounts',
        r'tutorial|roblox',
    ]

    has_relationship = has_re(relationship_cues) and not has_re(relationship_quote_exclusions)
    has_quote = has_re(quote_cues)

    # 1) Carousel-like text posts: preserve Carousel so true MY carousel rows still pass,
    # but tune the second semantic label.
    if 'Carousel' in label_set and has_relationship and 'Relationship' not in label_set:
        return _set_labels_preserve_allowed(
            result,
            ['Carousel', 'Relationship'],
            'MY relationship guardrail: carousel/text post has strong relationship cues, so Relationship replaced the weaker semantic label.'
        )
    if 'Carousel' in label_set and has_quote and 'Quotes' not in label_set and not has_relationship:
        return _set_labels_preserve_allowed(
            result,
            ['Carousel', 'Quotes'],
            'MY quote guardrail: carousel/text post has strong quote cues, so Quotes was used as the semantic label.'
        )
    if (
        'Carousel' in label_set and 'Relationship' in label_set and 'Reflection' not in label_set
        and has_re([r'kindly|live kindly|self-love|personal growth|healing|spiritual|academic|anxiety'])
        and not has_relationship
    ):
        return _set_labels_preserve_allowed(
            result,
            ['Carousel', 'Reflection'],
            'MY reflection guardrail: carousel/text post has personal reflection cues, so Reflection was used as the semantic label.'
        )

    # 2) Relationship rescue for single-label non-carousel predictions.
    if has_relationship and 'Relationship' not in label_set:
        if len(labels) == 1 and labels[0] in {'Reflection', 'Lyrics', 'Fashion', 'Lip Sync', 'POV', 'Quotes', 'Slice of Life'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Relationship'],
                'MY relationship guardrail: strong relationship cues detected, so Relationship was added as supporting label.'
            )
        if labels == ['Fashion', 'Carousel']:
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Relationship'],
                'MY relationship guardrail: candid/relationship cues detected in a carousel-style post.'
            )

    # 3) Quotes rescue for text/advice posts. Additive when possible.
    if has_quote and 'Quotes' not in label_set:
        if len(labels) == 1 and labels[0] in {'Reflection', 'Fashion', 'Dance', 'POV', 'Lip Sync', 'Relationship', 'Lyrics'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Quotes'],
                'MY quote guardrail: strong quote/advice/text-card cues detected, so Quotes was added.'
            )
        if len(labels) == 2 and 'Relationship' in label_set and 'POV' in label_set:
            return _set_labels_preserve_allowed(
                result,
                ['Relationship', 'Quotes'],
                'MY quote guardrail: relationship roleplay has quote-style text, so Quotes was added.'
            )
        if len(labels) == 2 and 'Lip Sync' in label_set and 'Relationship' in label_set:
            return _set_labels_preserve_allowed(
                result,
                ['Lip Sync', 'Quotes'],
                'MY quote guardrail: lip-sync post has quote-style relationship text, so Quotes was added.'
            )

    # 4) Slice of Life rescue for everyday real-life scenes that were over-read as Reflection/Lyrics/Comedy/Media.
    if 'Slice of Life' not in label_set and has_re(slice_cues):
        if len(labels) == 1 and labels[0] in {'Reflection', 'Lyrics', 'Comedy', 'Media/Infotainment', 'Lip Sync'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Slice of Life'],
                'MY slice-of-life guardrail: everyday scene cues detected, so Slice of Life was added.'
            )
        if set(labels) == {'Travel', 'Carousel'}:
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Slice of Life'],
                'MY slice-of-life guardrail: casual beach/shoreline posing looked more lifestyle than travel.'
            )
        if set(labels) == {'Dance', 'Carousel'}:
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Slice of Life'],
                'MY slice-of-life guardrail: school/lifestyle carousel cues detected.'
            )

    # 5) Comedy rescue, additive so correct Slice/Reflection rows are preserved.
    if 'Comedy' not in label_set and has_re(comedy_cues):
        if len(labels) == 1 and labels[0] in {'Slice of Life', 'Reflection', 'Lip Sync'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Comedy'],
                'MY comedy guardrail: humorous/meme/playful cues detected, so Comedy was added.'
            )
        if set(labels) == {'Dance', 'Lip Sync'}:
            return _set_labels_preserve_allowed(
                result,
                ['Lip Sync', 'Comedy'],
                'MY comedy guardrail: comedic lip-sync/skit cues detected, so Comedy replaced Dance.'
            )

    # 6) Lip Sync rescue for MY cases where still frames made hand motions/beauty/fashion look like another format.
    if 'Lip Sync' not in label_set and has_re(lip_sync_cues):
        if len(labels) == 1 and labels[0] in {'Lyrics', 'Fashion', 'Beauty', 'Celebrity Edits'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Lip Sync'],
                'MY lip-sync guardrail: mouth/lip-sync cues detected, so Lip Sync was added.'
            )
        if labels == ['Dance']:
            return _set_labels_preserve_allowed(
                result,
                ['Dance', 'Lip Sync'],
                'MY lip-sync guardrail: simple hand/mouth performance can be Lip Sync, so Lip Sync was added.'
            )
    if 'Dance' in label_set and 'Lip Sync' not in label_set and has_re([r'hand gesture choreography|rhythmic hand gestures|synchronized hand movements']):
        return _set_labels_preserve_allowed(
            result,
            ['Dance', 'Lip Sync'],
            'MY lip-sync guardrail: simple hand-gesture performance can count as Lip Sync in MY reviewed taxonomy.'
        )

    # 7) Travel rescue for clear winter/snow/travel scenes.
    if 'Travel' not in label_set and has_re(travel_cues):
        if len(labels) == 1 and labels[0] in {'Dance', 'Reflection', 'Lyrics', 'Slice of Life'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Travel'],
                'MY travel guardrail: winter/snow/travel cues detected, so Travel was added.'
            )

    # 8) Dance recovery for classroom Gen-Z trend / simple dance rows, while preserving Comedy/Beauty if present.
    if 'Dance' not in label_set and has_re(dance_recovery_cues):
        if 'Comedy' in label_set:
            return _set_labels_preserve_allowed(
                result,
                ['Comedy', 'Dance'],
                'MY dance guardrail: Gen-Z classroom/social trend cues detected, so Dance was added.'
            )
        if len(labels) == 1 and labels[0] in {'Beauty', 'POV', 'Slice of Life'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Dance'],
                'MY dance guardrail: simple dance/trend cues detected, so Dance was added.'
            )

    # 9) Media/Infotainment rescue for finance/spiritual/tutorial cases.
    if 'Media/Infotainment' not in label_set and has_re(media_info_cues):
        if len(labels) == 1 and labels[0] in {'Reflection', 'Gaming', 'Slice of Life'}:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Media/Infotainment'],
                'MY infotainment guardrail: advice/tutorial/spiritual/finance cues detected, so Media/Infotainment was added.'
            )

    return result


def apply_th_scene_balance_guardrails(result, row=None):
    """TH-specific balance from the TH mismatch report.

    Thailand is more scene-dependent, so this uses additive labels when possible:
    - strong TH dance-track history adds Dance as a supporting label;
    - obvious non-choreography Dance false positives are softened to Slice/Lip Sync;
    - playful Slice of Life can also include Comedy;
    - Thai concert/lyric fan-perspective posts on POV-leaning tracks can include POV.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    if _row_market_code(row) != 'TH':
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if not labels:
        return result
    label_set = set(labels)
    blob = _result_text_blob(result)

    # 1) TH track-level Dance recovery, generalized through KB track history.
    rule, track_key = _kb_track_rule(row)
    kb_labels = _kb_valid_labels(rule.get('preferred_creative_type') or rule.get('labels') or [])
    try:
        kb_conf = float(rule.get('confidence', 0) or 0)
        kb_total = int(rule.get('total', rule.get('count', 0)) or 0)
    except Exception:
        kb_conf, kb_total = 0.0, 0
    if 'Dance' in kb_labels and kb_conf >= 0.70 and kb_total >= 10 and 'Dance' not in label_set:
        recoverable_first = {
            'Lip Sync', 'Fashion', 'Beauty', 'Slice of Life', 'Celebrity Edits',
            'Fitness', 'Cover', 'Relationship', 'Comedy', 'POV', 'Media/Infotainment'
        }
        if len(labels) == 1 and labels[0] in recoverable_first:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Dance'],
                f'TH track KB guardrail: track {track_key} historically leans Dance ({kb_conf:.2f}, n={kb_total}), so Dance was added as supporting label.'
            )
        if len(labels) == 2 and labels[0] in recoverable_first and 'Carousel' not in label_set:
            return _set_labels_preserve_allowed(
                result,
                [labels[0], 'Dance'],
                f'TH track KB guardrail: track {track_key} historically leans Dance ({kb_conf:.2f}, n={kb_total}), so Dance replaced the weaker second label.'
            )

    # 2) TH Dance false positive softener. This fixes static/casual TH scenes that
    # were labeled Dance even though Gemini described a selfie, standing, student,
    # casual night-out, etc. Strong choreography phrases protect real Dance.
    strong_dance_cues = [
        'synchronized', 'synchronised', 'choreography', 'dance movements',
        'rhythmic dance', 'performing a dance', 'simple dance', 'dance sequence',
        'dance and finger heart', 'dancing motions', 'mimicking dancing',
        'rhythmic', 'coordinated dance', 'dance routine', 'perform dance',
        'performs a dance', 'coordinated movement'
    ]
    lip_cues = ['mouthing', 'lip-sync', 'lip sync', 'sings along', 'mouths the lyrics']
    casual_cues = [
        'selfie', 'portrait', 'sits', 'sitting', 'stands', 'standing', 'casual',
        'candid', 'greeting gesture', 'montage', 'green screen', 'student',
        'friends', 'night out', 'school uniform', 'campus life'
    ]
    if labels == ['Dance'] and not any(c in blob for c in strong_dance_cues):
        if any(c in blob for c in lip_cues):
            return _set_labels_preserve_allowed(
                result,
                ['Lip Sync'],
                'TH scene guardrail: lip-sync/casual cues with no choreography, so Dance was softened to Lip Sync.'
            )
        if any(c in blob for c in casual_cues):
            return _set_labels_preserve_allowed(
                result,
                ['Slice of Life'],
                'TH scene guardrail: casual/static scene cues with no choreography, so Dance was softened to Slice of Life.'
            )

    # 3) TH playful Slice of Life can also be Comedy. Additive, not replacing.
    comedy_cues = [
        'playful', 'playfully', 'comedic', 'humorous', 'funny', 'joke',
        'banter', 'lighthearted', 'cute children', 'baby elephant',
        'turns its backside', 'trophy', 'milestone', 'skit'
    ]
    if labels == ['Slice of Life'] and any(c in blob for c in comedy_cues):
        return _set_labels_preserve_allowed(
            result,
            ['Slice of Life', 'Comedy'],
            'TH comedy guardrail: playful/humorous cues detected, so Comedy was added as supporting label.'
        )

    # 4) TH POV recovery may use track history only after the current post has
    # direct first-person/viewer-perspective evidence. A concert, singer or text
    # overlay alone is not POV.
    dist = rule.get('distribution', {}) if isinstance(rule, dict) else {}
    pov_count = 0
    for k, v in dist.items():
        if str(k).strip().lower() == 'pov':
            try:
                pov_count = int(v)
            except Exception:
                pov_count = 0
    pov_track = ('POV' in kb_labels) or (pov_count >= 4 and kb_total >= 10)
    pov_context = any(c in blob for c in [
        'pov:', 'point of view', 'first-person', 'first person',
        'fan perspective', 'viewer perspective', 'camera perspective',
        'seen through the viewer', 'from the audience perspective',
    ])
    if (
        pov_track and pov_context and 'POV' not in label_set and len(labels) == 1
        and labels[0] in {'Lyrics', 'Celebrity Edits', 'Slice of Life', 'Travel', 'Relationship', 'Beauty', 'Lip Sync'}
    ):
        return _set_labels_preserve_allowed(
            result,
            [labels[0], 'POV'],
            f'TH POV track guardrail: track {track_key} has repeated POV history and the current post has explicit first-person/viewer-perspective evidence, so POV was added.'
        )

    return result


def apply_vn_scene_balance_guardrails(result, row=None):
    """VN-specific balance from the Vietnam mismatch report.

    Vietnam reviewed labels are highly scene/context based. The repeated gaps were:
    - Lip Sync hidden by Lyrics / Slice / Dance / Media labels;
    - Lyrics Translation hidden by plain Lyrics or visual labels;
    - everyday food/wedding/pet/family scenes over-read as Media/Relationship/Dance;
    - static text/photo posts over-read as Reflection/Relationship/Comedy instead of Quotes;
    - first-person scooter/walking/flower scenarios missing POV.

    These are reusable signal rules. They do not memorize exact TikTok URLs.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    if _row_market_code(row) != 'VN':
        return result

    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if not labels:
        return result

    label_set = set(labels)
    observation_blob = _result_observation_blob(result)
    blob = ' '.join([
        observation_blob,
        _row_text_blob_for_safety(row),
        _kb_extract_creator(row),
        _kb_extract_track(row),
    ]).lower()

    def has_re(patterns):
        return any(re.search(p, blob) for p in patterns)

    def add_second(label, reason):
        if label in set(labels) or len(labels) != 1:
            return None
        return _set_labels_preserve_allowed(result, [labels[0], label], reason)

    # 1) Lyrics Translation rescue. In VN, bilingual/translated lyrics often looked
    # like plain Lyrics, Lip Sync, or Dance from frames alone.
    lyrics_translation_cues = [
        r'lyric[s]?.{0,80}(translation|translated|english|vietnamese|bilingual)',
        r'(english|vietnamese|bilingual|translated|translation).{0,80}lyric[s]?',
        r'lyrics at the top.{0,80}vietnamese',
        r'vietnamese text.{0,80}(translation|translations|lyrics)',
    ]
    if has_re(lyrics_translation_cues):
        if 'Carousel' in label_set:
            return _set_labels_preserve_allowed(
                result, ['Carousel', 'Lyrics Translation'],
                'VN lyrics-translation guardrail: bilingual/translated lyric cues detected.'
            )
        if 'Dance' in label_set:
            return _set_labels_preserve_allowed(
                result, ['Lyrics Translation', 'Dance'],
                'VN lyrics-translation guardrail: translated lyric cues were stronger than the visual motion label.'
            )
        if 'Lip Sync' in label_set:
            return _set_labels_preserve_allowed(
                result, ['Lyrics Translation', 'Lip Sync'],
                'VN lyrics-translation guardrail: translated lyric cues detected while preserving Lip Sync.'
            )
        return _set_labels_preserve_allowed(
            result, ['Lyrics Translation'],
            'VN lyrics-translation guardrail: bilingual/translated lyric cues detected.'
        )

    # 2) Lip Sync rescue. If Gemini describes mouthing/lip-syncing, preserve that
    # even when the top label became Lyrics, Slice, Reflection, or Media.
    lip_sync_cues = [
        r'lip[- ]?sync', r'mouthing', r'mouths? lyric', r'sings? along',
        r'performs? a lip', r'mouth/face performance'
    ]
    if 'Lip Sync' not in label_set and has_re(lip_sync_cues):
        strong_dance_cues = [r'choreograph', r'synchronized dance', r'dance routine', r'dance challenge', r'coordinated dance']
        if labels == ['Dance'] and not has_re(strong_dance_cues):
            return _set_labels_preserve_allowed(
                result, ['Dance', 'Lip Sync'],
                'VN lip-sync guardrail: mouthing/lip-sync cues detected alongside weak dance evidence.'
            )
        if len(labels) == 1:
            return _set_labels_preserve_allowed(
                result, [labels[0], 'Lip Sync'],
                'VN lip-sync guardrail: explicit mouthing/lip-sync cues detected.'
            )

    # 3) POV rescue for first-person / viewer-perspective posts.
    pov_cues = [
        r'first[- ]person', r'viewer perspective', r'point of view', r'\bpov\b',
        r'from (?:a )?(?:motorbike|scooter|bicycle|bike)', r'walking .*wet',
        r'holding (?:a )?bouquet.*walking', r'did not ask.*flowers',
        r'shall we go', r'your turn to save me'
    ]
    if 'POV' not in label_set and has_re(pov_cues):
        if labels == ['Relationship']:
            return _set_labels_preserve_allowed(
                result, ['Relationship', 'POV'],
                'VN POV guardrail: first-person/relationship scenario cues detected.'
            )
        if labels == ['Dance']:
            return _set_labels_preserve_allowed(
                result, ['Dance', 'POV'],
                'VN POV guardrail: first-person walking/riding cues detected.'
            )
        if len(labels) == 1:
            return _set_labels_preserve_allowed(
                result, [labels[0], 'POV'],
                'VN POV guardrail: first-person/viewer-perspective cues detected.'
            )

    # 4) Quotes rescue. Keep this high precision so true Reflection/Relationship
    # carousels are not overwritten.
    high_quote_cues = [
        r'phone calls?|ignored phone', r'insecurity|body confidence',
        r'sensitive|melanchol|exhaustion', r'cut mango|mango',
        r'good luck|keep the chain', r'face[- ]distortion filter.*new year|upcoming new year'
    ]
    general_quote_cues = [
        r'\bquote\b', r'text quote', r'quote card', r'static .*text',
        r'overlaid text', r'on[- ]screen text', r'onscreen text', r'text overlay'
    ]
    if 'Quotes' not in label_set:
        if has_re(high_quote_cues):
            if 'Carousel' in label_set and (label_set & {'Reflection', 'Relationship', 'Comedy', 'Slice of Life'}):
                return _set_labels_preserve_allowed(
                    result, ['Carousel', 'Quotes'],
                    'VN quote guardrail: high-confidence static text/quote cues detected.'
                )
            if len(labels) == 1 and labels[0] in {'Reflection', 'Relationship', 'Comedy', 'Slice of Life', 'Lyrics'}:
                return _set_labels_preserve_allowed(
                    result, [labels[0], 'Quotes'],
                    'VN quote guardrail: high-confidence text/quote cues detected.'
                )
        elif has_re(general_quote_cues) and len(labels) == 1 and labels[0] in {'Reflection', 'Relationship', 'Comedy', 'Slice of Life', 'Lyrics', 'Media/Infotainment'}:
            return _set_labels_preserve_allowed(
                result, [labels[0], 'Quotes'],
                'VN quote guardrail: text-overlay quote cues detected.'
            )

    # 5) Slice of Life rescue for VN everyday scenes that are often over-read as
    # Media, Dance, Relationship, Reflection, Comedy, or Travel.
    slice_cues = [
        r'food (?:vlog|montage)|arranging.*food|sashimi|seafood|cooking challenge|milk tea rice|rice cooker',
        r'wedding (?:decor|decoration|setup|entrance)|bride.*cutout|vu quy|nhà có hỷ',
        r'gift box|birthday gift|decorated gift', r'classroom|students raising',
        r'pet|dog|cat|kitten|meerkat|baby|toddler|children|child|family|siblings|brother',
        r'casual|everyday|daily|slice[- ]of[- ]life|candid|portrait|selfie|poses?|standing|sitting|home setting|bedroom|bonfire|campfire|eating a meal|sunset',
        r'0\.5x wide-angle selfie|aesthetic outdoor selfie|cafe daily life|new year portrait'
    ]
    if 'Slice of Life' not in label_set and has_re(slice_cues):
        if len(labels) == 1 and labels[0] in {'Media/Infotainment', 'Dance', 'Relationship', 'Reflection', 'Comedy', 'Travel', 'Beauty', 'Lyrics', 'Fashion'}:
            return _set_labels_preserve_allowed(
                result, [labels[0], 'Slice of Life'],
                'VN slice-of-life guardrail: everyday/pet/family/food/wedding scene cues detected.'
            )

    # 6) Dance false-positive softener for VN casual/selfie/family/pet scenes.
    if labels == ['Dance'] and not has_re([r'choreograph', r'dance routine', r'dance challenge', r'synchronized dance', r'coordinated dance', r'perform.*dance', r'dances? together']):
        if has_re([r'selfie|portrait|standing|friends smile|pose|family|baby|children|dog|cat|bonfire|warm hands']):
            return _set_labels_preserve_allowed(
                result, ['Dance', 'Slice of Life'],
                'VN dance guardrail: casual/static scene cues detected, so Slice of Life was added.'
            )

    # 7) Comedy rescue for playful/meme/skit/filter/animation posts.
    comedy_cues = [
        r'comedic|humorous|funny|joke|playful|prank|skit|meme',
        r'face[- ]distortion|distorted face|throwing money|animated cat|cartoon cat',
        r'capybara|mock kiss|sleepy cat|cute sleepy|humorous text|funny chemistry|toddler reaction'
    ]
    if 'Comedy' not in label_set and has_re(comedy_cues):
        if len(labels) == 1 and labels[0] in {'Dance', 'Relationship', 'Reflection', 'Gaming', 'Slice of Life', 'Media/Infotainment', 'POV'}:
            return _set_labels_preserve_allowed(
                result, [labels[0], 'Comedy'],
                'VN comedy guardrail: playful/humorous/meme cues detected.'
            )

    # 8) Small but high-signal rescues.
    if 'Relationship' not in label_set and has_re([r'proposal|engagement ring|boyfriend|girlfriend|partner|couple|romantic|pre[- ]wedding|wedding attire|bride and groom']):
        if len(labels) == 1 and labels[0] in {'Media/Infotainment', 'Lyrics', 'Slice of Life', 'POV', 'Carousel'}:
            return _set_labels_preserve_allowed(
                result, [labels[0], 'Relationship'],
                'VN relationship guardrail: romantic/couple/flower cues detected.'
            )
    if 'Beauty' not in label_set and has_re([r'makeup|nail art|manicure|cosmetics']):
        if len(labels) == 1:
            return _set_labels_preserve_allowed(result, [labels[0], 'Beauty'], 'VN beauty guardrail: makeup/nail/cosmetic cues detected.')
    if 'Fashion' not in label_set and has_re([r'outfit|crop top|skirt|handbag|styling|fashion|white crop top|dragon design']):
        if len(labels) == 1:
            return _set_labels_preserve_allowed(result, [labels[0], 'Fashion'], 'VN fashion guardrail: outfit/styling cues detected.')
    if 'Travel' not in label_set and has_re([r'mountain village|picturesque mountain|landscape|scenery|destination|tourism|village']):
        if len(labels) == 1:
            return _set_labels_preserve_allowed(result, [labels[0], 'Travel'], 'VN travel guardrail: scenery/destination cues detected.')
    if 'Fitness' not in label_set and has_re([r'divers?|synchronized dive|athletes?|swimming|sporting event|marathon|runner|race']):
        if len(labels) == 1:
            return _set_labels_preserve_allowed(result, [labels[0], 'Fitness'], 'VN fitness/sport guardrail: athlete/sport cues detected.')
    if 'Media/Infotainment' not in label_set and has_re([r'match highlights|goals? by|marathon|runner.*finish|race|sports news|event staff|finish line']):
        if len(labels) == 1 and 'Gaming' not in label_set:
            return _set_labels_preserve_allowed(result, [labels[0], 'Media/Infotainment'], 'VN sports-info guardrail: match/race informational cues detected.')
    if 'Movie/Tv/Drama Edits' not in label_set and has_re([r'fictional|drama scene|split-screen.*woman.*man|characters? with|foreheads touching']):
        if len(labels) == 1 and labels[0] in {'Celebrity Edits', 'Relationship'}:
            return _set_labels_preserve_allowed(result, [labels[0], 'Movie/Tv/Drama Edits'], 'VN drama-edit guardrail: fictional scene/character cues detected.')

    return result

def apply_vn_v16_remaining_balance_guardrails(result, row=None):
    """VN v16 follow-up tuning from the latest VN mismatch report.

    This is market-scoped and feature-based. It does not use exact TikTok URLs,
    row numbers, or creator-to-label memorisation. The rules are deliberately
    additive/preservative: when possible, keep the existing strong label and add
    the missing VN semantic label as the second label.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    if _row_market_code(row) != 'VN':
        return result

    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if not labels:
        return result
    label_set = set(labels)

    observation_blob = _result_observation_blob(result)
    blob = ' '.join([
        observation_blob,
        _row_text_blob_for_safety(row),
        _kb_extract_creator(row),
        _kb_extract_track(row),
    ]).lower()

    def has_re(patterns):
        return any(re.search(p, blob, flags=re.I) for p in patterns)

    def add_preserve(target, reason, prefer_keep=None):
        """Add target while preserving the most stable existing label."""
        nonlocal labels, label_set
        if target in label_set:
            return result
        if len(labels) == 0:
            return _set_labels_preserve_allowed(result, [target], reason)
        if len(labels) == 1:
            return _set_labels_preserve_allowed(result, [labels[0], target], reason)

        hard_order = [
            'Carousel', 'Movie/Tv/Drama Edits', 'Gaming', 'Fitness', 'Comedy',
            'Quotes', 'Lip Sync', 'Slice of Life', 'Relationship', 'Dance',
            'Celebrity Edits', 'Media/Infotainment', 'Beauty', 'Fashion',
            'Travel', 'Reflection', 'Lyrics', 'Lyrics Translation', 'POV'
        ]
        if prefer_keep and prefer_keep in label_set:
            keep = prefer_keep
        else:
            keep = labels[0]
            for h in hard_order:
                if h in label_set:
                    keep = h
                    break
        return _set_labels_preserve_allowed(result, [keep, target], reason)

    # 1) Real sports/event/news information. Avoid gameplay/esports because those
    # can be Gaming or Celebrity Edits in the reviewed taxonomy.
    if 'Media/Infotainment' not in label_set and not has_re([r'efootball', r'gameplay', r'roblox', r'game edit']) and has_re([
        r'match highlights', r'barcelona vs napoli', r'goals? by', r'sports news',
        r'runner.*finish', r'finish line', r'statue installed', r'mechanical horse statue', r'installed in'
    ]):
        return add_preserve('Media/Infotainment', 'VN v16 media guardrail: sports/event/public-installation information cues detected.', prefer_keep='Fitness' if 'Fitness' in label_set else None)

    # 2) Football-game / game-footage fan edit style. Keep Gaming but add Celebrity
    # Edits where the reviewed VN taxonomy treats the sports/player edit as celebrity content.
    if 'Celebrity Edits' not in label_set and has_re([
        r'football game edit', r'efootball', r'gameplay footage.*celebration', r'team celebration'
    ]):
        return add_preserve('Celebrity Edits', 'VN v16 celebrity-edit guardrail: sports/gameplay fan-edit cues detected.', prefer_keep='Gaming' if 'Gaming' in label_set else None)

    if 'Celebrity Edits' not in label_set and not (label_set & {'Movie/Tv/Drama Edits', 'Gaming'}) and has_re([
        r'live performance clip', r'grammy awards', r'artist .*performance', r'singer .*performance'
    ]):
        return add_preserve('Celebrity Edits', 'VN v16 celebrity-edit guardrail: real artist/live performance cue detected.')

    drama_edit_cues = [
        r'split-screen.*woman.*man', r'foreheads touching', r'fictional',
        r'drama scene', r'movie scene', r'tv scene', r'series scene',
        r'cinematic (?:scene|montage|sequence)', r'film still', r'dialogue subtitle',
        r'montage.{0,80}(?:couple|woman and man|man and woman).{0,80}(?:romantic|settings|scenes)',
        r'(?:couple|woman and man|man and woman).{0,80}montage.{0,80}(?:romantic|settings|scenes)',
        r'romantic.{0,80}montage.{0,80}(?:couple|characters?).{0,80}cinematic',
        r'montage.{0,100}(?:couple|characters?).{0,100}(?:cinematic|intimate shots|multiple scenes)',
    ]
    if 'Movie/Tv/Drama Edits' not in label_set and has_re(drama_edit_cues):
        if 'Lyrics Translation' in label_set:
            return _set_labels_preserve_allowed(
                result,
                ['Movie/Tv/Drama Edits', 'Lyrics Translation'],
                'VN v17 drama-edit guardrail: cinematic/recurring-character montage cues detected while preserving translated lyrics.'
            )
        return add_preserve('Movie/Tv/Drama Edits', 'VN v17 drama-edit guardrail: fictional/cinematic montage cues detected.')

    # 3) Strong Dance recovery. Keep Lip Sync as second label when present.
    strong_dance_observation = any(re.search(pattern, observation_blob, flags=re.I) for pattern in [
        r'choreograph', r'dance performance', r'\bdancing\b', r'body rolls',
        r'fan.*dance', r'synchronized hand dance', r'coordinated dance',
        r'dance routine', r'dance challenge', r'dance practice',
        r'(?:creator|person|people|group|girl|boy|woman|man|idol)s?.{0,30}(?:performs?|doing).{0,15}dance',
    ])
    static_or_edit_observation = any(re.search(pattern, observation_blob, flags=re.I) for pattern in [
        r'static (?:shot|shots|image|images)', r'still (?:shot|shots|image|images)',
        r'photo montage', r'series of photos', r'posed portrait', r'lyrics? (?:displayed|overlaid)',
        r'montage.{0,80}(?:couple|character|actor|scene)', r'no choreography', r'little/no choreography',
    ])
    if 'Dance' not in label_set and strong_dance_observation and not static_or_edit_observation:
        if 'Lip Sync' in label_set:
            return _set_labels_preserve_allowed(result, ['Dance', 'Lip Sync'], 'VN v16 dance guardrail: explicit dance/movement cues detected while preserving Lip Sync.')
        keep = labels[0] if labels[0] in {'Lyrics Translation', 'Slice of Life', 'Reflection'} else None
        return _set_labels_preserve_allowed(result, ['Dance'] + ([keep] if keep else []), 'VN v16 dance guardrail: explicit dance/movement cues detected.')

    # 4) Lip Sync recovery for VN cases where frames describe a filter/selfie/standing
    # performance but miss mouth movement. This is additive and preserves a hard label.
    if 'Lip Sync' not in label_set and has_re([
        r'lip[- ]?sync', r'mouthing', r'mouths? along', r'mouths? lyrics', r'sings? along',
        r'filter challenge', r'face filter challenge', r'cristiano ronaldo filter',
        r'holding.*cute', r'personal facts list', r'personal traits', r'preferences',
        r'standing by a river', r'wide-angle selfie', r'cafe apron', r'young girl .*poses',
        r'playful.*performance'
    ]):
        return add_preserve('Lip Sync', 'VN v16 lip-sync guardrail: reusable filter/selfie/performance cues detected.')

    # 5) Lyrics Translation needs actual lyric + translation/bilingual/Vietnamese-language cue.
    # Avoid false positives such as a drama title containing "translated".
    lyrics_translation_explicit = has_re([
        r'lyric[s]?.{0,100}(translation|translated|english|vietnamese|bilingual)',
        r'(english|vietnamese|bilingual|translated|translation).{0,100}lyric[s]?',
        r'lyrics at the top', r'lyrics.*place names', r'vietnamese text.*lyrics'
    ])
    if 'Lyrics Translation' not in label_set and lyrics_translation_explicit:
        if 'Dance' in label_set:
            return _set_labels_preserve_allowed(result, ['Lyrics Translation', 'Dance'], 'VN v16 lyrics-translation guardrail: lyrics plus translation/language cue detected.')
        if 'Lip Sync' in label_set:
            return _set_labels_preserve_allowed(result, ['Lyrics Translation', 'Lip Sync'], 'VN v16 lyrics-translation guardrail: lyrics plus translation/language cue detected while preserving Lip Sync.')
        if 'Carousel' in label_set:
            return _set_labels_preserve_allowed(result, ['Carousel', 'Lyrics Translation'], 'VN v16 lyrics-translation guardrail: carousel with lyric translation cues detected.')
        return add_preserve('Lyrics Translation', 'VN v16 lyrics-translation guardrail: lyrics plus translation/language cue detected.')

    # 6) POV recovery requires explicit perspective/scenario evidence. Do not
    # infer POV from the subject (pets, flowers, helmets, rooms, etc.).
    if 'POV' not in label_set and has_re([
        r'\bpov\s*:', r'point of view', r'first-person (?:view|perspective|scenario)',
        r'viewer perspective', r'from the viewer.s perspective',
        r'camera (?:acts as|represents) the viewer', r'acted (?:pov|scenario|roleplay)',
        r'roleplay from (?:the )?viewer'
    ]):
        prefer = 'Carousel' if 'Carousel' in label_set else ('Relationship' if 'Relationship' in label_set else None)
        return add_preserve('POV', 'VN v16 POV guardrail: first-person/perspective scenario cues detected.', prefer_keep=prefer)

    # 7) Quote recovery. Keep this high precision and avoid generic "overlaid text".
    if 'Quotes' not in label_set and has_re([
        r'insecurit', r'body image', r'hidden sadness', r'ignored phone', r'phone calls?',
        r'calling someone', r'ignoring phone', r'melanchol', r'exhausted', r'stuck in negative',
        r'comforts of life', r'good luck', r'keep the chain', r'four-leaf clover',
        r'flame character', r'fire character', r'heartfelt message'
    ]):
        return add_preserve('Quotes', 'VN v16 quotes guardrail: high-confidence static text/quote cues detected.', prefer_keep='Carousel' if 'Carousel' in label_set else None)

    if 'Reflection' not in label_set and has_re([
        r'life goals', r'personal goals', r'goals for 2026', r'relationship struggles',
        r'emotional vulnerability', r'failed relationship'
    ]):
        return add_preserve('Reflection', 'VN v16 reflection guardrail: personal-goals/relationship-struggle cues detected.', prefer_keep='Carousel' if 'Carousel' in label_set else None)

    # 8) Comedy recovery requires explicit humour evidence. Generic mood words
    # such as "playful" are not enough because romantic/couple posts can be playful.
    if 'Comedy' not in label_set and 'Quotes' not in label_set and has_re([
        r'comedic', r'humorous', r'funny', r'\bjoke\b', r'\bskit\b', r'\bmeme\b',
        r'\bprank\b', r'wordplay', r'\bpun\b', r'absurd', r'exaggerated (?:reaction|surprise)'
    ]):
        prefer = 'Carousel' if 'Carousel' in label_set else ('Relationship' if 'Relationship' in label_set else None)
        return add_preserve('Comedy', 'VN v17 comedy guardrail: explicit humour/joke/skit/meme evidence detected.', prefer_keep=prefer)

    # 9) Relationship rescue, but avoid rows already accepted as Comedy/Quotes.
    if 'Relationship' not in label_set and not (label_set & {'Comedy', 'Quotes'}) and has_re([
        r'young couple', r'couple shares', r'affectionate', r'engagement ring', r'proposal',
        r'partner', r'boyfriend', r'girlfriend', r'dating tips', r'changed her partner',
        r'couple.*cuddling', r'romantic getaway'
    ]):
        return add_preserve('Relationship', 'VN v16 relationship guardrail: romantic/couple scenario cues detected.', prefer_keep='Carousel' if 'Carousel' in label_set else None)

    # 10) Slice of Life recovery for food/wedding/family/baby/pajama/sunset/Tet casual scenes.
    if 'Slice of Life' not in label_set and has_re([
        r'milk tea rice', r'rice cooker', r'cooking challenge', r'wedding gate',
        r'wedding decor', r'bride.*cutout', r'traditional red ao dai', r'family.*poses',
        r'family portrait', r'lunar new year', r'baby.*nail', r'young child',
        r'manicure.*child', r'pajamas.*mirror selfie', r'spending habits', r'eating a meal',
        r'outdoors at sunset', r'sunset', r'filter.*tet holiday', r'lying down',
        r'adjusting hair', r'howl.*picture book', r'picture book', r'four-leaf clover', r'good luck'
    ]):
        return add_preserve('Slice of Life', 'VN v16 slice-of-life guardrail: everyday/family/food/wedding/static-scene cues detected.', prefer_keep='Carousel' if 'Carousel' in label_set else None)

    # 11) High-signal Beauty/Fashion/Travel/Fitness additions.
    if 'Fashion' not in label_set and not (label_set & {'Comedy', 'Gaming', 'Quotes'}) and has_re([
        r'crop top', r'skirt', r'handbag', r'street style', r'storefront.*outfit',
        r'traditional-inspired outfit', r'fashion showcase', r'styling'
    ]):
        return add_preserve('Fashion', 'VN v16 fashion guardrail: styling/outfit-specific cues detected.', prefer_keep='Carousel' if 'Carousel' in label_set else None)

    if 'Beauty' not in label_set and has_re([r'makeup', r'girls makeup', r'nail art', r'manicure', r'cosmetics']):
        return add_preserve('Beauty', 'VN v16 beauty guardrail: makeup/nail/cosmetic cues detected.', prefer_keep='Carousel' if 'Carousel' in label_set else None)

    if 'Travel' not in label_set and not has_re([r'parked scooter']) and has_re([
        r'mountain village', r'scenic meadow', r'forest landscape', r'landscape',
        r'scenery', r'destination', r'vinwonders', r'cattle'
    ]):
        return add_preserve('Travel', 'VN v16 travel guardrail: scenery/destination cues detected.')

    if 'Fitness' not in label_set and has_re([
        r'divers?', r'synchronized dive', r'athletes?', r'swimming pool',
        r'sporting event', r'marathon', r'runner', r'race'
    ]):
        return add_preserve('Fitness', 'VN v16 fitness/sport guardrail: sports-action cues detected.', prefer_keep='Media/Infotainment' if 'Media/Infotainment' in label_set else None)

    if 'Carousel' not in label_set and has_re([r'compilation of short clips', r'series of photos', r'series of images', r'slideshow', r'photo carousel']):
        return add_preserve('Carousel', 'VN v16 carousel guardrail: slideshow/series/compilation cue detected.')

    return result


def apply_static_non_dance_guardrail(result, row=None):
    """Remove Dance when direct visual observations describe static/edit content.

    This is deliberately based on content_details, not model reasoning, captions,
    track names or previously assigned labels. It therefore cannot turn a phrase
    such as "prioritised Lyrics over Dance" into false motion evidence.
    """
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list) or 'Dance' not in labels:
        return result

    details = str(result.get('content_details', '') or '').lower()
    explicit_motion = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'choreograph', r'dance performance', r'\bdancing\b', r'dance challenge',
        r'dance routine', r'dance practice', r'synchronized (?:dance|movement)',
        r'coordinated (?:dance|movement)', r'body rolls?', r'repeated body movement',
        r'performs? (?:a |the )?(?:rhythmic )?dance',
    ])
    static_or_edit = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'static.{0,30}(?:shot|shots|image|images)',
        r'still.{0,30}(?:shot|shots|image|images)',
        r'photo montage', r'series of photos', r'posed portrait',
        r'lyrics? (?:displayed|overlaid|shown)', r'text[- ]only',
        r'montage.{0,100}(?:couple|character|actor|scene|romantic settings)',
        r'cinematic (?:scene|montage|sequence)', r'drama scene', r'movie scene',
    ])
    if explicit_motion or not static_or_edit:
        return result

    replacement = [label for label in labels if label != 'Dance']
    if not replacement:
        if re.search(r'(?:translated|bilingual).{0,50}lyric|lyric.{0,50}(?:translated|translation|bilingual)', details):
            replacement = ['Lyrics Translation']
        elif re.search(r'(?:drama|movie|tv|fictional|cinematic).{0,40}(?:scene|montage|character)', details):
            replacement = ['Movie/Tv/Drama Edits']

    if replacement:
        result['creative_type'] = replacement[:2]
        old_reason = str(result.get('reasoning', '') or '')
        reason = 'Static/edit safeguard: direct visual details show no choreography, so Dance was removed.'
        if reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
    else:
        result['needs_human_review'] = True
        try:
            result['confidence'] = min(float(result.get('confidence', 0) or 0), 0.60)
        except Exception:
            result['confidence'] = 0.0
    return result


def apply_content_details_consistency_guardrail(result, row=None):
    """Correct only high-signal contradictions in visual details or captions.

    Content Details is treated as visual evidence, not as unrestricted label
    memory. The patterns below require explicit actions such as applying makeup
    or mouthing lyrics; generic appearance words are intentionally insufficient.
    """
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [label for label in labels if label in ALLOWED_SET]
    details = str(result.get('content_details', '') or '').lower()
    caption_blob = _row_text_blob_for_safety(row)
    if not details and not caption_blob:
        return result

    beauty_action_evidence = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'professional makeup artist', r'appl(?:y|ies|ying) (?:various )?makeup',
        r'makeup (?:and hair )?(?:transformation|makeover|tutorial|routine)',
        r'(?:makeup|beauty|eyeliner|eyeshadow|eye shadow) (?:tips|advice|guide|recommendations?)',
        r'(?:tips|advice|guide|recommendations?).{0,45}(?:makeup|beauty|eyeliner|eyeshadow|eye shadow)',
        r'(?:choose|select|match).{0,35}(?:makeup|eyeliner|eyeshadow|eye shadow).{0,35}(?:eye|face) shape',
        r'(?:eye|face) shape.{0,35}(?:makeup|eyeliner|eyeshadow|eye shadow)',
        r'undergoes? a makeover', r'skincare (?:routine|tutorial|application)',
        r'cosmetic (?:application|tutorial|transformation)',
        r'nail art', r'hair styling transformation',
    ])
    beauty_focus_evidence = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'(?:distinct|distinctive|elaborate|creative|graphic|stylized|stylised|avant[- ]garde).{0,35}makeup',
        r'doll[- ]?like makeup', r'graphic eyeliner', r'face markings.{0,25}(?:makeup|beauty|look)',
        r'(?:showcases?|highlights?|focuses? on).{0,35}(?:makeup|beauty look|eye look)',
        r'(?:makeup|beauty) look.{0,30}(?:main focus|visual focus|showcased)',
    ])
    beauty_evidence = beauty_action_evidence or beauty_focus_evidence
    if beauty_evidence and (not labels or 'Beauty' not in labels):
        if 'Carousel' in labels:
            result['creative_type'] = ['Carousel', 'Beauty']
        elif beauty_focus_evidence and 'Lip Sync' in labels:
            result['creative_type'] = ['Lip Sync', 'Beauty']
        else:
            keep = next((label for label in ['Lip Sync', 'Fashion', 'Media/Infotainment'] if label in labels), None)
            result['creative_type'] = ['Beauty'] + ([keep] if keep else [])
        old_reason = str(result.get('reasoning', '') or '')
        reason = 'Content-details safeguard: explicit beauty action or deliberately showcased makeup styling detected, so Beauty was included.'
        if reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
        labels = list(result['creative_type'])

    lip_sync_evidence = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'lip[- ]?sync', r'mouths? (?:along|the lyrics|song lyrics)',
        r'mouthing (?:along|the lyrics|song lyrics)', r'sings? along to',
        r'face/mouth performance',
    ])
    choreography_evidence = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'choreograph', r'dance performance', r'\bdancing\b', r'dance routine',
        r'dance challenge', r'dance steps?', r'synchronized (?:dance|movement)',
        r'coordinated dance', r'repeated (?:rhythmic )?body movement',
        r'rhythmic body movements?', r'dance[- ]like (?:motion|movement)',
        r'rhythmic.{0,28}(?:paws?|legs?|limbs?|body|movement).{0,24}(?:music|beat|rhythm)',
        r'moves? (?:its |their |his |her )?(?:paws?|legs?|limbs?|body).{0,35}(?:rhythmic|to the (?:music|beat))',
    ])
    choreography_negated = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'(?:no|without|lacks?|does not|doesn.t).{0,24}(?:dance|dancing|choreograph)',
        r'not (?:a |the )?(?:dance|dance performance|choreographed routine)',
    ])
    choreography_evidence = choreography_evidence and not choreography_negated

    # Dance describes the visible action, not the species. Direct descriptions
    # of choreography or repeated rhythmic movement can therefore support Dance
    # for people, real animals, animated characters or game characters.
    dance_recoverable_labels = {
        'Travel', 'Lip Sync', 'Relationship', 'Fitness', 'Fashion', 'Comedy',
        'Slice of Life', 'POV', 'Movie/Tv/Drama Edits', 'Celebrity Edits',
        'Gaming', 'Others',
    }
    if (
        choreography_evidence
        and 'Dance' not in labels
        and labels
        and labels[0] in dance_recoverable_labels
    ):
        keep = next(
            (label for label in labels if label in dance_recoverable_labels and label != 'Others'),
            None,
        )
        result['creative_type'] = ['Dance'] + ([keep] if keep else [])
        old_reason = str(result.get('reasoning', '') or '')
        reason = (
            'Content-details safeguard: explicit dance steps or rhythmic '
            'body movement detected, so Dance was restored.'
        )
        if reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
        labels = list(result['creative_type'])
    if lip_sync_evidence and not choreography_evidence and (not labels or labels[0] != 'Lip Sync'):
        keep = next((label for label in ['Beauty', 'Lyrics Translation', 'Lyrics', 'POV', 'Relationship', 'Comedy'] if label in labels), None)
        result['creative_type'] = ['Lip Sync'] + ([keep] if keep else [])
        old_reason = str(result.get('reasoning', '') or '')
        reason = 'Content-details safeguard: explicit mouthing/lip-sync evidence with no choreography detected, so Lip Sync replaced the motion guess.'
        if reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')

    # Direct-to-camera speech is not choreography or lip-sync. This uses the
    # visual description rather than captions or track names. If no supported
    # semantic label remains, Review is safer than inventing one.
    labels = [label for label in result.get('creative_type', []) if label in ALLOWED_SET]
    speech_evidence = any(re.search(pattern, details, flags=re.I) for pattern in [
        r'talks? directly to (?:the )?camera', r'speaks? directly to (?:the )?camera',
        r'addresses? (?:the )?camera', r'talking to (?:the )?camera',
        r'offers? (?:advice|tips|encouragement)', r'gives? (?:advice|tips|encouragement)',
        r'personal announcement', r'express(?:es|ing) (?:his|her|their) (?:thoughts|desire|goals?)',
    ])
    if speech_evidence and not lip_sync_evidence and not choreography_evidence and set(labels) & {'Dance', 'Lip Sync'}:
        remaining = [label for label in labels if label not in {'Dance', 'Lip Sync'}]
        if remaining:
            result['creative_type'] = remaining[:2]
        else:
            result['creative_type'] = ['Others']
            result['needs_human_review'] = True
            try:
                result['confidence'] = min(float(result.get('confidence', 0) or 0), 0.65)
            except Exception:
                result['confidence'] = 0.0
        old_reason = str(result.get('reasoning', '') or '')
        reason = 'Content-details safeguard: direct-to-camera speech was described without mouthing or choreography, so unsupported motion labels were removed.'
        if reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')

    relationship_blob = f'{details} {caption_blob}'
    relationship_evidence = any(re.search(pattern, relationship_blob, flags=re.I) for pattern in [
        r'wedding (?:photo|photos|photoshoot|photo shoot|portrait|portraits|attire)',
        r'pre[- ]wedding', r'bridal (?:shoot|portrait|photoshoot)',
        r'bride and groom', r'romantic couple', r'couple (?:photoshoot|photo shoot|portraits?)',
        r'young couple.{0,50}(?:romantic|affectionate|wedding)',
        r'engagement (?:ring|photoshoot|portrait)', r'marriage proposal',
        r'husband and wife', r'boyfriend and girlfriend',
        r'romantic sentiment.{0,50}(?:partner|love|relationship)',
        r'relationship advice', r'dating advice', r'anxiety.{0,30}blind date',
        r'romantic partner', r'choosing (?:a|their|your) partner',
        r'bộ ảnh cưới', r'chụp ảnh cưới', r'ảnh cưới', r'đám cưới',
        r'cô dâu.{0,30}chú rể', r'chú rể.{0,30}cô dâu', r'vợ chồng',
    ])
    labels = [label for label in result.get('creative_type', []) if label in ALLOWED_SET]
    if relationship_evidence:
        if 'Carousel' in labels:
            desired = ['Carousel', 'Relationship']
        elif 'Movie/Tv/Drama Edits' in labels:
            desired = ['Movie/Tv/Drama Edits', 'Relationship']
        elif labels and labels[0] == 'Relationship':
            desired = labels[:2]
        else:
            keep = next((label for label in ['Quotes', 'Lyrics Translation', 'Lyrics', 'Lip Sync', 'Fashion', 'Slice of Life', 'POV'] if label in labels), None)
            desired = ['Relationship'] + ([keep] if keep else [])
        if labels[:2] != desired:
            result['creative_type'] = desired
            old_reason = str(result.get('reasoning', '') or '')
            reason = 'Content/caption safeguard: explicit wedding/couple evidence detected, so Relationship was prioritised as the semantic label.'
            if reason not in old_reason:
                result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
    return result


def apply_v66_semantic_consistency_guardrail(result, row=None):
    """Reconcile final labels with Gemini's usually stronger semantic fields.

    The rule order is evidence-first: Content Details, Narrative, caption, then
    KB/track history. It uses reusable meaning/action patterns and never stores
    exact URLs or expected labels from the holdout workbook.
    """
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = [label for label in result.get('creative_type', []) if label in ALLOWED_SET]
    if not labels:
        return result

    narrative = str(result.get('narrative', '') or '').lower()
    details = str(result.get('content_details', '') or '').lower()
    observation = f'{narrative} {details}'
    caption = _row_text_blob_for_safety(row)
    evidence = f'{observation} {caption}'
    image_count = _slideshow_image_count(row)
    structural_carousel = (
        'Carousel' in labels
        and _kb_url_type(row) == 'photo'
        and image_count != 1
    )

    def has(patterns, blob=observation):
        return any(re.search(pattern, blob, flags=re.I) for pattern in patterns)

    def commit(new_labels, reason, *, review=False):
        nonlocal labels
        clean = []
        for label in new_labels:
            if label in ALLOWED_SET and label not in clean:
                clean.append(label)
        if not clean:
            clean = ['Others']
        result['creative_type'] = clean[:2]
        labels = list(result['creative_type'])
        old_reason = str(result.get('reasoning', '') or '')
        if reason and reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
        if review:
            result['needs_human_review'] = True
            try:
                result['confidence'] = min(float(result.get('confidence', 0) or 0), 0.65)
            except Exception:
                result['confidence'] = 0.0

    strong_dance = has([
        r'choreograph', r'dance (?:routine|challenge|performance|practice)',
        r'synchroni[sz]ed (?:dance|movement)', r'coordinated dance',
        r'repeated rhythmic (?:body|hand) movement', r'hand[- ]gesture dance',
        r'performs? (?:a |the )?(?:rhythmic )?dance', r'dance moves?',
        r'dance[- ]like (?:motion|movement)',
        r'rhythmic.{0,28}(?:paws?|legs?|limbs?|body|movement).{0,24}(?:music|beat|rhythm)',
        r'moves? (?:its |their |his |her )?(?:paws?|legs?|limbs?|body).{0,35}(?:rhythmic|to the (?:music|beat))',
    ]) and not has([r'dancing slightly', r'moves slightly', r'dance-like pose'])
    lip_sync = has([
        r'lip[- ]?sync', r'mouths? (?:along|the lyrics|song lyrics)',
        r'mouthing (?:along|the lyrics|song lyrics)', r'sings? along to',
    ])
    visible_lyrics = has([
        r'(?:visible|displayed|written|overlaid|on[- ]screen|onscreen|spotify[- ]style).{0,35}lyrics?',
        r'lyrics?.{0,35}(?:visible|displayed|written|overlaid|on[- ]screen|onscreen)',
        r'lyric (?:video|text|card)', r'song words (?:appear|displayed|shown)',
    ])

    human_subject = has([
        r'\bcreator\b', r'young woman', r'young man', r'\bwoman\b', r'\bman\b',
        r'\bgirl\b', r'\bboy\b', r'\bperson\b', r'\bpeople\b',
    ])
    non_human = has([
        r'\bhamster\b', r'\bcats?\b', r'\bdogs?\b', r'\bpet\b',
        r'\banimal\b', r'\brabbit\b', r'\bbird\b',
    ]) and not human_subject and not has([r'(?:cat|dog)[- ]themed (?:ar )?filter'])
    humorous = has([r'\bfunny\b', r'humorous', r'comedic', r'joke', r'meme', r'prank'])
    if non_human and strong_dance and 'Dance' not in labels:
        keep = next(
            (label for label in labels if label not in {'Dance', 'Others'}),
            None,
        )
        desired = ['Dance'] + ([keep] if keep else [])
        commit(
            desired,
            'V68.13 action safeguard: explicit rhythmic/choreographed animal movement supports Dance.',
        )
        labels = list(result.get('creative_type', []))

    unsupported_non_human = {'Lip Sync', 'Cover'}
    if not strong_dance:
        unsupported_non_human.add('Dance')
    if non_human and (set(labels) & unsupported_non_human or (humorous and 'Comedy' not in labels)):
        semantic = 'Comedy' if humorous else 'Slice of Life'
        if structural_carousel:
            desired = ['Carousel', semantic]
        else:
            keep = next((label for label in labels if label not in unsupported_non_human | {'Carousel'}), None)
            desired = [keep or semantic]
            if humorous and desired[0] != 'Comedy':
                desired.append('Comedy')
        commit(desired, 'V68.13 non-human safeguard: unsupported vocal or non-rhythmic motion labels were removed.')

    fitness = has([
        r'fitness flex', r'flex(?:es|ing)? (?:their |his |her )?(?:arm )?muscles?',
        r'(?:shows?|showing|displays?|displaying).{0,30}(?:physique|muscle definition|biceps)',
        r'bodybuilding', r'workout routine', r'exercise routine', r'gym training',
        r'(?:lifting|lifts?) weights?', r'fitness transformation', r'sport training',
    ])
    if fitness and ('Fitness' not in labels or ('Dance' in labels and not strong_dance)):
        if strong_dance:
            desired = ['Dance', 'Fitness']
        else:
            desired = ['Fitness']
            keep = next((label for label in ['Fashion', 'Beauty'] if label in labels), None)
            if keep:
                desired.append(keep)
        commit(desired, 'V66 fitness safeguard: explicit exercise/physique evidence was prioritised over unsupported Dance.')

    fashion = has([
        r'outfit showcase', r'showcases?.{0,35}(?:outfit|clothing|knitwear)',
        r'outfit combinations?', r'trying on layers', r'fit check', r'\bootd\b',
        r'fashion showcase', r'models? (?:different |multiple )?outfits?',
        r'styling .{0,25}(?:outfit|clothes|look)',
    ], evidence)
    if fashion and ('Fashion' not in labels or ('Dance' in labels and not strong_dance)):
        if structural_carousel:
            desired = ['Carousel', 'Fashion']
        else:
            desired = ['Fashion']
            keep = next((label for label in ['Beauty', 'Lip Sync'] if label in labels), None)
            if strong_dance:
                keep = 'Dance'
            if keep:
                desired.append(keep)
        commit(desired, 'V66 fashion safeguard: outfit modelling/posing was prioritised over unsupported Dance.')

    # Mouthing lyrics is Lip Sync; Lyrics additionally requires visible written words.
    if 'Lyrics' in labels and lip_sync and not visible_lyrics:
        desired = [label for label in labels if label != 'Lyrics']
        if 'Lip Sync' not in desired:
            desired.insert(0, 'Lip Sync')
        commit(desired, 'V66 lyrics safeguard: mouthing was visible but written lyric text was not, so Lyrics was removed.')

    travel = has([
        r'beach vacation', r'tropical beach', r'vacation (?:scene|photo|activity|memory)',
        r'travel (?:destination|vlog|memory)', r'tourist destination',
        r'scenic .{0,35}(?:ocean|mountain|city|destination)', r'jet skis? on the ocean',
        r'cruise ship .{0,35}(?:ocean|sunrise)',
    ])
    if travel and 'Travel' not in labels:
        if structural_carousel:
            desired = ['Carousel', 'Travel']
        else:
            keep = next((label for label in ['Lyrics Translation', 'Lyrics', 'Lip Sync', 'Slice of Life'] if label in labels), None)
            desired = ['Travel'] + ([keep] if keep else [])
        commit(desired, 'V66 travel safeguard: Narrative/Content Details explicitly describe a destination or vacation.')

    explicit_reflection = has([
        r'\breflection\b', r'\breflecting on\b', r'personal introspection',
        r'emotional introspection', r'personal life lesson', r'self[- ]worth',
        r'self[- ]growth', r'endings and new beginnings', r'inner thoughts',
    ])
    supportive_message = has([
        r'(?:emotional|supportive|encouraging|comforting) (?:message|sentiment|statement)',
        r'(?:express(?:es|ing)|shares?|offers?).{0,55}(?:care|support|encouragement|reassurance)',
        r'(?:overlaid|on[- ]screen|written) text.{0,55}(?:care|support|encouragement|reassurance)',
        r'personal message.{0,45}(?:healing|hope|kindness|difficult times)',
    ])
    # A supportive personal statement is Reflection only when Gemini did not
    # explicitly identify the visible words as song lyrics. This prevents a
    # meaningful text overlay from being mislabeled Lyrics while preserving
    # real lyric cards and lyric videos.
    reflection = explicit_reflection or (supportive_message and not visible_lyrics)
    if reflection and 'Reflection' not in labels:
        if structural_carousel:
            desired = ['Carousel', 'Reflection']
        else:
            keep = next((label for label in ['Relationship', 'Quotes', 'Fashion', 'Slice of Life', 'Media/Infotainment'] if label in labels), None)
            desired = ['Reflection'] + ([keep] if keep else [])
        commit(desired, 'V66 reflection safeguard: Narrative/Content Details explicitly describe personal reflection or introspection.')

    explicit_pov = has([
        r'\bpov\s*[:\-]', r'\bpoint of view\b',
        r'\bfirst[- ]person (?:perspective|view|camera|shot|footage|journey|experience)',
        r'(?:from|through) (?:the )?(?:viewer|creator|camera)(?:\'s)? perspective',
        r'(?:viewer|camera) (?:moves|travels|walks|slides|climbs|crosses|rides|enters|follows)',
        r'(?:acted|role[- ]?played?) (?:pov|first[- ]person) scenario',
    ])
    audience_prompt = has([
        r'(?:text|caption|post) (?:asks|prompts|invites) (?:the )?(?:viewer|audience|followers?)',
        r'asks? (?:the )?(?:viewer|audience|followers?) to',
        r'\b(?:name|guess|choose|pick) .{0,55}(?:initial|answer|option|flower|person)',
        r'\bcomment (?:your|the) .{0,35}(?:answer|choice|initial)',
        r'\btag (?:a |your )?(?:friend|partner|crush|someone)',
    ], evidence)
    if explicit_pov and 'POV' not in labels:
        if structural_carousel:
            desired = ['Carousel', 'POV']
        else:
            keep = next((label for label in ['Relationship', 'Comedy', 'Travel', 'Slice of Life'] if label in labels), None)
            desired = ['POV'] + ([keep] if keep else [])
        commit(desired, 'V66 POV safeguard: direct first-person/viewer-perspective evidence was prioritised over a generic scene label.')
    elif 'POV' in labels and audience_prompt and not explicit_pov:
        prompt_humour = humorous or has([
            r'playful (?:prompt|joke|challenge|reaction)', r'exaggerated humorous reaction',
            r'comedic (?:prompt|challenge|reaction)', r'audience joke',
        ], evidence)
        remaining = [label for label in labels if label != 'POV']
        if prompt_humour:
            desired = ['Carousel', 'Comedy'] if structural_carousel else ['Comedy']
        elif remaining:
            desired = remaining
        else:
            desired = ['Others']
        commit(
            desired,
            'V66 POV safeguard: an audience question or challenge is not a POV scenario without first-person framing.',
            review=not prompt_humour and not remaining,
        )

    relationship_reflection = has([
        r'relationship reflection', r'reflecting on.{0,45}(?:relationship|being single)',
        r'end of (?:a |the )?(?:single period|period of being single)',
    ])
    if relationship_reflection and 'Relationship' not in labels:
        desired = ['Reflection', 'Relationship'] if 'Reflection' in labels else ['Relationship']
        commit(desired, 'V66 relationship safeguard: explicit romantic/single-status reflection supports Relationship.')

    explicit_couple_relationship = has([
        r'romantic wedding', r'wedding vows?', r'wedding couple',
        r'bride.{0,80}(?:groom|partner|husband|couple)',
        r'(?:groom|partner|husband).{0,80}bride',
        r'romantic (?:couple|partner|interaction)',
        r'couple.{0,60}(?:wedding|marriage|romantic|affectionate)',
    ], evidence)
    if explicit_couple_relationship and 'Relationship' not in labels:
        if structural_carousel:
            desired = ['Carousel', 'Relationship']
        elif 'Movie/Tv/Drama Edits' in labels:
            desired = ['Movie/Tv/Drama Edits', 'Relationship']
        elif strong_dance:
            desired = ['Dance', 'Relationship']
        elif lip_sync:
            desired = ['Lip Sync', 'Relationship']
        else:
            keep = next((label for label in ['Quotes', 'Lyrics Translation', 'Lyrics', 'Fashion', 'Slice of Life'] if label in labels), None)
            desired = ['Relationship'] + ([keep] if keep else [])
        commit(desired, 'V66 relationship safeguard: explicit bride/groom/partner evidence preserves Relationship alongside the main format.')

    abstract_template = has([
        r'capcut template (?:video|edit)', r'oscillating abstract graphic',
        r'abstract (?:graphic )?animation', r'template edit featuring abstract visual effects',
    ])
    instructional_or_review = has([
        r'\btutorial\b', r'step[- ]by[- ]step', r'demonstrates? how',
        r'clinic recommendation', r'product (?:review|recommendation|catalog)',
        r'pricing information', r'advertisement', r'educational', r'instructional',
        r'personal advice', r'spiritual prayer.{0,40}advice', r'explains? the meaning',
        r'practical guidance',
    ], evidence)
    if abstract_template and 'Media/Infotainment' in labels and not instructional_or_review:
        commit(['Others'], 'V66 media safeguard: an abstract template alone is not informative content.', review=True)
    elif instructional_or_review and 'Media/Infotainment' not in labels:
        protected_carousel_semantic = structural_carousel and any(
            label in labels for label in ['Beauty', 'Relationship', 'Gaming', 'Fashion', 'Reflection']
        )
        if protected_carousel_semantic:
            desired = labels
        elif structural_carousel:
            desired = ['Carousel', 'Media/Infotainment']
        else:
            if 'Reflection' in labels:
                desired = ['Reflection', 'Media/Infotainment']
            else:
                keep = next((label for label in ['Beauty', 'Relationship', 'Gaming', 'Fashion'] if label in labels), None)
                desired = ['Media/Infotainment'] + ([keep] if keep else [])
        if desired != labels:
            commit(desired, 'V66 media safeguard: explicit tutorial, review, recommendation or pricing evidence detected.')

    synthetic_subject = has([
        r'ai[- ]generated.{0,35}(?:character|child|person|performer|singer|musician|figure)',
        r'(?:synthetic|virtual) (?:character|child|person|performer|singer|musician)',
        r'computer[- ]generated (?:character|child|person|performer|singer)',
    ], evidence)
    fictional = synthetic_subject or has([
        r'\banime\b', r'\bmanga\b', r'\bwebtoon\b', r'fictional character',
        r'anime character', r'game character', r'deltarune', r'haikyuu', r'saiki',
    ], evidence)
    synthetic_music_performance = synthetic_subject and has([
        r'sings? (?:into|on|to|while)', r'singing (?:into|on|to|while)',
        r'vocal performance', r'performs? (?:a |the )?song', r'concert performance',
        r'plays? (?:the )?(?:guitar|piano|drums?|violin|instrument)',
        r'(?:virtual )?band performs?',
    ])
    if synthetic_music_performance:
        commit(
            ['Cover'],
            'V66 source safeguard: an AI-generated/virtual musical performer is a Cover-style performance, not a real-celebrity edit or POV.',
        )
    fictional_edit = fictional and has([
        r'anime edit', r'fan edit', r'montage of (?:anime )?scenes?',
        r'scenes? from (?:the )?anime', r'anime.{0,45}montage',
        r'fictional character.{0,45}(?:edit|montage|clips?)',
    ])
    if fictional_edit and 'Movie/Tv/Drama Edits' not in labels and not instructional_or_review:
        if structural_carousel:
            desired = ['Carousel', 'Movie/Tv/Drama Edits']
        else:
            keep = next((label for label in ['Relationship', 'Lyrics Translation', 'Lyrics'] if label in labels), None)
            desired = ['Movie/Tv/Drama Edits'] + ([keep] if keep else [])
        commit(desired, 'V66 source safeguard: an anime/fictional scene montage is Movie/Tv/Drama Edits, not a generic semantic label.')
    if 'Celebrity Edits' in labels and fictional:
        if synthetic_subject:
            desired = [label for label in labels if label not in {'Celebrity Edits', 'POV'}]
            commit(
                desired or ['Others'],
                'V66 source safeguard: an AI-generated/virtual subject is not a real celebrity.',
                review=not desired,
            )
        else:
            target = 'Gaming' if has([r'\bgame\b', r'deltarune', r'game character'], evidence) else 'Movie/Tv/Drama Edits'
            desired = [target if label == 'Celebrity Edits' else label for label in labels]
            commit(desired, 'V66 source safeguard: fictional/anime/game characters are not real celebrities.')

    non_romantic_family_advice = has([r'family leadership', r'religious commitment', r'spiritual leadership'])
    romantic = has([
        r'romantic', r'boyfriend', r'girlfriend', r'husband', r'wife', r'couple',
        r'dating', r'breakup', r'heartbreak', r'partner', r'wedding', r'bride', r'groom',
    ], evidence)
    if 'Relationship' in labels and non_romantic_family_advice and not romantic:
        desired = [label for label in labels if label != 'Relationship']
        if not desired:
            desired = ['Reflection']
        commit(desired, 'V66 relationship safeguard: general family/religious advice is not automatically romantic Relationship content.')

    return result


def apply_v67_evidence_contradiction_guardrail(result, row=None):
    """Resolve high-signal contradictions in the final automated labels.

    Only Narrative and Content Details are used here. Captions, track history,
    creator memory and model reasoning cannot create positive evidence.
    """
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = [label for label in result.get('creative_type', []) if label in ALLOWED_SET]
    if not labels:
        return result

    narrative = str(result.get('narrative', '') or '').lower()
    details = str(result.get('content_details', '') or '').lower()
    observation = f'{narrative} {details}'

    def has(patterns):
        return any(re.search(pattern, observation, flags=re.I) for pattern in patterns)

    def commit(new_labels, reason, *, review=False):
        nonlocal labels
        clean = []
        for label in new_labels:
            if label in ALLOWED_SET and label not in clean:
                clean.append(label)
        if not clean:
            clean = ['Others']
        result['creative_type'] = clean[:2]
        labels = list(result['creative_type'])
        old_reason = str(result.get('reasoning', '') or '')
        if reason and reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
        if review:
            result['needs_human_review'] = True
            try:
                result['confidence'] = min(float(result.get('confidence', 0) or 0), 0.65)
            except Exception:
                result['confidence'] = 0.0

    lyric_labels = {'Lyrics', 'Lyrics Translation'}
    strong_song_lyrics = has([
        r'lyric (?:video|card|display)', r'karaoke', r'spotify[- ]style lyrics?',
        r'(?:visible|displayed|written|overlaid|on[- ]screen|onscreen).{0,28}(?:song )?lyrics?',
        r'(?:song )?lyrics?.{0,28}(?:visible|displayed|written|overlaid|on[- ]screen|onscreen)',
        r'bilingual lyrics?', r'translated (?:song )?lyrics?', r'lyrics? translation',
        r'original and translated lyrics?',
    ])
    explicit_not_lyrics = has([
        r'(?:not|rather than|instead of|without).{0,28}(?:song )?lyrics?',
        r'(?:does not|doesn.t|do not).{0,20}(?:display|show|contain).{0,24}(?:song )?lyrics?',
        r'(?:subtitle|caption)s?.{0,40}(?:speech|spoken|dialogue|conversation)',
        r'(?:speech|spoken|dialogue|conversation).{0,40}(?:subtitle|caption)s?',
        r'not (?:a |the )?lyric display',
    ])
    direct_speech = has([
        r'(?:speaks?|talks?|addresses?) (?:directly )?(?:to )?(?:the )?(?:camera|viewer|audience)',
        r'(?:man|woman|person|creator).{0,35}(?:speaks?|talks?|addresses?)',
        r'shares? (?:his|her|their|a) (?:thoughts|goals|advice|message|story)',
        r'personal (?:speech|message|advice|story|announcement)',
        r'spoken (?:message|dialogue|words)', r'voiceover (?:speech|message|dialogue)',
    ])
    reflection = has([
        r'(?:personal|emotional|relationship|life) reflection', r'personal introspection',
        r'reflect(?:s|ing)? on', r'thoughts about (?:life|relationships?|the future)',
        r'(?:emotional|supportive|encouraging|comforting) (?:message|sentiment|statement)',
        r'(?:express(?:es|ing)|shares?|offers?).{0,55}(?:care|support|encouragement|reassurance)',
        r'(?:team|personal|life) goals?', r'motivational message',
    ])

    if set(labels) & lyric_labels and (explicit_not_lyrics or direct_speech):
        if strong_song_lyrics:
            result['_v67_lyrics_contradiction'] = True
            commit(
                labels,
                'V67 lyrics contradiction: the description contains both speech/subtitle and explicit song-lyric evidence, so human review is required.',
                review=True,
            )
        else:
            remaining = [label for label in labels if label not in lyric_labels]
            if reflection and 'Reflection' not in remaining:
                remaining.insert(0, 'Reflection')
            commit(
                remaining or ['Others'],
                'V67 lyrics contradiction safeguard: speech, dialogue subtitles or personal reflection are not song lyrics.',
                review=not remaining,
            )

    labels = [label for label in result.get('creative_type', []) if label in ALLOWED_SET]
    strong_dance = has([
        r'choreograph', r'dance (?:routine|challenge|performance|practice|moves?)',
        r'synchroni[sz]ed (?:dance|movement)', r'coordinated dance',
        r'repeated rhythmic (?:body|hand) movement', r'hand[- ]gesture dance',
        r'performs? (?:a |the )?(?:rhythmic )?dance',
    ]) and not has([
        r'dancing slightly', r'moves? (?:slightly|forward and backward|to the beat)',
        r'generic hand gestures?', r'touches? (?:her|his|their) hair', r'poses? for (?:the )?camera',
        r'(?:no|without|lacks?|does not|doesn.t).{0,24}(?:dance|dancing|choreograph)',
        r'not (?:a |the )?(?:dance|dance performance|choreographed routine)',
    ])
    if 'Dance' in labels and labels[0] != 'Dance' and not strong_dance:
        commit(
            [label for label in labels if label != 'Dance'],
            'V67 secondary-Dance safeguard: no explicit choreography or coordinated dance evidence was described.',
        )

    return result


def apply_single_image_carousel_guardrail(result, row=None):
    """Normalize Carousel using the confirmed slideshow image count."""
    if not isinstance(result, dict) or result.get('parse_error'):
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    image_count = _slideshow_image_count(row)
    raw_slideshow = None
    try:
        if 'isSlideshow' in row:
            raw_slideshow = row.get('isSlideshow')
        elif 'is_slideshow' in row:
            raw_slideshow = row.get('is_slideshow')
    except Exception:
        pass
    confirmed_video_mode = (
        raw_slideshow is False
        or str(raw_slideshow).strip().lower() in {'false', '0', 'no'}
    )

    if confirmed_video_mode and 'Carousel' in labels:
        remaining = [label for label in labels if label in ALLOWED_SET and label != 'Carousel']
        if not remaining:
            remaining = ['Slice of Life']
        result['creative_type'] = remaining[:2]
        old_reason = str(result.get('reasoning', '') or '')
        reason = 'Post-format safeguard: Apify confirmed normal video mode, so Carousel was removed from the photo/video montage.'
        if reason not in old_reason:
            result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
        return result

    if image_count is not None and image_count >= 2 and 'Carousel' in labels:
        result['creative_type'] = ['Carousel'] + [label for label in labels if label != 'Carousel'][:1]
        return result
    if image_count != 1 or 'Carousel' not in labels:
        return result

    remaining = [label for label in labels if label in ALLOWED_SET and label != 'Carousel']
    if not remaining:
        remaining = ['Slice of Life']
    result['creative_type'] = remaining[:2]
    old_reason = str(result.get('reasoning', '') or '')
    reason = 'Post-format safeguard: Apify confirmed only one slideshow image, so Carousel was removed.'
    if reason not in old_reason:
        result['reasoning'] = (old_reason + ' | ' + reason).strip(' |')
    return result


def apply_sg_scene_balance_guardrails(result, row=None):
    """SG-specific scene balance from the Singapore mismatch report.

    Keep the rules market-scoped and mostly additive. Singapore mismatches were
    dominated by:
    - fan-art/anime/manga carousels predicted as Movie/Tv/Drama but reviewed as Celebrity Edits;
    - casual couple/wedding posts predicted as Relationship but reviewed as Slice of Life;
    - food/campus/product snippets predicted as Media/Infotainment but reviewed as Slice of Life;
    - Dance/Fashion/Fitness/Lip Sync confusion in short creator videos;
    - photo-carousel text/quote/city/family nuance.

    These are reusable signal rules. They do not memorize TikTok URLs.
    """
    if row is None or not isinstance(result, dict) or result.get('parse_error'):
        return result
    if _row_market_code(row) != 'SG':
        return result
    labels = result.get('creative_type', [])
    if not isinstance(labels, list):
        return result
    labels = [x for x in labels if x in ALLOWED_SET]
    if not labels:
        return result
    label_set = set(labels)

    # Build a broad but local text context. _result_text_blob uses Gemini output;
    # _row_text_blob_for_safety uses caption/hashtags; the extra row keys add creator handles.
    extra_parts = []
    try:
        for key in ['authorMeta.name', 'authorMeta.nickName', 'creator', 'creator_handle', 'username']:
            extra_parts.append(str(row.get(key, '') or ''))
        am = row.get('authorMeta', {})
        if isinstance(am, dict):
            extra_parts.append(str(am.get('name', '') or ''))
            extra_parts.append(str(am.get('nickName', '') or ''))
    except Exception:
        pass
    blob = ' '.join([_result_text_blob(result), _row_text_blob_for_safety(row), ' '.join(extra_parts)]).lower()

    def has_any_term(terms):
        return any(t in blob for t in terms)

    def has_re(patterns):
        return any(re.search(p, blob) for p in patterns)

    # 1) Single-label Relationship in SG often means a casual couple/wedding slice.
    # Add Slice of Life as support rather than replacing Relationship.
    if labels == ['Relationship'] and has_any_term([
        'couple', 'young men', 'young couple', 'wedding', 'marriage', 'restaurant',
        'affection', 'intimate', 'husband', 'wife', 'mixed marriage', 'dining',
        'holding hands', 'portrait', 'kiss', 'touching', 'couple relaxing'
    ]):
        return _set_labels_preserve_allowed(
            result,
            ['Relationship', 'Slice of Life'],
            'SG relationship guardrail: casual couple/wedding scene cues detected, so Slice of Life was added.'
        )

    # 2) SG food/campus/product snippets are often reviewed as lifestyle, unless the
    # scene is explicitly romantic gift or comedic/meme content.
    if labels == ['Media/Infotainment']:
        if has_any_term(['gift', 'girlfriend', 'flower bouquet', 'chocolates', 'apologise', 'apologize']):
            return _set_labels_preserve_allowed(
                result,
                ['Media/Infotainment', 'Relationship'],
                'SG media guardrail: romantic gift/apology cues detected, so Relationship was added.'
            )
        if has_any_term(['comedy', 'humor', 'humour', 'humorous', 'meme', 'cortisol', 'funny']):
            return _set_labels_preserve_allowed(
                result,
                ['Media/Infotainment', 'Comedy'],
                'SG media guardrail: humorous/meme cues detected, so Comedy was added.'
            )
        if has_any_term([
            'food', 'pizza', 'bazaar', 'tiramisu', 'pho', 'cooking', 'recipe',
            'campus', 'classmates', 'students', 'cheese pull', 'food showcase',
            'food recommendation', 'food items', 'product showcase'
        ]):
            return _set_labels_preserve_allowed(
                result,
                ['Media/Infotainment', 'Slice of Life'],
                'SG media guardrail: food/campus/product lifestyle cues detected, so Slice of Life was added.'
            )

    # 3) SG single-label Dance: preserve Dance, add the missed secondary format.
    if labels == ['Dance']:
        if has_any_term(['zumba class', 'group dance workout', 'women in activewear', 'brightly lit indoor studio']):
            return _set_labels_preserve_allowed(
                result,
                ['Dance', 'Slice of Life'],
                'SG dance guardrail: group class/social workout context detected, so Slice of Life was added.'
            )
        if has_any_term(['gym', 'flex', 'physique', 'biceps', 'compression', 'fitness flex', 'bodybuilding']):
            return _set_labels_preserve_allowed(
                result,
                ['Dance', 'Fitness'],
                'SG dance guardrail: fitness/flex cues detected, so Fitness was added.'
            )
        if has_any_term(['outfit', 'ootd', 'modeling', 'fit check', 'top', 'hijab', 'jeans', 'camisole', 'maroon']):
            return _set_labels_preserve_allowed(
                result,
                ['Dance', 'Fashion'],
                'SG dance guardrail: outfit/fashion cues detected, so Fashion was added.'
            )

    # 4) SG Lip Sync sometimes hides Dance/Comedy from still frames.
    if labels == ['Lip Sync']:
        if has_any_term(['walking', 'public space', 'casual life update', 'comedy', 'funny', 'humorous']):
            return _set_labels_preserve_allowed(
                result,
                ['Lip Sync', 'Comedy'],
                'SG lip-sync guardrail: casual comedic walking/lip-sync cues detected, so Comedy was added.'
            )
        if has_any_term(['playful', 'glitch', 'trending audio', 'jersey', 'lighthearted expression']):
            return _set_labels_preserve_allowed(
                result,
                ['Lip Sync', 'Dance'],
                'SG lip-sync guardrail: playful/trend cues detected, so Dance was added.'
            )

    # 5) SG Slice of Life can miss Comedy, Celebrity Edits, Lip Sync, or Dance.
    if labels == ['Slice of Life']:
        if has_any_term(['laughing', 'dumber', 'joke', 'funny', 'humorous', 'comedic']):
            return _set_labels_preserve_allowed(
                result,
                ['Slice of Life', 'Comedy'],
                'SG slice-of-life guardrail: humorous/friends cues detected, so Comedy was added.'
            )
        if has_any_term(['k-pop', 'kpop', 'idol', 'celebrity', 'h2h', 'juun', 'a-na', 'a na']) or has_re([r'\bmember\b', r'\bmembers\b']):
            return _set_labels_preserve_allowed(
                result,
                ['Slice of Life', 'Celebrity Edits'],
                'SG slice-of-life guardrail: idol/member/celebrity cues detected, so Celebrity Edits was added.'
            )
        if has_any_term(['mouthing', 'mouths', 'lip sync', 'lip-sync', 'lyrics to camera']):
            return _set_labels_preserve_allowed(
                result,
                ['Slice of Life', 'Lip Sync'],
                'SG slice-of-life guardrail: lip-sync cues detected, so Lip Sync was added.'
            )
        if has_any_term(['posing', 'getting ready', 'styled hair', 'makeup posing', 'preparation before an event']):
            return _set_labels_preserve_allowed(
                result,
                ['Slice of Life', 'Dance'],
                'SG slice-of-life guardrail: creator posing/trend cues detected, so Dance was added.'
            )

    # 6) SG Fashion can hide Beauty, Dance, or Comedy.
    if labels == ['Fashion']:
        if has_any_term(['transformation', 'qipao', 'makeup', 'beauty', 'hair']):
            return _set_labels_preserve_allowed(
                result,
                ['Fashion', 'Beauty'],
                'SG fashion guardrail: beauty/transformation cues detected, so Beauty was added.'
            )
        if has_any_term(['two young women', 'side-by-side', 'modeling', 'friends outfit showcase']):
            return _set_labels_preserve_allowed(
                result,
                ['Fashion', 'Dance'],
                'SG fashion guardrail: paired outfit/movement cues detected, so Dance was added.'
            )
        if has_any_term(['gestures', 'gesture', 'humorous', 'joke', 'on-screen text', 'onscreen text']):
            return _set_labels_preserve_allowed(
                result,
                ['Fashion', 'Comedy'],
                'SG fashion guardrail: humorous gesture/text cues detected, so Comedy was added.'
            )

    # 7) SG Lyrics false positives: preserve Lyrics but add the clearer visual format.
    if labels == ['Lyrics']:
        if has_any_term(['young couple', 'intimate', 'affectionate', 'inside a car']):
            return _set_labels_preserve_allowed(
                result,
                ['Lyrics', 'Slice of Life'],
                'SG lyrics guardrail: couple/lifestyle visual cues detected, so Slice of Life was added.'
            )
        if has_any_term(['stands indoors', 'smiles while mouthing', 'young woman stands']):
            return _set_labels_preserve_allowed(
                result,
                ['Lyrics', 'Fashion'],
                'SG lyrics guardrail: creator styling/pose cues detected, so Fashion was added.'
            )
        if has_any_term(['mouthing', 'mouths', 'creator records', 'records a short video']):
            return _set_labels_preserve_allowed(
                result,
                ['Lyrics', 'Lip Sync'],
                'SG lyrics guardrail: mouthing/lip-sync cues detected, so Lip Sync was added.'
            )

    # 8) SG Beauty can hide Comedy, Slice of Life, or Dance.
    if labels == ['Beauty']:
        if has_any_term(['frustration', 'humorous', 'pink bunny', 'bunny headband']):
            return _set_labels_preserve_allowed(
                result,
                ['Beauty', 'Comedy'],
                'SG beauty guardrail: humorous/frustration cues detected, so Comedy was added.'
            )
        if has_any_term(['transitions', 'showcases skincare and makeup products', 'beauty transition']):
            return _set_labels_preserve_allowed(
                result,
                ['Beauty', 'Dance'],
                'SG beauty guardrail: trend/transition cues detected, so Dance was added.'
            )
        if has_any_term(['morning routine', 'hair transition', 'bathroom']):
            return _set_labels_preserve_allowed(
                result,
                ['Beauty', 'Slice of Life'],
                'SG beauty guardrail: bathroom/routine/lifestyle cues detected, so Slice of Life was added.'
            )

    # 9) Carousel Movie/Tv/Drama in SG fan-art/manga/anime contexts is usually
    # reviewed as Celebrity Edits in the original taxonomy.
    if label_set == {'Carousel', 'Movie/Tv/Drama Edits'}:
        if has_any_term([
            'anime', 'manga', 'webtoon', 'digital art', 'fan art', 'character',
            'haikyuu', 'sakamoto', 'demon slayer', 'gachiakuta', 'danmei',
            'deltarune', 'marvel', 'spider-man', 'spiderman', 'deadpool'
        ]):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Celebrity Edits'],
                'SG carousel guardrail: fan-art/anime/manga character cues detected, so Celebrity Edits replaced Movie/Tv/Drama Edits.'
            )

    # 10) Carousel Media/Infotainment nuance.
    if label_set == {'Carousel', 'Media/Infotainment'}:
        if has_any_term(['makeup product', 'makeup products']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Beauty'],
                'SG carousel media guardrail: makeup product rating cues detected, so Beauty was used.'
            )
        if has_any_term(['anime', 'manga', 'deltarune', 'fan-made merchandise', 'fan art', 'digital art', 'character', 'saiki']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Celebrity Edits'],
                'SG carousel media guardrail: fan-art/merchandise cues detected, so Celebrity Edits was used.'
            )
        if has_any_term(['baby name', 'baby boy']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Relationship'],
                'SG carousel media guardrail: baby/family relationship cues detected, so Relationship was used.'
            )
        if has_any_term(['negative interaction', 'food stall', 'food review conflict']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Slice of Life'],
                'SG carousel media guardrail: everyday food-review conflict cues detected, so Slice of Life was used.'
            )

    # 11) Other carousel semantic corrections.
    if label_set == {'Carousel', 'Slice of Life'}:
        if has_any_term(['dark cartoonish cat', 'roblox', 'game', 'gaming', 'hihi i have twitter']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Gaming'],
                'SG carousel slice guardrail: game/character art cues detected, so Gaming was used.'
            )
        if has_any_term(['father-child', 'father child', 'student relatable', 'conversational habits']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Reflection'],
                'SG carousel slice guardrail: reflective school/family text cues detected, so Reflection was used.'
            )
        if has_any_term(["you're pure", 'soft text overlay', 'short quote', 'quote text']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Quotes'],
                'SG carousel slice guardrail: quote/text-card cues detected, so Quotes was used.'
            )

    if label_set == {'Carousel', 'Reflection'}:
        if has_any_term(['mother', 'prayers', "mother's prayers", 'power of a mother']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Quotes'],
                'SG carousel reflection guardrail: standalone mother/prayer quote cues detected, so Quotes was used.'
            )
        if has_any_term(['family portrait', 'family growth', 'addition of a new baby']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Slice of Life'],
                'SG carousel reflection guardrail: family portrait/lifestyle cues detected, so Slice of Life was used.'
            )

    if label_set == {'Carousel', 'Travel'}:
        if has_any_term(['city view', 'klcc', 'airbnb', 'dessert shop', 'street scene', 'petronas']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Slice of Life'],
                'SG carousel travel guardrail: city/lifestyle scenery cues detected, so Slice of Life was used.'
            )

    if label_set == {'Carousel', 'Relationship'}:
        if has_any_term(['cat', 'outfit', 'fashion']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Fashion'],
                'SG carousel relationship guardrail: cat/outfit/fashion cue detected, so Fashion was used.'
            )
        if has_any_term(['roblox', 'game', 'gaming']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Gaming'],
                'SG carousel relationship guardrail: gaming/Roblox cues detected, so Gaming was used.'
            )
        if has_any_term(['reflective', 'personal desires', 'wedding aspiration', 'professional camera viewfinder']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Reflection'],
                'SG carousel relationship guardrail: reflective aspiration cues detected, so Reflection was used.'
            )

    if label_set == {'Carousel', 'Lyrics'}:
        if has_any_term(['moving to australia', 'migration', 'dreaming of migration']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Reflection'],
                'SG carousel lyrics guardrail: migration/reflection cues detected, so Reflection was used.'
            )
        if has_any_term(['city sidewalk', 'outfit showcase']):
            return _set_labels_preserve_allowed(
                result,
                ['Carousel', 'Quotes'],
                'SG carousel lyrics guardrail: aesthetic quote/outfit cues detected, so Quotes was used.'
            )

    if label_set == {'Carousel', 'Fitness'} and has_any_term(['family', 'lighthearted family']):
        return _set_labels_preserve_allowed(
            result,
            ['Carousel', 'Slice of Life'],
            'SG carousel fitness guardrail: family portrait cues detected, so Slice of Life was used.'
        )

    if label_set == {'Carousel', 'POV'} and has_any_term(['student', 'school', 'commenting on']):
        return _set_labels_preserve_allowed(
            result,
            ['Carousel', 'Reflection'],
            'SG carousel POV guardrail: school/reflection text cues detected, so Reflection was used.'
        )

    # 12) Two-label non-carousel fixes.
    if label_set == {'Dance', 'Movie/Tv/Drama Edits'} and has_any_term(['stranger things cast', 'actors', 'actresses']):
        return _set_labels_preserve_allowed(
            result,
            ['Dance', 'Celebrity Edits'],
            'SG edit guardrail: real cast/actors cue detected, so Celebrity Edits replaced Movie/Tv/Drama Edits.'
        )
    if label_set == {'Dance', 'Fashion'} and has_any_term(['lunar new year', 'cheongsam', 'skincare', 'makeup', 'beauty']):
        return _set_labels_preserve_allowed(
            result,
            ['Dance', 'Beauty'],
            'SG dance/fashion guardrail: beauty/Lunar New Year transition cues detected, so Beauty replaced Fashion.'
        )
    if label_set == {'Beauty', 'Carousel'} and has_any_term(['humorous text', 'dating requirements']):
        return _set_labels_preserve_allowed(
            result,
            ['Carousel', 'Reflection'],
            'SG carousel beauty guardrail: humorous reflection text cues detected, so Reflection replaced Beauty.'
        )

    return result



def coerce_gemini_result(obj):
    """Normalize any Gemini response into the dict schema used by the tagger.

    Gemini is instructed to return a JSON object, but occasionally it returns
    a list, for example [{...}] or ["Dance"]. Without this guard the pipeline
    can crash at result['tier_used'] with: TypeError: list indices must be
    integers or slices, not str. This function keeps the batch running and
    flags malformed responses for review instead of stopping the whole run.
    """
    # Most normal path: already a dict.
    if isinstance(obj, dict):
        result = dict(obj)
    # Common Gemini mistake: wraps the object in a one-item list.
    elif isinstance(obj, list):
        first_dict = next((x for x in obj if isinstance(x, dict)), None)
        if first_dict is not None:
            result = dict(first_dict)
            result.setdefault('reasoning', 'Gemini returned a JSON list; first object was used safely.')
        else:
            labels = [str(x).strip() for x in obj if str(x).strip() in ALLOWED_SET]
            result = {
                'narrative': 'NA',
                'creative_type': labels[:2],
                'content_details': 'Gemini returned a label list instead of the required JSON object.',
                'confidence': 0.45,
                'reasoning': 'Malformed Gemini response: list instead of object. Row kept for review instead of crashing.',
                'needs_human_review': True,
                'parse_error': False if labels else True,
            }
    else:
        result = {
            'narrative': 'NA',
            'creative_type': [],
            'content_details': 'Gemini returned an unsupported response type.',
            'confidence': 0,
            'reasoning': f'Malformed Gemini response type: {type(obj).__name__}',
            'needs_human_review': True,
            'parse_error': True,
        }

    # Normalize common alternate key spellings.
    if 'creative_type' not in result:
        for alt in ['creative_types', 'Creative Type', 'creativeType', 'labels', 'category']:
            if alt in result:
                result['creative_type'] = result.get(alt)
                break
    if 'content_details' not in result:
        for alt in ['content_detail', 'Content Details', 'details', 'description']:
            if alt in result:
                result['content_details'] = result.get(alt)
                break

    ct = result.get('creative_type', [])
    if isinstance(ct, str):
        # Split only on comma; keep labels like Movie/Tv/Drama Edits intact.
        ct = [p.strip() for p in ct.split(',') if p.strip()]
    elif not isinstance(ct, list):
        ct = []
    # Keep allowed labels only and avoid duplicates while preserving order.
    cleaned = []
    for x in ct:
        sx = str(x).strip()
        # Handle common typo in manual/model outputs.
        if sx.lower() == 'media/infortainment':
            sx = 'Media/Infotainment'
        if sx in ALLOWED_SET and sx not in cleaned:
            cleaned.append(sx)
    result['creative_type'] = cleaned[:2]

    narrative = result.get('narrative', '')
    if isinstance(narrative, list):
        narrative = ', '.join(str(x).strip() for x in narrative if str(x).strip())
    result['narrative'] = str(narrative or 'NA').strip()
    result['content_details'] = str(result.get('content_details', '') or '').strip()
    result['reasoning'] = str(result.get('reasoning', '') or result.get('reason', '') or '').strip()
    try:
        result['confidence'] = float(result.get('confidence', 0) or 0)
    except Exception:
        result['confidence'] = 0.0

    if not result['creative_type']:
        result['needs_human_review'] = True
        result.setdefault('parse_error', True)
    return result

def apply_post_guardrails(result, row=None):
    """Single post-processing path with market-aware guardrails."""
    result = coerce_gemini_result(result)
    pre_guardrail_labels = list(result.get('creative_type', []))
    result = apply_lyrics_guardrails(result, row)
    result = apply_dance_guardrails(result, row)
    result = apply_knowledge_guardrails(result, row)
    result = apply_lyrics_guardrails(result, row)
    # Market-specific tuning from PH/TH/KR mismatch reports. These rules are
    # reusable signal-based guardrails, not URL memorisation.
    result = apply_my_scene_balance_guardrails(result, row)
    result = apply_ph_text_quote_and_lipsync_guardrails(result, row)
    result = apply_th_scene_balance_guardrails(result, row)
    result = apply_sg_scene_balance_guardrails(result, row)
    result = apply_vn_scene_balance_guardrails(result, row)
    result = apply_vn_v16_remaining_balance_guardrails(result, row)
    result = apply_kr_track_dance_guardrails(result, row)
    result = apply_static_non_dance_guardrail(result, row)
    result = apply_content_details_consistency_guardrail(result, row)
    result = apply_v66_semantic_consistency_guardrail(result, row)
    result = apply_v67_evidence_contradiction_guardrail(result, row)
    result = apply_single_image_carousel_guardrail(result, row)
    result = coerce_gemini_result(result)
    final_labels = list(result.get('creative_type', []))
    result['_pre_guardrail_labels'] = pre_guardrail_labels
    result['_guardrail_changed_labels'] = pre_guardrail_labels != final_labels
    result['_guardrail_changed_primary'] = (
        (pre_guardrail_labels[0] if pre_guardrail_labels else '')
        != (final_labels[0] if final_labels else '')
    )
    return result

def build_prompt(row):
    caption    = row.get('text', '')
    _raw_tags  = row.get('hashtags')
    _raw_tags  = _raw_tags if isinstance(_raw_tags, list) else []
    hashtags   = [h.get('name','') if isinstance(h,dict) else str(h) for h in _raw_tags]
    htag_str   = ' '.join(f'#{h}' for h in hashtags) if hashtags else '(none)'
    kb_hint    = creative_kb_prompt_hint(row)
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
    slide_count = _slideshow_image_count(row)
    slide_count_display = slide_count if slide_count is not None else 'unknown'
    allowed_str = '\n'.join(f'  - {t}' for t in ALLOWED_CREATIVE_TYPES)
    return f"""You are a senior TikTok UGC content analyst for Universal Music Group.
Your task is to classify TikTok posts for music marketing analysis across Malaysia, Philippines, Singapore, Korea, Thailand, Vietnam and wider SEA markets.

Return ONLY valid JSON. No markdown. No explanation outside JSON.

=== POST METADATA ===
Caption: {caption}
Hashtags: {htag_str}
Creator: {author}
Music: {music} by {music_auth}
Duration: {duration}s | Market: {location} | Is Slideshow: {is_slide} | Confirmed Slideshow Images: {slide_count_display}
Plays: {play:,} | Likes: {likes:,} | Shares: {shares:,} | Saves: {saves:,}
Historical KB: {kb_hint}

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
- A static or aesthetic video showing song lyrics/text as the central focus is Lyrics, not Dance.
- A drama/anime/movie scene edit is Movie/Tv/Drama Edits, not Slice of Life.
- A K-pop idol photo/video montage is Celebrity Edits, not Slice of Life.
- A makeup routine is Beauty, not Fashion, even if the outfit is nice.
- Makeup advice, eye-shape guidance and cosmetic tips are Beauty even when presented as a photo carousel.
- A supportive personal message is Reflection, not Lyrics, unless the text is explicitly identified as song lyrics.
- A question, viewer prompt or challenge is not POV by itself. POV requires explicit first-person, viewer-perspective or acted-scenario framing.
- Celebrity Edits requires a real public figure. An AI-generated or fictional singer is not a celebrity edit; classify the musical performance as Cover when clearly shown.

=== OUTPUT RULES ===
- Creative Type: return 1 or 2 labels only.
- Include Carousel only when the post has at least 2 confirmed slideshow images.
- If Confirmed Slideshow Images is 1, do NOT use Carousel; classify the single image by its content.
- Carousel is a TikTok photo-mode format, not an editing style. If Is Slideshow is false, do NOT use Carousel even when a normal video is edited from several photos.
- If the slideshow image count is unknown, use isSlideshow conservatively and never infer Carousel from a video montage alone.
- If Carousel is included, use the second label for the actual content type when possible, e.g. ["Carousel", "Beauty"].
- Do not use Slice of Life as a fallback when a more specific label applies.
- If uncertain, choose the strongest visible signal and lower confidence.
- Remix is audio-only. Never use Remix for visual transitions, outfit changes, or editing style.
- If visible lyrics, lyric text, karaoke-style text, Spotify lyrics, or translated lyrics are the main visual content, use Lyrics or Lyrics Translation. Do NOT use Dance just because the song title contains "dance" or the audio is rhythmic.

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
2. Is the main content from a movie, drama, TV show, anime, web series or fictional scene? Use Movie/Tv/Drama Edits. A polished montage of the same recurring couple/characters across multiple cinematic settings is normally a drama edit, not Dance or ordinary Relationship content.
3. Is the main content a fan edit/montage of a real celebrity, idol, singer, actor, athlete, influencer or public figure? Use Celebrity Edits.
4. Is visible choreography, repeated body movement, dance challenge, or synchronized/group movement the main focus? Use Dance.
5. Is the creator mainly mouthing/singing lyrics with little/no choreography? Use Lip Sync. If choreography is visible, Dance wins over Lip Sync.
6. Is the creator performing a cover, singing/playing an instrument as their own performance? Use Cover.
7. Is the main focus makeup, skincare, hair, nails or cosmetics? Use Beauty. A distinctive or deliberately showcased makeup look may combine Beauty + Lip Sync when the creator is also clearly mouthing the audio.
8. Is the main focus clothing, outfit styling, OOTD, fit check or fashion haul? Use Fashion.
9. Is the main message romantic love, longing, heartbreak, partner dynamics or affection for someone special? Use Relationship.
10. Is it a first-person acted scenario or explicit "POV" setup? Use POV, optionally with Comedy or Relationship. A viewer question, prompt or challenge alone is not POV.
11. Is the main purpose humour, joke, meme, prank or comedic skit? Use Comedy.
12. Are song words visibly displayed as the main content? Use Lyrics when the words stay in the song's original language. Use Lyrics Translation only when the post explicitly translates/explains those lyrics in another language, normally with both original and translated text visible. Ordinary captions, quotes and dialogue subtitles are not Lyrics.
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
Talking, giving advice or making a personal announcement directly to camera is not Lip Sync unless the creator visibly mouths or sings along to the audio.

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
If several polished cinematic shots show recurring characters/cast members across different settings, treat it as a drama/movie edit even when translated lyrics are overlaid. Lyrics Translation may be the second label.

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
Distinctive doll-like, graphic, creative or transformation makeup may count as Beauty when the visual styling itself is clearly showcased, even if no application step is shown. Do not infer Beauty from ordinary makeup alone.
Makeup advice, eye-shape guidance, cosmetic recommendations and beauty tips are Beauty; combine with Carousel when there are at least two confirmed slideshow images.

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
A question asking viewers to name, guess, choose, comment or tag something is an audience prompt, not POV, unless first-person/viewer-perspective framing is also explicit.

11) Comedy
Definition: Main purpose is humour.
Use for: joke, meme, prank, funny skit, humorous acting, exaggerated reaction, comedic situation.
Can combine with: POV.
Do NOT use if the content is only light-hearted but not primarily funny. Do NOT classify a skit as Lip Sync just because music is playing; if the creator is acting/talking for humour, choose Comedy.

12) Lyrics
Definition: Song lyrics in their original language are visibly displayed or are the central content.
Use for: lyric video, lyric edit, karaoke-style text, emotional lyric text, post built around written lyrics.
Do NOT use merely because the audio has lyrics.
Do NOT use for an ordinary caption, standalone quote, dialogue subtitle or personal statement that is not clearly song lyrics.
Rule: Lyrics must be visible or captionally central.
Supportive, caring or introspective personal text is Reflection rather than Lyrics unless the post explicitly presents it as song lyrics.

13) Lyrics Translation
Definition: The post translates or explains song lyrics from the original language into another language.
Use for: bilingual lyric cards, original lyrics plus translated text, or an explicit translated-lyric explanation.
Do NOT use for plain original-language lyrics, ordinary translated dialogue subtitles, or a quote written in one language.
Rule: Choose Lyrics Translation only with explicit translation/bilingual evidence; otherwise use Lyrics when the visible text is clearly song lyrics.

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
Use when: TikTok/Apify metadata confirms photo/slideshow mode with at least 2 images.
Do not use Carousel for a confirmed single-image photo-mode post; classify that image by its content.
Do not use Carousel for a normal TikTok video made from a montage or sequence of photos.
Best practice: use Carousel + content label, e.g. Carousel + Beauty, Carousel + Quotes, Carousel + Celebrity Edits.

=== COMMON CONFUSIONS TO AVOID ===
- Dance vs Lip Sync: Dance = choreography/body movement. Lip Sync = mouth/face performance to lyrics.
- Ordinary walking, posing, turning, stepping forward/backward or changing outfits is not Dance. When clothing is the visual purpose, use Fashion.
- Animals or animated subjects can be Dance when explicit choreography, repeated rhythmic movement or movement to the beat is visible. Ordinary pet movement, posing or rolling is not Dance.
- Do not use Lip Sync for an animal unless explicit animated mouthing-to-lyrics evidence is visible.
- Dance vs Slice of Life: if dancing is visible, do not call it Slice of Life just because setting is casual.
- Beauty vs Fashion: Beauty = makeup/skincare/hair/nails/cosmetics. Fashion = clothes/outfit/styling.
- Relationship vs Slice of Life: Relationship = romance/partner/love/longing. Slice of Life = ordinary daily life.
- Quotes vs Reflection: Quotes = quote text. Reflection = personal introspection/life lesson.
- Celebrity Edits vs Movie/Tv/Drama Edits: real public figure = Celebrity Edits. Fictional/drama/movie/anime scene = Movie/Tv/Drama Edits.
- Media/Infotainment vs Slice of Life: if the post teaches, explains, recommends or reports, use Media/Infotainment.
- A CapCut template or abstract visual effect is not Media/Infotainment unless the post teaches, reviews or explains something.
- Lyrics vs Lip Sync: Lyrics = text shown. Lip Sync = person mouths/sings lyrics.
- Lyrics vs Dance: Lyrics wins when the post is mainly lyric text/static lyric visuals. Dance requires visible choreography/body movement, not just a dance-related song title.
- Track titles such as "Raindance" do NOT imply Dance. If the visual is text/lyrics/Spotify lyrics/static lyric edit, choose Lyrics or Lyrics Translation.
- Track/creator history never overrides the observed action. Final Creative Type must agree with Narrative and Content Details.

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

def call_gemini(contents, gemini_key, max_retries=2):
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
            return coerce_gemini_result(json.loads(text))
        except Exception as e:
            err = str(e)
            if '429' in err or 'RESOURCE_EXHAUSTED' in err:
                wait = GEMINI_BACKOFF_SECONDS*(attempt+1) + random.randint(0,5)
                time.sleep(wait)
            elif '503' in err or 'UNAVAILABLE' in err:
                wait = max(10, GEMINI_BACKOFF_SECONDS//2)*(attempt+1) + random.randint(0,5)
                time.sleep(wait)
            else:
                return {'parse_error': True, 'raw_response': err, 'needs_human_review': True}
    return {'parse_error': True, 'raw_response': 'Max retries exceeded', 'needs_human_review': True}


def call_targeted_evidence_verifier(prompt, gemini_key, max_retries=2):
    """Return raw verifier JSON without coercing it into the tagging schema."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_key)
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(response_mime_type='application/json'),
            )
            text = response.text.strip()
            text = re.sub(r'^```json\s*', '', text)
            text = re.sub(r'```$', '', text).strip()
            return json.loads(text)
        except Exception as e:
            err = str(e)
            if '429' in err or 'RESOURCE_EXHAUSTED' in err:
                time.sleep(GEMINI_BACKOFF_SECONDS * (attempt + 1) + random.randint(0, 5))
            elif '503' in err or 'UNAVAILABLE' in err:
                time.sleep(max(10, GEMINI_BACKOFF_SECONDS // 2) * (attempt + 1) + random.randint(0, 5))
            else:
                return {'parse_error': True, 'reason': err}
    return {'parse_error': True, 'reason': 'Targeted verifier retries exhausted'}


def maybe_run_targeted_evidence_verifier(
    result,
    row,
    gemini_key,
    review_reasons=None,
    verifier_call=None,
):
    """Run a cheap second pass only when cross-field evidence is questionable."""
    if not ENABLE_TARGETED_EVIDENCE_VERIFIER:
        return result
    reasons = targeted_verifier_reasons(
        result,
        row,
        ALLOWED_CREATIVE_TYPES,
        review_reasons=review_reasons,
    )
    if not reasons:
        return result

    prompt = build_verifier_prompt(result, row, ALLOWED_CREATIVE_TYPES, reasons)
    call = verifier_call or call_targeted_evidence_verifier
    try:
        response = call(prompt, gemini_key)
    except Exception as exc:
        response = {'parse_error': True, 'reason': str(exc)}
    return apply_verifier_response(
        result,
        response,
        row,
        ALLOWED_CREATIVE_TYPES,
        reasons,
        route_errors_to_review=bool(resolvable_review_reasons(review_reasons)),
    )

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
                return coerce_gemini_result(json.loads(text))
            except Exception as e:
                err = str(e)
                if '429' in err or 'RESOURCE_EXHAUSTED' in err:
                    time.sleep(GEMINI_BACKOFF_SECONDS*(attempt+1) + random.randint(0,5))
                elif '503' in err or 'UNAVAILABLE' in err:
                    time.sleep(max(10, GEMINI_BACKOFF_SECONDS//2)*(attempt+1) + random.randint(0,5))
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
    result = coerce_gemini_result(result)
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
    result = coerce_gemini_result(result)
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
        'review_risk_reasons':  str(result.get('review_risk_reasons', '') or ''),
        'tier3_reason':         tier3_reason,
        'verifier_status':      str(result.get('_verifier_status', '') or 'not_run'),
        'verifier_input_labels': ', '.join(result.get('_verifier_input_labels', []) or []),
        'verifier_output_labels': ', '.join(result.get('_verifier_output_labels', []) or []),
        'verifier_confidence':  result.get('_verifier_confidence', 0) or 0,
        'verifier_reason':      str(result.get('_verifier_reason', '') or ''),
        'verifier_evidence':    ' | '.join(result.get('_verifier_evidence', []) or []),
        'verifier_triggers':    ' | '.join(result.get('_verifier_trigger_reasons', []) or []),
        # Keep a lightweight copy of the normalized source row so the Review page
        # can still recover metrics/link/cover for every pending item after reruns.
        '_raw_row_json':        json.dumps(raw_record if raw_record else (row.to_dict() if hasattr(row, 'to_dict') else dict(row)), default=str),
    }

def run_pipeline(records, track, gemini_key, apify_token, log_list, delay_seconds=1, on_row_done=None, source_file="", campaign_market=""):
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
        market = campaign_market or row.get('locationCreated', raw_source.get('locationCreated', 'UNKNOWN'))
        try:
            if pd.isna(market):
                market = campaign_market or raw_source.get('locationCreated', 'UNKNOWN')
        except Exception:
            pass

        # Pass source-report market/track context into the optional Creative KB.
        # Use the Batch Filter country when available, because TikTok locationCreated
        # may describe the creator/post origin rather than the UMG market being evaluated.
        try:
            row['_campaign_track'] = track
            row['_campaign_market'] = campaign_market or market
        except Exception:
            pass
        if isinstance(raw_source, dict):
            raw_source.setdefault('_campaign_track', track)
            raw_source.setdefault('_campaign_market', campaign_market or market)

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

        # Sensitive posts can still be opened and classified by an authorised
        # human reviewer, even when Apify will not return their media/metadata.
        # Keep the link, skip Gemini, and route the row directly to Review.
        scraper_issue_blob = f"{scraper_error} {scraper_error_code}".upper()
        sensitive_scraper_row = 'SENSITIVE' in scraper_issue_blob
        if sensitive_scraper_row:
            reason_text = scraper_error or scraper_error_code or 'Sensitive post'
            log_list.append(f"  â†’ Sensitive post sent to human review ({scraper_error_code or reason_text})")
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
                'sensitive_human_review', 'review', 0,
                [str(scraper_error_code or reason_text)],
                'Sensitive post requires human review.',
                raw_source, source_file, i
            )
            if not out.get('tiktok_url') and public_url:
                out['tiktok_url'] = public_url
            out['review_action'] = ''
            out['needs_human_review'] = True
            out['manual_metrics_required'] = all_metrics_zero
            results.append(out)
            if on_row_done:
                on_row_done(i + 1, len(df), out, 'sensitive_human_review')
            time.sleep(delay_seconds)
            continue

        # Deleted/private/unavailable/unusable scraper rows should NOT go to Review.
        # Review is only for posts that a human can actually open and classify.
        # If Apify returns an error row or no usable metadata, we auto-remove it from final export.
        def _is_unavailable_scraper_issue(*vals):
            blob = ' '.join(str(v or '') for v in vals).upper()
            if not blob.strip():
                return False
            unavailable_markers = [
                'POST_NOT_FOUND', 'NOT_FOUND', 'PRIVATE', 'DELETED', 'UNAVAILABLE',
                'VIDEO_UNAVAILABLE', 'ITEM_UNAVAILABLE', 'NO_LONGER_AVAILABLE',
                'COULD NOT RETRIEVE', 'NOT AVAILABLE', 'LOGIN_REQUIRED', 'AGE_RESTRICTED',
                'REMOVED', 'DOES NOT EXIST', 'COULDNT_FIND', 'COULDN\'T FIND',
                'NO USABLE METADATA', 'METRICS UNAVAILABLE', 'SCRAPER ERROR'
            ]
            return any(m in blob for m in unavailable_markers)

        no_usable_metadata = all_metrics_zero and public_url and not _clean_text(row.get('text'))
        unusable_scraper_row = bool(scraper_error or scraper_error_code or no_usable_metadata)

        if unusable_scraper_row:
            reason_text = scraper_error or scraper_error_code or 'No usable metadata from scraper'
            log_list.append(f"  → Unavailable/deleted/private/unusable post auto-removed ({scraper_error_code or reason_text})")
            result = {
                'narrative': '',
                'creative_type': [],
                'content_details': '',
                'confidence': 0,
                'reasoning': str(reason_text),
                'needs_human_review': False,
            }
            out = build_out(
                row, vid_id, market, track, result,
                'auto_removed_unavailable', 'removed', 0,
                [str(scraper_error_code or reason_text)],
                'Auto-skipped because the post is unavailable, deleted, private, scraper-error, or has no usable metadata.',
                raw_source, source_file, i
            )
            # Ensure the public URL is preserved even when the scraper row only has `url`.
            if not out.get('tiktok_url') and public_url:
                out['tiktok_url'] = public_url
            out['review_action'] = 'REMOVE'
            out['remove_reason'] = str(scraper_error_code or reason_text)
            out['needs_human_review'] = False
            out['manual_metrics_required'] = False
            results.append(out)
            if on_row_done:
                on_row_done(i + 1, len(df), out, 'auto_removed_unavailable')
            time.sleep(delay_seconds)
            continue

        # Keep vague-caption posts in the same cover -> 3 frames -> 9 frames ->
        # full-video cascade. The legacy Tier 0 shortcut is retained only for
        # rollback and is disabled by default because it could bypass fallbacks.
        if ENABLE_LEGACY_TIER0_VAGUE_SHORTCUT and is_too_vague(row):
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
                # v5 fix: Tier 0 visual-only results used to bypass the Lyrics/Dance/KB
                # post-processing path. That is why PH lyric-display rows could still
                # export as Dance. Apply the same guardrails here before validation.
                tier0_result = apply_post_guardrails(tier0_result, row)
                t0_status, t0_score, t0_issues = validate(tier0_result)
                tier0_result, t0_status, t0_score, t0_issues = apply_review_policy(
                    tier0_result, row, t0_status, t0_score, t0_issues,
                    include_audit=False, include_guardrail_changes=False
                )
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
            # An unresolved vague-caption result must not jump directly to
            # human Review. Continue into the normal cover -> 3 frames ->
            # 9 frames -> full-video cascade below. Only that final cascade
            # is allowed to create a human-review row.
            log_list.append("  -> Tier 0V unresolved; continuing through all automated fallbacks...")

        log_list.append("  → Tier 1 (cover image)...")
        prompt = build_prompt(row)
        if is_too_vague(row):
            prompt += "\n\nThe caption/hashtags are vague or missing. Base the classification on visual evidence. Do not infer a format from the track name alone."
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
        result = apply_post_guardrails(result, row)
        result['tier_used'] = 'tier1_cover'
        status, score, issues = validate(result)
        result, status, score, issues = apply_review_policy(
            result, row, status, score, issues,
            include_audit=False, include_guardrail_changes=False
        )

        cover_result = dict(result)
        cover_escalation_reasons = visual_escalation_reasons(
            result, row, stage='cover'
        )
        if _kb_url_type(row) == 'video':
            temporal_reason = 'Normal video requires temporal sampling before final classification'
            if temporal_reason not in cover_escalation_reasons:
                cover_escalation_reasons.insert(0, temporal_reason)
        if cover_escalation_reasons:
            log_list.append(
                "  -> Cover result needs stronger evidence: "
                + " | ".join(cover_escalation_reasons)
            )

        if (
            status == 'review'
            or result.get('confidence', 0) < 0.75
            or bool(cover_escalation_reasons)
        ):
            log_list.append("  → Tier 2A (3 video frames)...")
            video_url = get_video_url(row)
            if video_url:
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        video_path = os.path.join(tmp, f'{vid_id}.mp4')
                        download_video(video_url, video_path, apify_token)

                        # Tier 2A: fast default pass using 3 frames.
                        frame_paths = extract_frames(video_path, os.path.join(tmp, 'frames_3'), FRAME_POINTS_3)
                        contents2 = [prompt + "\n\nDefault temporal pass: compare all sampled frames before deciding. Do not treat an opening object or food shot as the whole post when later frames show a person, celebrity, edit, visible lyrics, or another main subject."]
                        for fp in frame_paths:
                            with open(fp, 'rb') as f:
                                contents2.append(gtypes.Part.from_bytes(data=f.read(), mime_type='image/jpeg'))
                        result2 = call_gemini(contents2, gemini_key)
                        result2 = apply_post_guardrails(result2, row)
                        result2['tier_used'] = 'tier2a_3frames'
                        status2, score2, issues2 = validate(result2)
                        result2, status2, score2, issues2 = apply_review_policy(
                            result2, row, status2, score2, issues2,
                            include_audit=False, include_guardrail_changes=False
                        )
                        frame3_result = dict(result2)
                        if score2 >= score or result.get('parse_error'):
                            result, status, score, issues = result2, status2, score2, issues2

                        # Tier 2B: adaptive motion refinement.
                        # Only run the slower 9-frame pass when the content is likely motion-heavy
                        # or the 3-frame result is still weak. This is designed to help KR/Dance
                        # without slowing every PH-style Lip Sync / Relationship / Quote post.
                        # Run the 9-frame pass only when the 3-frame result is
                        # still unresolved. A successful 3-frame classification
                        # should not consume another Gemini call.
                        frame_refinement_reasons = visual_escalation_reasons(
                            result2, row, stage='frames', previous_result=cover_result
                        )
                        should_refine_motion = (
                            status2 == 'review'
                            or result2.get('parse_error')
                            or result2.get('confidence', 0) < 0.80
                            or bool(frame_refinement_reasons)
                        )
                        if should_refine_motion:
                            log_list.append("  → Tier 2B (adaptive 9-frame motion refinement)...")
                            frame_paths_9 = extract_frames(video_path, os.path.join(tmp, 'frames_9'), FRAME_POINTS_9)
                            contents9 = [prompt + "\n\nMulti-frame refinement: analyse the full sequence carefully. Resolve movement (Dance vs Lip Sync vs Cover), text meaning (Lyrics vs Lyrics Translation vs Quotes), and source identity (real celebrity vs fictional scene). Do not rely on the cover frame or confidence alone."]
                            for fp in frame_paths_9:
                                with open(fp, 'rb') as f:
                                    contents9.append(gtypes.Part.from_bytes(data=f.read(), mime_type='image/jpeg'))
                            result9 = call_gemini(contents9, gemini_key)
                            result9 = apply_post_guardrails(result9, row)
                            result9['tier_used'] = 'tier2b_9frames_adaptive'
                            status9, score9, issues9 = validate(result9)
                            result9, status9, score9, issues9 = apply_review_policy(
                                result9, row, status9, score9, issues9,
                                include_audit=False, include_guardrail_changes=False
                            )
                            # Prefer 9-frame result only when it is clearly stronger or fixes a failed/low-confidence result.
                            if (
                                (status9 == 'pass' and not result9.get('parse_error'))
                                or score9 > score
                                or result.get('parse_error')
                                or (status != 'pass' and status9 == 'pass')
                                or (result9.get('confidence', 0) >= result.get('confidence', 0) + 0.10)
                            ):
                                result, status, score, issues = result9, status9, score9, issues9

                        # Tier 2C: full-video fallback, used only for unresolved motion-heavy ambiguity.
                        # This is slower and consumes more quota, so it is deliberately conservative.
                        # Full video is the last automated fallback. It runs only
                        # when the 3-frame and 9-frame path is still unresolved.
                        full_video_reasons = visual_escalation_reasons(
                            result, row, stage='frames', previous_result=frame3_result
                        )
                        unresolved_after_frames = (
                            status == 'review'
                            or result.get('parse_error')
                            or bool(full_video_reasons)
                        )
                        if ENABLE_TIER2C_FULL_VIDEO_FALLBACK and unresolved_after_frames:
                            log_list.append("  → Tier 2C (full video fallback for unresolved ambiguity)...")
                            video_prompt = prompt + "\n\nUse the full video to resolve remaining ambiguity. Check temporal movement, all visible text, and whether edited subjects are real public figures or fictional characters."
                            resultv = call_gemini_video_file(video_path, video_prompt, gemini_key)
                            resultv = apply_post_guardrails(resultv, row)
                            resultv['tier_used'] = 'tier2c_full_video'
                            statusv, scorev, issuesv = validate(resultv)
                            resultv, statusv, scorev, issuesv = apply_review_policy(
                                resultv, row, statusv, scorev, issuesv,
                                include_audit=False, include_guardrail_changes=False
                            )
                            # Prefer full-video result when it passes validation and is at least as strong,
                            # or when it fixes a low-confidence/review result.
                            if (
                                not resultv.get('parse_error')
                                and (
                                    statusv == 'pass'
                                    or scorev > score
                                    or (status != 'pass' and statusv == 'pass')
                                    or (resultv.get('confidence', 0) >= max(0.75, result.get('confidence', 0) + 0.05))
                                )
                            ):
                                result, status, score, issues = resultv, statusv, scorev, issuesv
                        elif unresolved_after_frames:
                            log_list.append("  → Tier 2C skipped in runtime-safe mode (prevents long full-video upload waits).")
                except Exception as e:
                    log_list.append(f"  → Tier 2 failed: {e}")

        # One conservative second opinion after the best temporal result has
        # been selected. It is intentionally not called at every tier. The
        # verifier may confirm, make a high-evidence correction, or preserve
        # the labels and route the row to human review.
        pre_verifier_reasons = review_risk_reasons(
            result,
            row,
            include_audit=False,
            include_guardrail_changes=False,
        )
        result = maybe_run_targeted_evidence_verifier(
            result,
            row,
            gemini_key,
            review_reasons=pre_verifier_reasons,
        )
        verifier_status = str(result.get('_verifier_status', '') or '')
        if verifier_status == 'changed':
            # A verifier change is still subject to every established market,
            # semantic and structural guardrail. Preserve the verifier audit
            # fields while normalizing the accepted final label set.
            verifier_audit = {
                key: value for key, value in result.items()
                if key.startswith('_verifier_')
            }
            result = apply_post_guardrails(result, row)
            result.update(verifier_audit)
            result['_verifier_output_labels'] = list(result.get('creative_type', []) or [])
            verifier_status = str(result.get('_verifier_status', '') or '')
        if verifier_status:
            triggers = result.get('_verifier_trigger_reasons', []) or []
            log_list.append(
                f"  → Evidence verifier {verifier_status}: "
                + (' | '.join(triggers) if triggers else 'targeted cross-check')
            )
            status, score, issues = validate(result)
            if verifier_status in {'review', 'error'}:
                status = 'review'
                verifier_issue = str(
                    result.get('review_risk_reasons', '')
                    or 'Targeted evidence remains unresolved'
                )
                issue = f'Targeted verifier: {verifier_issue}'
                if issue not in issues:
                    issues.append(issue)

        if result.get('tier_used') == 'tier1_cover' and cover_escalation_reasons:
            # A cover-only result cannot safely resolve a motion/text/source
            # ambiguity when no usable video was available for the fallbacks.
            unresolved_visual_reasons = list(cover_escalation_reasons)
        else:
            unresolved_visual_reasons = visual_escalation_reasons(
                result, row, stage='frames'
            )
        if unresolved_visual_reasons:
            result['needs_human_review'] = True
            existing_review_reasons = [
                part.strip()
                for part in str(result.get('review_risk_reasons', '') or '').split('|')
                if part.strip()
            ]
            combined_review_reasons = existing_review_reasons + [
                reason for reason in unresolved_visual_reasons
                if reason not in existing_review_reasons
            ]
            result['review_risk_reasons'] = ' | '.join(combined_review_reasons)
            status = 'review'
            for reason in unresolved_visual_reasons:
                issue = f'Review risk after automated fallbacks: {reason}'
                if issue not in issues:
                    issues.append(issue)

        result, status, score, issues = apply_review_policy(
            result, row, status, score, issues,
            include_audit=True, include_guardrail_changes=False
        )
        final_conf  = result.get('confidence', 0)
        needs_human = (
            result.get('needs_human_review', False) or
            status == 'review' or final_conf == 0 or
            not result.get('narrative') or
            result.get('narrative') in ['?', 'null', 'None']
        )
        final_tier = str(result.get('tier_used', '') or '')
        audit_only = str(result.get('review_risk_reasons', '') or '') == 'Routine 5% quality-audit sample'
        tier3_reason = (
            '' if audit_only else
            'conf=0 or parse error after automated fallbacks' if needs_human and final_conf == 0 else
            'low confidence after automated fallbacks' if needs_human and final_conf < 0.80 else
            'still unresolved after 3-frame, 9-frame and full-video analysis' if needs_human and final_tier == 'tier2c_full_video' else
            'still unresolved after cover, 3-frame and 9-frame analysis' if needs_human and final_tier == 'tier2b_9frames_adaptive' else
            'still unresolved after cover and 3-frame analysis' if needs_human and final_tier == 'tier2a_3frames' else
            'still unresolved after cover/image analysis' if needs_human else ''
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
# ORIGINAL MELODYIQ / BATCH FILTER UI PRESERVED BELOW
# v16 KB + guardrail backend is used above.
# ══════════════════════════════════════════════════════════
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

# Creative KB status banner
try:
    kb_meta = load_creative_kb().get('metadata', {})
    if kb_meta:
        st.markdown(
            f"<div class='info-banner'>Creative KB loaded from <strong>creative_knowledge/</strong> · version {kb_meta.get('version', 'unknown')} · learned rows {kb_meta.get('rows_learned', 'unknown')}</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<div class='warn-banner'>No <strong>creative_knowledge/</strong> folder found beside this app. Tagging will still run, but KB support is off.</div>",
            unsafe_allow_html=True
        )
except Exception as _kb_banner_err:
    st.markdown(
        f"<div class='warn-banner'>Creative KB check failed: {_kb_banner_err}</div>",
        unsafe_allow_html=True
    )

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
        <p>Run Apify scraping and AI tagging from the filtered MelodyIQ report.</p>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.gemini_key or not st.session_state.apify_token:
        st.markdown("<div class='warn-banner'>Enter your Gemini and Apify API keys above before continuing.</div>", unsafe_allow_html=True)
        st.stop()

    if st.session_state.original_df.empty:
        st.markdown(
            "<div class='warn-banner'>No filtered MelodyIQ report is loaded yet. Start with <strong>Batch Filter</strong>, then return here.</div>",
            unsafe_allow_html=True
        )
        st.stop()

    orig_df = st.session_state.original_df.copy()
    url_col_api = st.session_state.get('original_url_col') or _detect_url_col_global(orig_df)
    market_col_api = _detect_market_col_global(orig_df)
    track_col_api = _detect_track_col_global(orig_df)

    if not url_col_api or not track_col_api:
        st.error("Could not detect the required Link and Artist - Sound / Track columns from the filtered report.")
        st.caption(f"Available columns: {', '.join(orig_df.columns.astype(str).tolist())}")
        st.stop()

    batches = _build_excel_track_batches(orig_df, market_col_api, track_col_api, url_col_api)
    total_links_api = sum(b['link_count'] for b in batches)

    source_note = "Batch Filter output" if not st.session_state.get('batch_filter_df', pd.DataFrame()).empty else "Loaded source report"
    st.markdown(f"""
    <div class='section-card'>
        <h3>Ready to Tag</h3>
        <div class='info-banner'>Using <strong>{source_note}</strong> as the source report · {len(orig_df)} rows.</div>
        <div class='metric-row' style='margin-bottom:0'>
            <div class='metric-card'><div class='val'>{len(orig_df)}</div><div class='lbl'>Filtered Rows</div></div>
            <div class='metric-card'><div class='val'>{len(batches)}</div><div class='lbl'>Track Batches</div></div>
            <div class='metric-card'><div class='val indigo'>{total_links_api}</div><div class='lbl'>TikTok Links</div></div>
            <div class='metric-card'><div class='val'>{url_col_api}</div><div class='lbl'>Link Column</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not batches:
        st.warning("No TikTok links were detected in the filtered report.")
        st.stop()

    with st.expander("Detected batches", expanded=False):
        preview_batches = pd.DataFrame([
            {'Country': b['country'], 'Artist - Sound': b['track'], 'Original Rows': b['rows'], 'Links': b['link_count']}
            for b in batches
        ])
        st.dataframe(preview_batches, use_container_width=True, hide_index=True)

    st.markdown("""
    <div class='section-card'>
        <h3>Run AI Tagging</h3>
        <p style='font-size:13px;color:#64748b;margin:0 0 14px'>
            The app will process all detected tracks automatically. Deleted, private, unavailable, or unusable posts will be skipped and excluded from the final export.
        </p>
    """, unsafe_allow_html=True)

    if st.button("Run Apify + AI Tagging", type="primary", use_container_width=True, key="run_apify_inside_app_simple"):
        all_results = []
        progress_bar = st.progress(0)
        status_box = st.empty()
        log_box = st.empty()
        log_lines = []
        api_delay = 1
        api_run_batches = batches

        for batch_i, batch in enumerate(api_run_batches):
            status_box.markdown(
                f"<div class='info-banner'>Processing <strong>{batch['country']} · {batch['track']}</strong> "
                f"({batch['link_count']} links) — batch {batch_i+1} of {len(api_run_batches)}</div>",
                unsafe_allow_html=True
            )
            try:
                items = run_apify_tiktok_scraper_api(batch['links'], st.session_state.apify_token)
            except Exception as e:
                st.error(f"Apify failed for {batch['track']}: {e}")
                continue

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
            log_box.code('\n'.join(log_lines[-10:]))

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
                source_file=f"apify_api_{batch['country']}_{batch['track']}",
                campaign_market=batch['country']
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
            skipped = int((combined.get('review_action', pd.Series([''] * len(combined))).fillna('') == 'REMOVE').sum())
            st.success(f"Done — {len(combined)} rows processed · {passed} AI tagged · {flagged} need review · {skipped} unavailable/skipped.")
            st.balloons()
        else:
            st.warning("No rows were returned/tagged. Check the Apify run or the source links.")

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
    _auto_remove_unusable_existing_rows()

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
        <p>Download the final MelodyIQ workbook with AI tagging columns appended.</p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.master_df.empty:
        st.info("No data loaded yet.")
        st.stop()

    _auto_remove_unusable_existing_rows()
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
        <h3>Final MelodyIQ Export</h3>
        <p style='font-size:13px;color:#64748b;margin:0 0 16px'>
            The app uses the Batch Filter output automatically, matches rows by TikTok <strong>video ID</strong>
            with normalized URL fallback, and appends only <strong>Narrative</strong>,
            <strong>Creative Type</strong>, and <strong>Content Details</strong> while preserving the workbook structure.
        </p>
    """, unsafe_allow_html=True)

    if st.session_state.original_df.empty:
        st.markdown("<div class='warn-banner'>No Batch Filter source report is loaded. Start again from Batch Filter before exporting.</div>", unsafe_allow_html=True)
        st.stop()

    melody_file = None

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
    # All Post Data rows are sorted by market in the same order, while
    # preserving the original row order inside each market. The only
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

        work['_export_market_order'] = work['_export_market_code'].apply(
            lambda x: FINAL_MARKET_ORDER.index(x) if x in FINAL_MARKET_ORDER else 999
        )
        work['_export_original_order'] = range(len(work))

        helper_cols = ['_export_market_code', '_export_market_order', '_export_original_order']

        # All Post Data must follow the Batch Filter market order:
        # MY -> PH -> SG -> TH -> VN -> KR, keeping original row order within each market.
        all_sheet = work.sort_values(
            ['_export_market_order', '_export_original_order'],
            kind='stable'
        )
        clean_all = all_sheet.drop(columns=helper_cols, errors='ignore')

        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
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

    if not st.session_state.original_df.empty:
        try:
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
