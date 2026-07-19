"""Automatic drama enrichment for the general UGC tagging pipeline.

The broad Creative Type classifier always runs first.  This module is called
only when the final broad label contains ``Movie/Tv/Drama Edits`` (including a
label selected by a human reviewer).  It does not create a separate UI mode and
does not change broad labels.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
from collections import OrderedDict
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

DRAMA_LABEL = "Movie/Tv/Drama Edits"

DRAMA_EXPORT_COLUMNS = [
    "Drama Content Category",
    "Drama Type",
    "Drama Edit Focus",
    "Drama Format",
    "Drama Country/Region",
    "Drama Title",
    "Detected Audio",
    "Audio Version",
    "Drama Evidence",
    "Drama Review Reason",
]

CONTENT_KINDS = (
    "Drama Edit",
    "CP Edit",
    "Entertainment News",
    "Anime Edit",
    "Actor/Actress Carousel",
    "Drama Carousel",
    "Behind-the-Scenes Edit",
    "K-pop Show Cut",
    "Actor/Actress Daily Vlog",
    "POV",
    "Other",
)
DRAMA_TYPES = ("General Drama", "BL Drama", "GL Drama", "Unknown")
EDIT_FOCUS = (
    "Fictional Story",
    "BL CP Edit",
    "GL CP Edit",
    "Cast/Actor Edit",
    "Character Edit",
    "General Drama Edit",
    "Unknown",
)
DRAMA_FORMAT_CHOICES = (
    "Long-form Drama",
    "Short-form Drama",
)
DRAMA_FORMAT_ALIASES = {
    "long": "Long-form Drama",
    "long form": "Long-form Drama",
    "long-form drama": "Long-form Drama",
    "short": "Short-form Drama",
    "short drama": "Short-form Drama",
    "short-form drama": "Short-form Drama",
    "short form drama": "Short-form Drama",
    # Preserve compatibility with saved review state and older exports while
    # presenting one consistent user-facing term.
    "micro": "Short-form Drama",
    "micro drama": "Short-form Drama",
    "micro-drama": "Short-form Drama",
    "n/a": "Not applicable",
    "na": "Not applicable",
}

# Reviewed production-format knowledge. Keep this list title-level and reusable;
# never add individual TikTok URLs. ``Still Love`` is distributed as a short-form
# drama even when a post omits #shortdrama or the model proposes Long-form.
KNOWN_SHORT_FORM_DRAMA_TITLES = {
    "still love",
}
FORMATS = (
    *DRAMA_FORMAT_CHOICES,
    "Unknown",
    "Not applicable",
)
REGIONS = (
    "Thailand", "China", "Taiwan", "Hong Kong", "Korea", "Japan",
    "Malaysia", "Indonesia", "Philippines", "Singapore", "Vietnam",
    "United States", "United Kingdom", "Other", "Unknown",
)
AUDIO_MATCHES = ("Matched", "Not Matched", "Unknown")
AUDIO_VERSIONS = (
    "Original",
    "Sped Up",
    "Slowed",
    "Remix",
    "Unknown",
)

DRAMA_REVIEW_OPTIONS = {
    "content_categories": CONTENT_KINDS,
    "drama_type": DRAMA_TYPES,
    "edit_focus": EDIT_FOCUS,
    "drama_format": DRAMA_FORMAT_CHOICES,
    "country_region": REGIONS,
    "audio_version": AUDIO_VERSIONS,
}


def _content_categories(value) -> List[str]:
    """Return at most two validated detail categories in stable order."""
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = re.split(r"\s*[,|]\s*", _text(value))
    aliases = {
        "drama": "Drama Edit",
        "drama edits": "Drama Edit",
        "cp edits": "CP Edit",
        "entertainment": "Entertainment News",
        "anime": "Anime Edit",
        "anime edits": "Anime Edit",
        "actor carousel": "Actor/Actress Carousel",
        "actress carousel": "Actor/Actress Carousel",
        "behind the scene edits": "Behind-the-Scenes Edit",
        "behind-the-scenes": "Behind-the-Scenes Edit",
        "kpop show cut": "K-pop Show Cut",
        "actor daily vlog": "Actor/Actress Daily Vlog",
        "actress daily vlog": "Actor/Actress Daily Vlog",
    }
    cleaned: List[str] = []
    for item in items:
        text = _text(item)
        category = text if text in CONTENT_KINDS else aliases.get(text.casefold(), "")
        if category and category not in cleaned:
            cleaned.append(category)
    return cleaned[:2]


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if value != value:  # NaN without importing pandas.
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _row_get(row, key: str, default=""):
    if row is None:
        return default
    try:
        direct = row.get(key, default)
    except Exception:
        return default
    if _text(direct):
        return direct
    if "." not in key:
        return direct
    current = row
    for part in key.split("."):
        if not isinstance(current, Mapping):
            return direct
        current = current.get(part)
    return current if current is not None else direct


def _labels(value) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = _text(value).split(",")
    return [_text(item) for item in items if _text(item)]


def has_drama_label(value) -> bool:
    """Return True only for the accepted broad drama-edit label."""
    if isinstance(value, Mapping):
        value = value.get("creative_type") or value.get("Creative Type") or value.get("Final Labels")
    return any(label.casefold() == DRAMA_LABEL.casefold() for label in _labels(value))


_ENTERTAINMENT_NEWS_PURPOSE_PATTERN = (
    r"\b(?:entertainment news|editorial|magazine|zine|cover story|actor comparison|"
    r"compares? (?:the )?(?:actor|actress|cast)|casting news|cast announcement|"
    r"interview|press event|red carpet|premiere|fashion media|industry update|"
    r"awards? (?:event|show|appearance)|celebrity spotlight|career evolution|"
    r"celebrity (?:child )?update|actor update|actress update|cast update|"
    r"celebrity banter(?: and interaction)?|cast banter|"
    r"upcoming (?:drama|series|show|release)|series releases?|drama releases?|"
    r"release (?:schedule|calendar|lineup|list)|monthly (?:release|drama) lineup|"
    r"drama watch guide|watch guide|what to watch|drama recommendations?|"
    r"drama tropes?|trope (?:discussion|explainer|ranking)|character profiles?|"
    r"actors? reflect(?:s|ed|ing)? on (?:a |the |his |her |their )?"
    r"(?:role|character|performance|experience|ending)|"
    r"reflect(?:s|ed|ing)? on (?:a |the |his |her |their )?"
    r"(?:role|character|performance|experience|ending)|"
    r"(?:fan|creator|public) concern (?:for|about) .{0,80}(?:health|well[- ]?being)|"
    r"(?:express(?:es|ed|ing)?|rais(?:e|es|ed|ing)) concern (?:for|about) "
    r".{0,80}(?:health|well[- ]?being)|"
    r"(?:health|well[- ]?being) (?:concern|update)|"
    r"livestream (?:discussion|recap|update)|"
    r"recipe tutorial|celebrity news|drama news|tv news|news update)\b"
)

_OBSERVED_FICTIONAL_SCENE_PATTERN = (
    r"\b(?:drama edit|fictional (?:characters?|story|scenes?)|"
    r"scripted (?:scene|episode)|episode scenes?|storyline|"
    r"scenes? from (?:a |the )?(?:chinese |korean |thai |indonesian )?"
    r"(?:drama|series|show|movie)|"
    r"(?:montage|compilation)(?: of)? .{0,180}"
    r"(?:fictional|drama|series|storyline|characters?|leads?|episode scenes?)|"
    r"(?:historical|period|romantic|emotional) (?:chinese |korean |thai |"
    r"indonesian )?(?:drama )?scenes?|"
    r"(?:romantic|protective|emotional) .{0,100}between (?:the )?"
    r"(?:characters?|leads?))\b"
)

_OBSERVED_REAL_WORLD_NEWS_PATTERN = (
    r"\b(?:actors? reflect(?:s|ed|ing)? on (?:a |the |his |her |their )?"
    r"(?:role|character|performance|experience|ending)|"
    r"reflect(?:s|ed|ing)? on (?:a |the |his |her |their )?"
    r"(?:role|character|performance|experience|ending)|"
    r"shares? (?:an? |his |her |their )?(?:emotional )?experience .{0,100}"
    r"(?:role|character|performance|drama|series)|"
    r"livestream (?:discussion|recap|update)|"
    r"(?:fan|creator|public) concern (?:for|about) .{0,80}(?:health|well[- ]?being)|"
    r"(?:express(?:es|ed|ing)?|rais(?:e|es|ed|ing)) concern (?:for|about) "
    r".{0,80}(?:health|well[- ]?being)|"
    r"(?:health|well[- ]?being) (?:concern|update))\b"
)

_HARD_NEWS_UPDATE_PATTERN = (
    r"\b(?:celebrity (?:child )?update|actor update|actress update|cast update|"
    r"celebrity banter(?: and interaction)?|cast banter|casting news|"
    r"cast announcement|industry update|release (?:schedule|calendar|lineup|list)|"
    r"monthly (?:release|drama) lineup|drama watch guide|watch guide|"
    r"what to watch|news update)\b"
)

_PROFILE_LOOK_PURPOSE_PATTERN = (
    r"\b(?:actors?|actress(?:es)?|celebrit(?:y|ies)|stars?|idols?|heroines?)\b"
    r".{0,100}\b(?:look|style|"
    r"costume|appearance|fashion|career) (?:comparison|transformation|evolution)\b|"
    r"\b(?:look|style|costume|appearance|fashion|career) (?:comparison|"
    r"transformation|evolution)\b.{0,100}\b(?:actors?|actress(?:es)?|"
    r"celebrit(?:y|ies)|stars?|idols?|heroines?)\b|"
    r"\b(?:heroine|actress|actor) look comparison\b|"
    r"\b(?:start|beginning) of (?:their |her |his )?careers?\b.{0,100}\b"
    r"(?:current|now|present)\b"
)


def _has_entertainment_news_purpose(blob: str) -> bool:
    return bool(re.search(_ENTERTAINMENT_NEWS_PURPOSE_PATTERN, blob, flags=re.I))


def _has_hard_news_update(blob: str) -> bool:
    return bool(re.search(_HARD_NEWS_UPDATE_PATTERN, blob, flags=re.I))


def _has_profile_look_purpose(blob: str) -> bool:
    return bool(re.search(_PROFILE_LOOK_PURPOSE_PATTERN, blob, flags=re.I))


def _has_observed_fictional_scene_purpose(blob: str) -> bool:
    return bool(re.search(_OBSERVED_FICTIONAL_SCENE_PATTERN, blob, flags=re.I))


def _has_observed_real_world_news_purpose(blob: str) -> bool:
    return bool(re.search(_OBSERVED_REAL_WORLD_NEWS_PATTERN, blob, flags=re.I))


def promote_entertainment_news_label(result: Dict, row=None) -> Dict:
    """Route strong entertainment/show/lifestyle evidence into the drama family.

    This is intentionally evidence-based and reusable. A normal celebrity fan
    montage stays Celebrity Edits; editorial reporting, actor comparisons,
    casting/red-carpet coverage, actor/actress daily-life posts,
    entertainment-industry updates, and explicit K-pop interview/show cuts
    become Movie/Tv/Drama Edits for the second pass.
    """
    output = dict(result or {})
    labels = _labels(output.get("creative_type"))
    if not labels:
        return output
    evidence = " ".join([
        _text(output.get("narrative")),
        _text(output.get("content_details")),
        _text(_row_get(row, "text")),
        _hashtags(row),
    ]).casefold()
    news_cue = _has_entertainment_news_purpose(evidence)
    hard_news_update = _has_hard_news_update(evidence)
    entertainment_quiz_cue = re.search(
        r"\b(?:guess the mascot|mascot (?:name )?(?:quiz|game)|"
        r"quiz format.{0,80}mascot)\b",
        evidence,
    )
    real_subject = re.search(
        r"\b(?:actors?|actress(?:es)?|cast|celebrit(?:y|ies)|stars?|public figures?|"
        r"idols?|editorial|magazine|zine)\b",
        evidence,
    )
    real_pair_cue = re.search(
        r"\b(?:two|pair of)\b.{0,80}\b(?:actors?|actress(?:es)?|celebrit(?:y|ies)|"
        r"idols?|stars?|public figures?)\b|"
        r"\b(?:actors?|actress(?:es)?|celebrit(?:y|ies)|idols?|stars?|public figures?)\b"
        r".{0,80}\b(?:pair|couple|duo)\b",
        evidence,
    )
    affection_cue = re.search(
        r"\b(?:romantic(?:ally)?|romance|couple (?:interaction|moments?|chemistry)|"
        r"affection(?:ate|ately|ion)?|close chemistry|shipping|ship edit|pairing|"
        r"flirt(?:ing|atious)?|cuddl(?:e|ing)|embrac(?:e|ing)|holding hands|"
        r"off[- ]screen (?:chemistry|romance)|playful chemistry|cute gestures?|"
        r"hearts? (?:at|to) (?:the )?camera)\b",
        evidence,
    )
    fictional_story_cue = re.search(
        r"\b(?:fictional (?:characters?|story|scene)|scripted (?:scene|episode)|"
        r"episode scene|drama scene|storyline|on[- ]screen characters?|"
        r"characters? in (?:a |the )?(?:drama|series|movie))\b",
        evidence,
    )
    bl_marker = re.search(
        r"(?:#(?:thai)?bl(?:series|drama|edit|cp)?\b|\bboys?[ '\u2019-]*love\b|"
        r"\bbl (?:drama|series|couple|cp|romance)\b)",
        evidence,
    )
    gl_marker = re.search(
        r"(?:#(?:thai)?gl(?:series|drama|edit|cp)?\b|#girlslove\b|#yuri\b|"
        r"#girllovegirl\b|#girlxgirl\b|"
        r"\bgirls?[ '\u2019-]*love(?:[ '\u2019-]*girls?)?\b|"
        r"\bgl (?:drama|series|couple|cp|romance)\b)",
        evidence,
    )
    explicit_male_pair = re.search(
        r"(?:\bmale[- ]male\b|\btwo (?:male(?: actors?| idols?| celebrities?)?|"
        r"men|boys)\b|\bboth (?:male|men)\b)",
        evidence,
    )
    explicit_female_pair = re.search(
        r"(?:\bfemale[- ]female\b|\btwo (?:female(?: actresses?| idols?|"
        r" celebrities?)?|women|girls|actress(?:es)?)\b|"
        r"\bboth (?:female|women|actress(?:es)?)\b|"
        r"\bactresses\b.{0,160}\b(?:together|each other|paired?)\b|"
        r"\b(?:together|paired?)\b.{0,160}\bactresses\b)",
        evidence,
    )
    male_pair_cue = bl_marker or explicit_male_pair
    female_pair_cue = gl_marker or explicit_female_pair
    plural_public_subject = re.search(
        r"\b(?:actors|actresses|celebrities|idols|stars|public figures)\b",
        evidence,
    )
    real_world_context = re.search(
        r"\b(?:fan ?meet(?:ing)?|promotional (?:event|appearance|activity)|"
        r"press event|on stage|stage interaction|interview|behind[- ]the[- ]scenes|"
        r"backstage|variety show|off[- ]screen|(?:at|to) (?:the )?camera|selfie|"
        r"portrait(?:s| images)?|photo(?:s|shoot)?|editorial|pose together|"
        r"retail setting|shopping mall|store|casual (?:indoor )?(?:setting|environment)|"
        r"close[- ]up (?:playful )?shots?|cute poses?)\b",
        evidence,
    )
    pair_interaction_cue = re.search(
        r"\b(?:fan ?service|feeding each other|interact(?:ing|ion) with each other|"
        r"playful (?:interaction|shots?|poses?|moments?)|affectionate interaction|"
        r"heart gestures?|cute (?:gestures?|poses?)|make hearts?|paired? promotion|"
        r"promot(?:e|ing) their .{0,50}appearance|"
        r"appear(?:ing|ance) together|share(?:d|s|ing)? .{0,30}(?:activity|moment)|"
        r"lip[- ]?sync(?:ing)? together|matching (?:outfits?|headbands?|accessories)|"
        r"pose together|(?:eat|eating|enjoy(?:ing)?) .{0,60} together|"
        r"chemistry|shipping|romantic|affectionate)\b",
        evidence,
    )
    carousel_cue = re.search(
        r"\b(?:photo carousel|carousel|photo slideshow|slideshow|multi[- ]image|"
        r"series of images|portrait images|multiple (?:photos?|portraits?|images?))\b",
        evidence,
    )
    profile_carousel_cue = re.search(
        r"\b(?:split[- ]screen image|before[- ]and[- ]after|career evolution|"
        r"celebrity child spotlight|collection of portraits?|profile images?|"
        r"various high[- ]fashion outfits?|multiple public appearances?)\b",
        evidence,
    )
    profile_look_cue = _has_profile_look_purpose(evidence)
    profile_ranking_cue = re.search(
        r"(?:\b(?:actors?|actress(?:es)?|celebrit(?:y|ies)|stars?|idols?|"
        r"public figures?)\b.{0,140}\b(?:ranking|ranked|net worth|richest|"
        r"highest[- ]paid|top \d+|career facts?|profile|biograph(?:y|ies))\b|"
        r"\b(?:ranking|ranked|net worth|richest|highest[- ]paid|top \d+|"
        r"career facts?|profile|biograph(?:y|ies))\b.{0,140}\b(?:actors?|"
        r"actress(?:es)?|celebrit(?:y|ies)|stars?|idols?|public figures?)\b)",
        evidence,
    )
    behind_scenes_cue = re.search(
        r"\b(?:behind[- ]the[- ]scenes|on set|filming|production footage|"
        r"rehearsal|camera crew|cast members? between takes?|bloopers?)\b",
        evidence,
    )
    kpop_subject = re.search(
        r"\b(?:k[- ]?pop|korean idols?|idol group|boy group|girl group|"
        r"big ?bang|bts|blackpink|exo|twice|stray kids|seventeen|aespa|"
        r"enhypen|txt|tomorrow x together|nct|shinee|super junior|2ne1)\b",
        evidence,
    )
    kpop_show_cue = re.search(
        r"\b(?:interviews?|talk show|variety show|reality show|broadcast (?:clip|segment)|"
        r"show (?:clip|cut|segment)|studio banter|funny banter|members? (?:joking|"
        r"talking|reacting)|humorous reactions?|on[- ]screen subtitles?|dialogue)\b",
        evidence,
    )
    kpop_structured_context_cue = re.search(
        r"\b(?:behind[- ]the[- ]scenes|promotional (?:clip|segment|activity)|"
        r"music[- ]video(?: (?:production|planning|concept|segment))?|recording studio|"
        r"studio (?:segment|activity|session)|game|task|challenge|puzzle)\b",
        evidence,
    )
    kpop_structured_interaction_cue = re.search(
        r"\b(?:members?|idols?|artists?|group)\b.{0,120}\b(?:interact(?:ing|ion)?|"
        r"collaborat(?:e|es|ing|ion)|brainstorm(?:s|ing|ed)?|complete(?:s|d|ing)?|"
        r"plan(?:s|ning|ned)?|perform(?:s|ing|ance)?|react(?:s|ing|ion)?)\b|"
        r"\b(?:interact(?:ing|ion)?|collaborat(?:e|es|ing|ion)|brainstorm(?:s|ing|ed)?|"
        r"complete(?:s|d|ing)?|plan(?:s|ning|ned)?|perform(?:s|ing|ance)?)\b.{0,120}"
        r"\b(?:members?|idols?|artists?|group)\b",
        evidence,
    )
    kpop_show_dominant_cue = re.search(
        r"\b(?:montage featuring interviews?|interviews?.{0,100}discuss(?:ing|ion)|"
        r"interspersed with (?:short )?clips?|interview (?:segment|montage)|"
        r"talk show (?:clip|segment)|variety show (?:clip|segment))\b",
        evidence,
    )
    daily_lifestyle_cue = re.search(
        r"\b(?:actor(?:'s)?|actress(?:'s)?|celebrity|star)\b.*\b(?:daily life|"
        r"day in (?:the|their) life|daily vlog|lifestyle|casual (?:life|moments?|"
        r"activities|outing)|creative activities|art studio|with (?:a |the )?"
        r"(?:kitten|cat|puppy|dog|pet)|travel[- ]themed|vacation|various locations)\b|"
        r"\b(?:daily life|day in (?:the|their) life|daily vlog|lifestyle|"
        r"creative activities|art studio|travel[- ]themed|various locations)\b.*"
        r"\b(?:actor|actress|celebrity|star)\b",
        evidence,
    )
    montage_cue = re.search(
        r"\b(?:montage|vlog|day in (?:the|their) life|interacting|activities|"
        r"various locations|casual moments?|travel[- ]themed)\b",
        evidence,
    )
    explicit_dance_cue = re.search(
        r"\b(?:dance routine|dancing|dance challenge|choreograph(?:y|ed)|"
        r"synchroni[sz]ed (?:dance|movement)|rhythmic (?:body )?movement)\b",
        evidence,
    )
    source_labels = set(labels) & {
        "Celebrity Edits", "Media/Infotainment", "Fashion", DRAMA_LABEL
    }
    cp_candidate_labels = set(labels) & {
        "Celebrity Edits", "Relationship", "Carousel", "Lyrics", DRAMA_LABEL
    }
    entertainment_news = bool(
        source_labels
        and (
            (
                news_cue
                and (
                    real_subject
                    or "Media/Infotainment" in labels
                    or "Carousel" in labels
                )
            )
            or (
                entertainment_quiz_cue
                and "Media/Infotainment" in labels
            )
        )
    )
    structured_kpop_segment = bool(
        kpop_structured_context_cue and kpop_structured_interaction_cue
    )
    kpop_show_cut = bool(
        kpop_subject
        and (kpop_show_cue or structured_kpop_segment)
        and source_labels
    )
    actor_daily_vlog = bool(
        real_subject and daily_lifestyle_cue and montage_cue and source_labels
    )
    real_cp_edit = bool(
        "Celebrity Edits" in labels
        and real_subject
        and real_pair_cue
        and (affection_cue or pair_interaction_cue)
        and not fictional_story_cue
    )
    marker_supported_pair = bool(
        (bl_marker or gl_marker)
        and (real_pair_cue or plural_public_subject or explicit_male_pair or explicit_female_pair)
        and real_world_context
        and not (
            profile_ranking_cue
            and not (affection_cue or pair_interaction_cue or real_pair_cue)
        )
    )
    explicit_gender_pair = bool(
        (explicit_male_pair or explicit_female_pair)
        and real_world_context
    )
    offscreen_same_gender_cp = bool(
        cp_candidate_labels
        and (marker_supported_pair or explicit_gender_pair)
        and (pair_interaction_cue or affection_cue or marker_supported_pair)
        and not fictional_story_cue
    )
    strict_relationship_cp = bool(
        "Relationship" in labels and offscreen_same_gender_cp
    )
    actor_carousel = bool(
        ("Celebrity Edits" in labels or DRAMA_LABEL in labels)
        and (real_subject or profile_look_cue)
        and (
            "Carousel" in labels
            or carousel_cue
            or profile_carousel_cue
            or profile_ranking_cue
            or profile_look_cue
        )
        and (profile_ranking_cue or profile_carousel_cue or profile_look_cue or carousel_cue)
        and not hard_news_update
        and not (
            (affection_cue or pair_interaction_cue)
            and (real_pair_cue or explicit_male_pair or explicit_female_pair)
        )
        and not fictional_story_cue
    )
    behind_scenes_edit = bool(
        source_labels
        and behind_scenes_cue
        and (real_subject or plural_public_subject)
    )
    possible_same_gender_cp = bool(
        bool(cp_candidate_labels)
        and bool(male_pair_cue or female_pair_cue)
        and (affection_cue or pair_interaction_cue or real_pair_cue)
        and not offscreen_same_gender_cp
        and not fictional_story_cue
    )
    if not (
        entertainment_news
        or kpop_show_cut
        or actor_daily_vlog
        or real_cp_edit
        or offscreen_same_gender_cp
        or strict_relationship_cp
        or actor_carousel
        or behind_scenes_edit
    ):
        ambiguous_entertainment_family = bool(
            source_labels
            and (real_subject or bl_marker or gl_marker)
            and (
                news_cue
                or behind_scenes_cue
                or carousel_cue
                or profile_carousel_cue
                or profile_ranking_cue
                or profile_look_cue
                or pair_interaction_cue
            )
        )
        if possible_same_gender_cp or ambiguous_entertainment_family:
            reason = (
                "Possible real-person BL/GL CP edit needs human confirmation"
                if possible_same_gender_cp
                else "Possible drama or entertainment subtype needs human confirmation"
            )
            output["needs_human_review"] = True
            existing = [
                part.strip()
                for part in _text(output.get("review_risk_reasons")).split("|")
                if part.strip()
            ]
            if reason not in existing:
                existing.append(reason)
            output["review_risk_reasons"] = " | ".join(existing)
        return output
    promoted = []
    replaced = False
    for label in labels:
        if label in {"Celebrity Edits", "Media/Infotainment"} and not replaced:
            promoted.append(DRAMA_LABEL)
            replaced = True
        elif (
            label not in {"Celebrity Edits", "Media/Infotainment"}
            and not (
                actor_daily_vlog
                and label == "Dance"
                and not explicit_dance_cue
            )
            and not (
                kpop_show_cut
                and kpop_show_dominant_cue
                and label == "Dance"
            )
        ):
            promoted.append(label)
    if not replaced:
        promoted.insert(0, DRAMA_LABEL)
    output["creative_type"] = list(dict.fromkeys(promoted))[:2]
    output["_drama_content_kind_hint"] = (
        "CP Edit"
        if real_cp_edit or offscreen_same_gender_cp or strict_relationship_cp
        else (
            "Actor/Actress Carousel"
            if actor_carousel
            else (
                "K-pop Show Cut"
                if kpop_show_cut
                else (
                    "Behind-the-Scenes Edit"
                    if behind_scenes_edit
                    else (
                        "Actor/Actress Daily Vlog"
                        if actor_daily_vlog
                        else "Entertainment News"
                    )
                )
            )
        )
    )
    return output


def _hashtags(row) -> str:
    raw = _row_get(row, "hashtags", [])
    if not isinstance(raw, list):
        return _text(raw)
    names = []
    for value in raw:
        name = value.get("name", "") if isinstance(value, Mapping) else value
        if _text(name):
            names.append(f"#{_text(name).lstrip('#')}")
    return " ".join(names)


def build_drama_prompt(result: Mapping, row=None) -> str:
    """Build the conditional second-pass prompt for drama/entertainment detail."""
    caption = _text(_row_get(row, "text"))
    music_name = _text(_row_get(row, "musicMeta.musicName"))
    music_author = _text(_row_get(row, "musicMeta.musicAuthor"))
    campaign_track = _text(_row_get(row, "_campaign_track"))
    market = _text(_row_get(row, "_campaign_market"))
    kind_hint = _text(result.get("_drama_content_kind_hint"))
    base_narrative = _text(result.get("narrative"))
    base_details = _text(result.get("content_details"))
    return f"""You are performing a SECOND-PASS drama/entertainment enrichment after the broad classifier has already confirmed {DRAMA_LABEL}.
Do not change the broad Creative Type. Analyse the supplied frames and metadata for reusable marketing details.

Existing visual summary: {base_details or '(not available)'}
Existing narrative: {base_narrative or '(not available)'}
Caption: {caption or '(none)'}
Hashtags: {_hashtags(row) or '(none)'}
TikTok audio title: {music_name or '(unknown)'}
TikTok audio artist: {music_author or '(unknown)'}
Campaign track: {campaign_track or '(not specified)'}
Campaign market: {market or '(not specified)'}
Content-category hint: {kind_hint or '(none)'}

Important evidence rules:
- First choose one or two Content Categories from this controlled list: Drama Edit, CP Edit, Entertainment News, Anime Edit, Actor/Actress Carousel, Drama Carousel, Behind-the-Scenes Edit, K-pop Show Cut, Actor/Actress Daily Vlog, POV, Other.
- Use a second category only when it describes a genuinely separate purpose or format (for example Entertainment News + CP Edit). Do not add categories merely because an actor or drama appears.
- Entertainment News covers real actors/celebrities and entertainment properties in editorials, interviews, press/red-carpet coverage, casting/news updates, celebrity/family updates, release schedules, watch guides, or creator-led actor comparisons. It is not a fictional scene edit.
- A real actor interview, press Q&A, talk-show segment, or actor discussing a drama, role, episode or ending is Entertainment News even when the topic is a fictional drama. Drama hashtags, a drama title or illustrative drama clips do not turn interview footage into Drama Edit.
- Anime Edit covers anime scenes or anime characters. Do not call anime General Drama.
- Drama Edit covers fictional live-action drama/movie/TV/web-series scenes and story edits.
- CP Edit covers real-actor/public-figure chemistry, shipping or pairing content. BL/GL is recorded in drama_type and edit_focus.
- Actor/Actress Carousel and Drama Carousel require a real multi-image/slideshow carousel. They are not generic labels for every montage.
- Drama Carousel is for slides built from fictional drama characters, drama stills, scenes, plot points or character-relationship information. The presence of named actors does not make those fictional slides an Actor/Actress Carousel.
- Actor/Actress Carousel is for the real person: portraits, career facts, real-person look/style comparisons, fashion, travel, public appearances or other off-screen/profile material. Do not use it when the slides primarily show actors as their drama characters.
- Behind-the-Scenes Edit requires explicit production, rehearsal, filming or off-screen evidence.
- K-pop Show Cut is a clipped segment from a Korean music/variety/reality show; Actor/Actress Daily Vlog is real-life daily activity rather than a fictional scene.
- Drama Country/Region means the ORIGINAL PRODUCTION or content-subject country/region, never the uploader market and never the campaign market. Song language, caption language and generic country hashtags alone are not proof.
- Fictional scenes/characters from a BL or GL story are BL Drama or GL Drama with Fictional Story focus.
- BL CP Edit / GL CP Edit is for REAL actors or public figures in interviews, fan meetings, behind-the-scenes footage, events, off-screen chemistry or shipping montages. Do not call a fictional scene a CP edit.
- Real-world fan service, feeding each other, paired promotional appearances, on-stage pair interaction and heart gestures can support CP Edit when the people and pair are explicit.
- Content purpose outranks format: a carousel centred on an explicit real-person ship/pair is CP Edit, while a single-actor career/portrait or lookalike slideshow is Actor/Actress Carousel.
- When CP evidence is explicit, return CP Edit rather than adding Actor/Actress Carousel merely because the post is a slideshow. When production evidence is explicit, return Behind-the-Scenes Edit unless a separate romantic/off-screen pairing purpose is also clearly present.
- A BL/GL hashtag alone is never enough. Require a visible or described pair plus real/off-screen interaction evidence; otherwise request review.
- BL requires explicit evidence of a male-male romantic pairing; GL requires explicit evidence of a female-female romantic pairing. A male-female romantic pair must never be labelled BL or GL. State the supporting genders in evidence when using BL or GL.
- If real-person CP evidence is strong but the pair's genders are not explicit, keep CP Edit with Unknown subtype and request review rather than guessing BL or GL from names.
- General Drama is used when fictional drama evidence exists but BL/GL evidence does not.
- A close-up of one actor or cast montage is Cast/Actor Edit unless the evidence is clearly a fictional story scene.
- Drama Format is production format only: Long-form Drama or Short-form Drama. Never use Fan Edit or Scene Compilation as a format.
- Short-form Drama requires explicit short/micro/vertical/platform-format evidence. The length of this TikTok clip is not the drama format.
- For a Drama Edit with no short-form evidence, use Long-form Drama as the operational default rather than Unknown.
- Any explicitly identified short-form, short web, vertical or micro drama is Short-form Drama.
- Only Drama Edit uses drama_format. Short-form Drama is a format, not a separate Content Category. For every other Content Category return Not applicable for drama_format.
- For categories unrelated to live-action drama/CP, return Unknown for drama_type and edit_focus.
- Only name a drama title when the title is visible or explicitly present in reliable caption/hashtag evidence. Otherwise use Unknown.
- If a caption or hashtag clearly states the drama/show/anime title, return that readable title even when the visual frames do not contain a title card. Decode a title-styled CamelCase or underscore hashtag only when the surrounding evidence identifies it as the title. Never use actor names, fandom tags, generic tags or the campaign song as a drama title.
- Audio speed/version must be based on explicit metadata, audible evidence or comparison evidence. A song title match alone does not prove Original, Sped Up or Slowed.
- When evidence is insufficient, use Unknown and explain the uncertainty. Do not guess from creator, exact URL or campaign market.

Return ONLY one JSON object with this exact schema:
{{
  "content_categories": ["one or two values from the controlled Content Category list"],
  "drama_type": "General Drama | BL Drama | GL Drama | Unknown",
  "edit_focus": "Fictional Story | BL CP Edit | GL CP Edit | Cast/Actor Edit | Character Edit | General Drama Edit | Unknown",
  "drama_format": "Long-form Drama | Short-form Drama | Not applicable",
  "country_region": "Thailand | China | Taiwan | Hong Kong | Korea | Japan | Malaysia | Indonesia | Philippines | Singapore | Vietnam | United States | United Kingdom | Other | Unknown",
  "drama_title": "title or Unknown",
  "detected_audio": "detected song/audio or Unknown",
  "audio_version": "Original | Sped Up | Slowed | Remix | Unknown",
  "visual_summary": "one factual sentence describing the observed drama or entertainment post",
  "evidence": ["up to five short factual observations"],
  "review_reason": "short reason when any important field is uncertain, otherwise empty"
}}"""


def _choice(value, allowed: Iterable[str], aliases: Optional[Mapping[str, str]] = None, default="Unknown") -> str:
    text = _text(value)
    if text in allowed:
        return text
    alias = (aliases or {}).get(text.casefold())
    return alias if alias in allowed else default


def _clean_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", _text(value))
    text = re.sub(r"\([^)]*(?:sped|slowed|remix|version|edit)[^)]*\)", " ", text, flags=re.I)
    text = re.sub(r"\b(?:sped\s*up|speed\s*up|slowed(?:\s*down)?|nightcore|remix|reverb(?:ed)?|version)\b", " ", text, flags=re.I)
    # Keep Unicode letters, numbers and combining marks.  The previous
    # ``[^a-z0-9]`` rule erased Chinese, Thai and Korean titles before the
    # Apple catalogue candidate was scored, making every native-script match
    # look empty.  Punctuation is still folded to spaces for stable matching.
    normalized = []
    for character in text.casefold():
        if unicodedata.category(character)[:1] in {"L", "N", "M"}:
            normalized.append(character)
        else:
            normalized.append(" ")
    return " ".join("".join(normalized).split())


def _itunes_storefronts(value: str) -> Tuple[str, ...]:
    """Return a small storefront fallback order for the title's script.

    Apple search results vary by storefront.  Keep the fallback list short so
    one new track does not consume an excessive number of public API calls.
    """
    text = unicodedata.normalize("NFKC", _text(value))
    codepoints = {ord(character) for character in text}

    def contains(ranges: Iterable[Tuple[int, int]]) -> bool:
        return any(start <= point <= end for point in codepoints for start, end in ranges)

    if contains(((0x0E00, 0x0E7F),)):
        return ("TH", "SG", "US")
    if contains(((0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7AF))):
        return ("KR", "SG", "US")
    if contains(((0x3040, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9D))):
        return ("JP", "US")
    if contains(((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x2FA1F))):
        return ("TW", "HK", "SG", "CN", "US")
    return ("US",)


def _similar(left: str, right: str, threshold: float = 0.72) -> bool:
    a, b = _clean_title(left), _clean_title(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _similarity_score(left: str, right: str) -> float:
    a, b = _clean_title(left), _clean_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) + 0.15
    return SequenceMatcher(None, a, b).ratio()


def _generic_audio_title(value: str) -> bool:
    raw = _text(value).casefold()
    # TikTok localizes its generic creator-audio label.  Preserve the creator
    # name for traceability, but do not mistake labels such as ``原声 - user``
    # for an actual song title.
    if re.match(
        r"^(?:原声|原聲|原创音乐|原創音樂|오리지널\s*사운드|オリジナル楽曲)"
        r"(?:\s*[-–—:：]\s*.*)?$",
        raw,
    ):
        return True
    folded = "".join(
        character
        for character in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(character)
    )
    text = _clean_title(folded)
    if not text:
        return True
    generic_phrases = {
        "original sound", "original audio", "sound", "audio",
        "nhac nen", "am thanh goc", "son original", "suono originale",
        "originalton", "som original",
    }
    return any(
        text == phrase or text.startswith(f"{phrase} ")
        for phrase in generic_phrases
    )


def split_campaign_track(value: str) -> Tuple[str, str]:
    """Return (artist, song) for the common ``Artist - Song`` input format."""
    text = _text(value)
    if " - " in text:
        artist, song = text.split(" - ", 1)
        return _text(artist), _text(song)
    return "", text


def _review_campaign_song(row: Mapping) -> str:
    """Return a usable campaign song for Review defaults, if one exists."""
    placeholders = {"unknown", "not specified", "other", "n/a", "na", "-"}
    for key in ("_campaign_track", "Track", "track"):
        _artist, song = split_campaign_track(_row_get(row, key))
        if song and song.casefold() not in placeholders:
            return song
    return ""


_ITUNES_CACHE_TTL_SECONDS = 24 * 60 * 60
_ITUNES_CACHE_MAX_ENTRIES = 256
_ITUNES_PREVIEW_CACHE: "OrderedDict[Tuple[str, str], Tuple[float, Dict[str, str]]]" = OrderedDict()
_ITUNES_PREVIEW_CACHE_LOCK = threading.RLock()


def _itunes_cache_key(campaign_track: str) -> Tuple[str, str]:
    """Return a stable artist/title key for one Apple catalogue lookup."""
    artist, song = split_campaign_track(campaign_track)
    return (_clean_title(artist), _clean_title(song))


def clear_itunes_preview_cache() -> None:
    """Clear cached Apple catalogue metadata (primarily useful for tests)."""
    with _ITUNES_PREVIEW_CACHE_LOCK:
        _ITUNES_PREVIEW_CACHE.clear()


def _cached_itunes_preview(campaign_track: str) -> Dict[str, str]:
    key = _itunes_cache_key(campaign_track)
    if not key[1]:
        return {}
    now = time.monotonic()
    with _ITUNES_PREVIEW_CACHE_LOCK:
        cached = _ITUNES_PREVIEW_CACHE.get(key)
        if not cached:
            return {}
        stored_at, value = cached
        if now - stored_at >= _ITUNES_CACHE_TTL_SECONDS:
            _ITUNES_PREVIEW_CACHE.pop(key, None)
            return {}
        _ITUNES_PREVIEW_CACHE.move_to_end(key)
        return dict(value)


def _store_itunes_preview(campaign_track: str, value: Mapping[str, str]) -> None:
    """Cache only successful matches so temporary Apple failures can recover."""
    if not value:
        return
    key = _itunes_cache_key(campaign_track)
    if not key[1]:
        return
    now = time.monotonic()
    with _ITUNES_PREVIEW_CACHE_LOCK:
        _ITUNES_PREVIEW_CACHE[key] = (now, dict(value))
        _ITUNES_PREVIEW_CACHE.move_to_end(key)
        while len(_ITUNES_PREVIEW_CACHE) > _ITUNES_CACHE_MAX_ENTRIES:
            _ITUNES_PREVIEW_CACHE.popitem(last=False)


def fetch_itunes_preview(campaign_track: str, timeout: int = 8, http_get=None) -> Dict[str, str]:
    """Find an Apple/iTunes candidate, including native-script storefront fallbacks."""
    artist, song = split_campaign_track(campaign_track)
    if not song:
        return {}
    # Production calls share one bounded metadata cache across Streamlit reruns
    # and concurrent sessions in the same Python process. Injected HTTP clients
    # deliberately bypass it so unit tests remain isolated and deterministic.
    if http_get is None:
        cached = _cached_itunes_preview(campaign_track)
        if cached:
            return cached
    if http_get is None:
        import requests
        getter = requests.get
    else:
        getter = http_get
    query = f"{artist} {song}".strip()
    for storefront in _itunes_storefronts(query):
        try:
            response = getter(
                "https://itunes.apple.com/search",
                params={
                    "term": query,
                    "country": storefront,
                    "media": "music",
                    "entity": "song",
                    "limit": 15,
                },
                timeout=timeout,
            )
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            payload = response.json() if hasattr(response, "json") else {}
        except Exception:
            # A regional lookup failure must not stop the remaining safe
            # storefront fallbacks, and an overall miss remains unconfirmed.
            continue

        candidates = []
        for item in payload.get("results", []) if isinstance(payload, Mapping) else []:
            title_score = _similarity_score(song, item.get("trackName", ""))
            artist_score = _similarity_score(artist, item.get("artistName", "")) if artist else 0.0
            if title_score < 0.72 or (artist and artist_score < 0.66):
                continue
            # Song title is the required signal. Artist, when supplied, is an
            # optional disambiguator rather than a second mandatory UI field.
            candidates.append((title_score + artist_score * 0.35, item))
        if candidates:
            _, item = max(candidates, key=lambda pair: pair[0])
            match = {
                "track_name": _text(item.get("trackName")),
                "artist_name": _text(item.get("artistName")),
                "preview_url": _text(item.get("previewUrl")),
                "track_view_url": _text(item.get("trackViewUrl")),
                "storefront": storefront,
            }
            if http_get is None:
                _store_itunes_preview(campaign_track, match)
            return match
    return {}


def campaign_track_catalog_status(campaign_track: str, http_get=None) -> Dict[str, str]:
    """Return a safe, non-blocking Apple/iTunes confirmation result.

    An empty catalogue result can mean either that the song was not found or
    that the public lookup was temporarily unavailable.  Callers must therefore
    describe it as *unconfirmed*, never as an invalid track.
    """
    input_track = _text(campaign_track)
    if not input_track or input_track.casefold() in {
        "unknown", "not specified", "other", "n/a", "na", "-",
    }:
        return {
            "status": "blank",
            "input_track": input_track,
            "track_name": "",
            "artist_name": "",
        }

    match = fetch_itunes_preview(input_track, http_get=http_get)
    if match:
        return {
            "status": "matched",
            "input_track": input_track,
            "track_name": _text(match.get("track_name")),
            "artist_name": _text(match.get("artist_name")),
            "track_view_url": _text(match.get("track_view_url")),
        }

    return {
        "status": "unconfirmed",
        "input_track": input_track,
        "track_name": "",
        "artist_name": "",
    }


def _ffmpeg_executable() -> str:
    """Return the bundled ffmpeg executable used for portable audio extraction."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _extract_audio_with_ffmpeg(input_path: str, output_path: str, duration: int = 40) -> bool:
    """Extract a short mono clip without requiring a user-installed ffmpeg."""
    command = [
        _ffmpeg_executable(),
        "-y",
        "-i",
        input_path,
        "-t",
        str(duration),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "22050",
        "-b:a",
        "128k",
        output_path,
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=90,
            check=False,
        )
        return (
            completed.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
        )
    except Exception:
        return False


def _save_preview_audio(preview_url: str, output_path: str, timeout: int = 60, http_get=None) -> None:
    """Download the small official preview used as the comparison reference."""
    if http_get is None:
        import requests

        getter = requests.get
    else:
        getter = http_get
    response = getter(preview_url, timeout=timeout)
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    content = getattr(response, "content", b"")
    if not content:
        raise ValueError("The official audio preview was empty")
    with open(output_path, "wb") as handle:
        handle.write(content)


def compare_video_audio_to_preview(
    video_path: str,
    preview_url: str,
    http_get=None,
) -> Dict[str, Any]:
    """Compare TikTok audio with an official preview and estimate speed changes.

    The comparison uses tempo plus CENS-chroma/DTW alignment across several
    time-stretch candidates. It stays Unknown when the preview and TikTok
    segments do not align strongly enough instead of forcing Original.
    """
    if not video_path or not os.path.exists(video_path) or not preview_url:
        return {
            "audio_version": "Unknown",
            "audio_evidence": "A TikTok video or official preview was unavailable.",
            "similarity": 0.0,
        }
    try:
        import librosa
        import numpy as np
        from librosa.sequence import dtw
    except Exception as exc:
        return {
            "audio_version": "Unknown",
            "audio_evidence": f"Audio comparison libraries were unavailable: {exc}",
            "similarity": 0.0,
        }

    def _trim(samples):
        try:
            trimmed, _ = librosa.effects.trim(samples, top_db=35)
            return trimmed if len(trimmed) else samples
        except Exception:
            return samples

    def _tempo(samples, sample_rate):
        try:
            values = librosa.feature.tempo(y=samples, sr=sample_rate, aggregate=None)
            return float(values[0]) if len(values) else 0.0
        except Exception:
            return 0.0

    def _chroma(samples, sample_rate):
        chroma = librosa.feature.chroma_cens(y=samples, sr=sample_rate)
        if chroma.shape[1] > 9:
            kernel = np.ones(5) / 5
            chroma = np.stack([
                np.convolve(row, kernel, mode="same") for row in chroma
            ])
        return chroma

    def _dtw_score(left, right):
        try:
            left = left[:, ::2]
            right = right[:, ::2]
            if left.shape[1] < 8 or right.shape[1] < 8:
                return 0.0
            distance, path = dtw(X=left, Y=right, metric="cosine")
            normalized = float(distance[-1, -1]) / max(len(path), 1)
            return max(0.0, min(1.0, 1.0 - normalized))
        except Exception:
            return 0.0

    with tempfile.TemporaryDirectory() as tmp:
        preview_path = os.path.join(tmp, "official_preview.m4a")
        video_audio = os.path.join(tmp, "tiktok_audio.mp3")
        preview_audio = os.path.join(tmp, "preview_audio.mp3")
        try:
            _save_preview_audio(preview_url, preview_path, http_get=http_get)
        except Exception as exc:
            return {
                "audio_version": "Unknown",
                "audio_evidence": f"The official preview could not be downloaded: {exc}",
                "similarity": 0.0,
            }
        if not _extract_audio_with_ffmpeg(video_path, video_audio):
            return {
                "audio_version": "Unknown",
                "audio_evidence": "The TikTok audio could not be extracted.",
                "similarity": 0.0,
            }
        if not _extract_audio_with_ffmpeg(preview_path, preview_audio):
            return {
                "audio_version": "Unknown",
                "audio_evidence": "The official preview audio could not be extracted.",
                "similarity": 0.0,
            }

        try:
            tiktok_audio, sample_rate = librosa.load(
                video_audio, sr=22050, mono=True, duration=40
            )
            official_audio, _ = librosa.load(
                preview_audio, sr=22050, mono=True, duration=40
            )
            tiktok_audio = _trim(tiktok_audio)
            official_audio = _trim(official_audio)
            if len(tiktok_audio) < sample_rate * 5 or len(official_audio) < sample_rate * 5:
                return {
                    "audio_version": "Unknown",
                    "audio_evidence": "The available audio was too short for comparison.",
                    "similarity": 0.0,
                }

            tiktok_tempo = _tempo(tiktok_audio, sample_rate)
            official_tempo = _tempo(official_audio, sample_rate)
            tempo_ratio = tiktok_tempo / official_tempo if official_tempo else 1.0
            while tempo_ratio >= 1.6:
                tempo_ratio /= 2.0
            while 0 < tempo_ratio <= 0.55:
                tempo_ratio *= 2.0

            tempo_label = "Unknown"
            if 0.72 <= tempo_ratio <= 0.88:
                tempo_label = "Slowed"
            elif 1.12 <= tempo_ratio <= 1.35:
                tempo_label = "Sped Up"

            # rate is the correction applied to the TikTok audio. If a slowed
            # TikTok must be sped up by 1.25x to match, its label is Slowed.
            candidates = [
                ("Sped Up", 0.75),
                ("Sped Up", 0.80),
                ("Sped Up", 0.90),
                ("Original", 1.00),
                ("Slowed", 1.11),
                ("Slowed", 1.20),
                ("Slowed", 1.25),
                ("Slowed", 1.33),
            ]
            official_chroma = _chroma(official_audio, sample_rate)
            scores = []
            for label, rate in candidates:
                try:
                    corrected = librosa.effects.time_stretch(tiktok_audio, rate=rate)
                    score = _dtw_score(
                        _chroma(corrected, sample_rate), official_chroma
                    )
                    scores.append((score, label, rate))
                except Exception:
                    continue
            if not scores:
                raise ValueError("No audio alignment score could be calculated")

            scores.sort(reverse=True, key=lambda item: item[0])
            best_score, best_label, best_rate = scores[0]
            original_score = max(
                [score for score, label, _ in scores if label == "Original"] or [0.0]
            )
            best_alternative = max(
                [item for item in scores if item[1] != "Original"],
                key=lambda item: item[0],
                default=(0.0, "Original", 1.0),
            )
            margin = best_alternative[0] - original_score

            version = "Unknown"
            if best_score >= 0.55 and tempo_label in {"Sped Up", "Slowed"}:
                version = tempo_label
            elif best_alternative[0] >= 0.82 and margin >= 0.010:
                version = best_alternative[1]
                best_score, best_label, best_rate = best_alternative
            elif original_score >= 0.82 and original_score >= best_alternative[0] + 0.015:
                version = "Original"
                best_score, best_label, best_rate = original_score, "Original", 1.0

            # A moderate original-leading match is useful, but should not be
            # presented as a verified Original. Close or alternative-leading
            # matches need review; weak/unusable matches remain Unknown without
            # creating review work.
            review_recommended = False
            if version == "Unknown":
                if (
                    original_score >= 0.68
                    and original_score >= best_alternative[0] + 0.005
                ):
                    version = "Original"
                    best_score, best_label, best_rate = original_score, "Original", 1.0
                elif max(original_score, best_alternative[0]) >= 0.68:
                    review_recommended = True

            evidence = (
                "Compared TikTok audio with the official preview "
                f"(best={best_label}@{best_rate:.2f}, score={best_score:.2f}, "
                f"original={original_score:.2f}, tempo_ratio={tempo_ratio:.2f})."
            )
            return {
                "audio_version": version,
                "audio_evidence": evidence,
                "similarity": round(float(best_score), 4),
                "original_score": round(float(original_score), 4),
                "alternative_score": round(float(best_alternative[0]), 4),
                "decision_margin": round(float(margin), 4),
                "review_recommended": review_recommended,
                "comparison_status": (
                    "review"
                    if review_recommended
                    else ("confident" if version != "Unknown" else "unusable")
                ),
            }
        except Exception as exc:
            return {
                "audio_version": "Unknown",
                "audio_evidence": f"Audio comparison failed: {exc}",
                "similarity": 0.0,
            }


def _metadata_audio_version(blob: str) -> str:
    text = _text(blob).casefold()
    if re.search(r"\b(?:sped\s*up|speed\s*up|nightcore|1\.[1-9]\d*\s*x)\b", text):
        return "Sped Up"
    if re.search(r"\b(?:slowed(?:\s*down)?|slow\s+version|0\.[1-9]\d*\s*x)\b", text):
        return "Slowed"
    if re.search(r"\b(?:remix|mashup|bootleg|flip|rework)\b", text):
        return "Remix"
    return "Unknown"


def resolve_audio_fields(response: Mapping, row=None, http_get=None) -> Dict[str, str]:
    """Combine Gemini observations, TikTok metadata and Apple/iTunes identity lookup."""
    music_name = _text(_row_get(row, "musicMeta.musicName"))
    music_author = _text(_row_get(row, "musicMeta.musicAuthor"))
    caption = _text(_row_get(row, "text"))
    campaign_track = _text(_row_get(row, "_campaign_track"))
    campaign_artist, campaign_song = split_campaign_track(campaign_track)
    verified_apple = response.get("_verified_itunes")
    apple = (
        dict(verified_apple)
        if isinstance(verified_apple, Mapping)
        else fetch_itunes_preview(campaign_track, http_get=http_get) if campaign_song else {}
    )

    model_detected = _text(response.get("detected_audio"))
    generic_metadata = bool(music_name) and _generic_audio_title(music_name)
    campaign_is_meaningful = bool(
        campaign_song
        and campaign_song.casefold() not in {"unknown", "not specified", "other", "n/a", "na"}
    )
    model_is_specific = bool(
        model_detected
        and model_detected.casefold() not in {"unknown", "not specified", "n/a", "na"}
        and not _generic_audio_title(model_detected)
    )
    used_campaign_display_fallback = False
    if generic_metadata and campaign_is_meaningful:
        if model_is_specific and _similar(model_detected, campaign_song):
            # Keep a cleaner localized title when it clearly describes the
            # same supplied campaign song (for example the Chinese half of a
            # bilingual Track value).
            detected = model_detected
        else:
            # The generic TikTok sound label is not useful to a marketing
            # user. Prefer the supplied campaign track over an unrelated
            # visual-model song guess, while leaving match/version
            # verification independent below.
            detected = campaign_song
            used_campaign_display_fallback = True
    elif generic_metadata and model_is_specific:
        detected = model_detected
    else:
        detected = music_name or model_detected or "Unknown"
    explicit_version = _metadata_audio_version(" ".join([music_name, music_author, caption]))
    # The drama pass receives image frames, not an audible waveform.  Therefore
    # it may use explicit TikTok metadata for speed/remix cues, but it must not
    # guess an audio version from the visual model response alone.
    version = explicit_version

    metadata_match = bool(
        campaign_song
        and not used_campaign_display_fallback
        and _similar(campaign_song, detected)
        and (not campaign_artist or not music_author or _similar(campaign_artist, music_author, threshold=0.66))
    )
    if metadata_match and apple:
        match = "Matched"
    elif campaign_song and music_name and apple:
        match = "Not Matched"
    else:
        match = _choice(response.get("campaign_song_match"), AUDIO_MATCHES)
        # A model-only match remains uncertain without corroborating metadata.
        if match == "Matched" and not metadata_match:
            match = "Unknown"

    official_title_match = bool(
        apple
        and music_name
        and _clean_title(music_name) == _clean_title(apple.get("track_name", ""))
        and _clean_title(campaign_song) == _clean_title(apple.get("track_name", ""))
    )
    official_artist_match = bool(
        not campaign_artist
        or not music_author
        or _similar(campaign_artist, music_author, threshold=0.66)
    )
    if version == "Unknown" and match == "Matched" and official_title_match and official_artist_match:
        # A clean, exact TikTok-title + Apple-title identity match with no speed,
        # slowed, remix or reverb cue is strong enough to call the official version.
        version = "Original"

    exact_metadata_title = bool(
        campaign_song
        and music_name
        and _clean_title(music_name) == _clean_title(campaign_song)
    )
    generic_creator_audio = bool(re.search(
        r"\boriginal\s+(?:sound|audio)\b",
        " ".join([music_name, music_author]).casefold(),
    ))
    if version == "Unknown" and exact_metadata_title and not generic_creator_audio:
        # Apple lookup can be unavailable or rate-limited. A clean exact TikTok
        # sound title with no speed/remix cue is still sufficient metadata for
        # Original. Generic creator "original sound" remains Unknown.
        version = "Original"

    return {
        "detected_audio": detected,
        "campaign_song_match": match,
        "audio_version": version,
        "itunes_track": " - ".join(filter(None, [apple.get("artist_name", ""), apple.get("track_name", "")])) if apple else "",
        "itunes_preview_url": apple.get("preview_url", "") if apple else "",
    }


def apply_audio_comparison(result: Dict, comparison: Mapping) -> Dict:
    """Apply a confident waveform result and rebuild the single details field."""
    output = dict(result or {})
    if not has_drama_label(output):
        return output
    compared_version = _choice(comparison.get("audio_version"), AUDIO_VERSIONS)
    existing_version = _choice(output.get("audio_version"), AUDIO_VERSIONS)
    # Explicit speed/remix metadata remains authoritative. Waveform comparison
    # is most valuable when metadata says Original or cannot identify a version.
    if (
        compared_version != "Unknown"
        and existing_version not in {"Sped Up", "Slowed", "Remix"}
    ):
        output["audio_version"] = compared_version
    if compared_version != "Unknown" and _generic_audio_title(output.get("detected_audio")):
        _official_artist, official_song = split_campaign_track(output.get("itunes_track", ""))
        if official_song:
            output["detected_audio"] = official_song
    output["audio_comparison_evidence"] = _text(comparison.get("audio_evidence"))
    output["audio_comparison_similarity"] = comparison.get("similarity", 0.0)
    output["audio_comparison_status"] = _text(
        comparison.get("comparison_status")
    ) or "unusable"
    output["audio_comparison_review_recommended"] = bool(
        comparison.get("review_recommended", False)
    )
    output["audio_comparison_original_score"] = comparison.get(
        "original_score", 0.0
    )
    output["audio_comparison_alternative_score"] = comparison.get(
        "alternative_score", 0.0
    )
    if output["audio_comparison_review_recommended"]:
        reason = "Audio comparison is close or contradictory and needs review"
        existing_reason = _text(output.get("drama_review_reason"))
        output["drama_review_reason"] = " | ".join(
            dict.fromkeys(part for part in [existing_reason, reason] if part)
        )
    fields = {
        "content_kind": output.get("content_kind"),
        "content_categories": output.get("content_categories"),
        "drama_type": _choice(output.get("drama_type"), DRAMA_TYPES),
        "edit_focus": _choice(output.get("edit_focus"), EDIT_FOCUS),
        "drama_format": _choice(
            output.get("drama_format"), FORMATS, DRAMA_FORMAT_ALIASES
        ),
        "country_region": _choice(output.get("country_region"), REGIONS),
        "drama_title": _text(output.get("drama_title")) or "Unknown",
        "detected_audio": _text(output.get("detected_audio")) or "Unknown",
        "audio_version": _choice(output.get("audio_version"), AUDIO_VERSIONS),
        "visual_summary": _text(output.get("visual_summary")),
    }
    output["content_details"] = _structured_details(
        output.get("content_details", ""), fields
    )
    return output


def apply_generic_original_audio_default(result: Dict, row=None) -> Dict:
    """Resolve generic TikTok creator audio after stronger checks have run.

    TikTok's localized ``original sound`` label is not proof that the audio is
    the requested campaign song, so Campaign Song Match remains independent.
    It is, however, a usable source-version label when no slowed, sped-up,
    remix, or contradictory waveform evidence exists.
    """
    output = dict(result or {})
    if (
        not has_drama_label(output)
        or _choice(output.get("audio_version"), AUDIO_VERSIONS) != "Unknown"
        or bool(output.get("audio_comparison_review_recommended", False))
    ):
        return output

    music_name = _text(_row_get(row, "musicMeta.musicName"))
    music_author = _text(_row_get(row, "musicMeta.musicAuthor"))
    detected_audio = _text(output.get("detected_audio"))
    metadata_blob = " ".join(filter(None, [music_name, music_author, detected_audio]))
    if _metadata_audio_version(metadata_blob) != "Unknown":
        return output
    if not (
        (music_name and _generic_audio_title(music_name))
        or (detected_audio and _generic_audio_title(detected_audio))
    ):
        return output

    output["audio_version"] = "Original"
    output["audio_version_basis"] = "generic-tiktok-original-sound-default"
    fields = {
        "content_kind": output.get("content_kind"),
        "content_categories": output.get("content_categories"),
        "drama_type": _choice(output.get("drama_type"), DRAMA_TYPES),
        "edit_focus": _choice(output.get("edit_focus"), EDIT_FOCUS),
        "drama_format": _choice(
            output.get("drama_format"), FORMATS, DRAMA_FORMAT_ALIASES
        ),
        "country_region": _choice(output.get("country_region"), REGIONS),
        "drama_title": _text(output.get("drama_title")) or "Unknown",
        "detected_audio": detected_audio or "Unknown",
        "audio_version": "Original",
        "visual_summary": _text(output.get("visual_summary")),
    }
    output["content_details"] = _structured_details(
        output.get("content_details", ""), fields
    )
    return output


def route_unknown_drama_audio_to_review(result: Dict, row=None) -> Dict:
    """Review only unresolved audio with a meaningful but ambiguous match."""
    output = dict(result or {})
    campaign_track = _text(_row_get(row, "_campaign_track"))
    if (
        not has_drama_label(output)
        or not campaign_track
        or campaign_track.casefold() in {"not specified", "unknown", "other"}
        or _choice(output.get("audio_version"), AUDIO_VERSIONS) != "Unknown"
        or not bool(output.get("audio_comparison_review_recommended", False))
    ):
        return output

    reason = "Drama audio comparison is close or contradictory and requires review"
    output["needs_human_review"] = True
    for field in ("drama_review_reason", "review_risk_reasons"):
        existing = [
            part.strip()
            for part in _text(output.get(field)).split("|")
            if part.strip()
        ]
        if reason not in existing:
            existing.append(reason)
        output[field] = " | ".join(existing)
    return output


def clear_resolved_drama_soft_review_flags(result: Dict) -> Dict:
    """Clear stale generic review flags after detailed drama evidence resolves them.

    The broad classifier runs before drama enrichment, so a low-confidence or
    generic-subtype flag can become obsolete once the scene-frame pass returns
    a supported detailed category.  Only those two soft flags are removable.
    Audio conflicts, verifier/guardrail contradictions, Thailand ambiguity,
    missing detailed evidence and routine QA audits are always preserved.
    """
    output = dict(result or {})
    if not has_drama_label(output):
        return output

    categories = _content_categories(
        output.get("content_categories") or output.get("content_kind")
    )
    region = _choice(output.get("country_region"), REGIONS)
    resolved = bool(categories and region != "Unknown")

    if "Drama Edit" in categories:
        resolved = resolved and all([
            _choice(output.get("drama_type"), DRAMA_TYPES) != "Unknown",
            _choice(output.get("edit_focus"), EDIT_FOCUS) != "Unknown",
            _choice(
                output.get("drama_format"), FORMATS, DRAMA_FORMAT_ALIASES
            ) != "Unknown",
        ])
    elif "CP Edit" in categories:
        resolved = resolved and _choice(
            output.get("edit_focus"), EDIT_FOCUS
        ) in {"CP Edit", "BL CP Edit", "GL CP Edit"}

    if not resolved:
        return output

    reasons = [
        part.strip()
        for part in _text(output.get("review_risk_reasons")).split("|")
        if part.strip()
    ]
    soft_prefixes = (
        "AI confidence below 80%",
        "Possible drama or entertainment subtype needs human confirmation",
    )
    cleared = [
        reason for reason in reasons
        if reason.startswith(soft_prefixes)
    ]
    if not cleared:
        return output

    remaining = [reason for reason in reasons if reason not in cleared]
    output["review_risk_reasons"] = " | ".join(remaining)
    output["needs_human_review"] = bool(remaining)
    output["_drama_soft_review_flags_cleared"] = cleared
    return output


def route_thailand_carousel_ambiguity_to_review(result: Dict, row=None) -> Dict:
    """Prevent contradictory entertainment carousels from auto-passing.

    Thailand samples often combine actor names, BL/GL hashtags, drama stills,
    rankings and informational text in the same slideshow.  Those cues are
    useful, but they do not always identify the post's primary purpose.  This
    guardrail keeps strong, internally consistent decisions automatic and
    sends contradictory or under-supported carousel subtypes to Review.

    The rule is evidence based: it never memorises creators, tracks or URLs.
    """
    output = dict(result or {})
    market = _text(
        _row_get(row, "_campaign_market")
        or _row_get(row, "Market")
        or _row_get(row, "market")
    ).casefold()
    thailand_scope = market in {"th", "tha", "thailand"}

    labels = set(_labels(output.get("creative_type")))
    details_text = _text(output.get("content_details"))
    categories = _content_categories(
        output.get("content_categories") or output.get("content_kind")
    )
    if not categories:
        match = re.search(
            r"content categor(?:y|ies):\s*([^\r\n]+)",
            details_text,
            flags=re.I,
        )
        if match:
            categories = _content_categories(match.group(1))

    blob = " ".join(filter(None, [
        _text(output.get("narrative")),
        details_text,
        _text(output.get("visual_summary")),
        _text(_row_get(row, "text")),
        _hashtags(row),
    ])).casefold()
    carousel_context = bool(
        "Carousel" in labels
        or bool(_row_get(row, "isSlideshow", False))
        or re.search(
            r"\b(?:carousel|slideshow|multi[- ]image|series of images|"
            r"multiple (?:photos?|images?|portraits?)|\d+[- ](?:image|slide))\b",
            blob,
        )
    )
    if not carousel_context:
        return output

    bts_support = bool(re.search(
        r"\b(?:behind[- ]the[- ]scenes|on set|filming|production footage|"
        r"rehearsal|camera crew|between takes?|bloopers?|outtakes?)\b",
        blob,
    ))
    # Explicit production evidence is a strong, distinct outcome and should
    # not be made ambiguous merely because the post also uses a carousel.
    if bts_support and "Behind-the-Scenes Edit" in categories:
        return output

    public_subject = bool(re.search(
        r"\b(?:actors?|actress(?:es)?|celebrit(?:y|ies)|idols?|stars?|"
        r"public figures?|cast members?)\b",
        blob,
    ))
    profile_look_support = _has_profile_look_purpose(blob)
    profile_support = bool(
        (public_subject or profile_look_support)
        and re.search(
            r"\b(?:ranking|ranked|net worth|richest|highest[- ]paid|top \d+|"
            r"career (?:journey|facts?|evolution)|profile|biograph(?:y|ies)|"
            r"portraits?|public appearances?|fashion editorial|spotlight|"
            r"look comparison|style comparison|costume comparison|"
            r"appearance comparison|transformation)\b",
            blob,
        )
    )
    fictional_support = bool(re.search(
        r"\b(?:fictional (?:characters?|story|scene)|drama (?:characters?|stills?|"
        r"scenes?|plot|storyline)|character (?:introduction|profiles?|cards?|"
        r"relationships?)|relationship map|plot points?|episode scenes?|"
        r"promotional stills?|historical dramas?|female leads?|male leads?)\b",
        blob,
    ))
    news_support = bool(
        _has_entertainment_news_purpose(blob)
        or re.search(
            r"\b(?:press conference|tutorial|how to|recipe|informational|"
            r"discussion|explainer)\b",
            blob,
        )
    )
    bl_marker = bool(re.search(
        r"(?:#(?:thai)?bl(?:series|drama|edit|cp)?\b|\bboys?[ '\u2019-]*love\b|"
        r"\bbl (?:drama|series|couple|cp|romance)\b)",
        blob,
    ))
    gl_marker = bool(re.search(
        r"(?:#(?:thai)?gl(?:series|drama|edit|cp)?\b|#girlslove\b|#yuri\b|"
        r"#girllovegirl\b|#girlxgirl\b|\bgirls?[ '\u2019-]*love\b|"
        r"\bgl (?:drama|series|couple|cp|romance)\b)",
        blob,
    ))
    pair_support = bool(re.search(
        r"\b(?:two (?:actors?|actresses|women|girls|men|boys|celebrities)|"
        r"both (?:actors?|actresses|women|girls|men|boys)|pair|couple|chemistry|"
        r"shipping|ship edit|affectionate|playful (?:interaction|moments?)|"
        r"interact(?:ing|ion) (?:together|with each other)|pose together|"
        r"friends day out|film themselves|heart gestures?|matching accessories)\b",
        blob,
    ))
    cp_support = bool((bl_marker or gl_marker) and pair_support and not fictional_support)

    selected = set(categories)
    conflicts: List[str] = []
    if thailand_scope and not selected and (
        public_subject
        or fictional_support
        or news_support
        or bl_marker
        or gl_marker
        or bool(labels & {DRAMA_LABEL, "Celebrity Edits", "Media/Infotainment"})
    ):
        conflicts.append("detailed subtype is missing")
    if thailand_scope and "Actor/Actress Carousel" in selected and not profile_support:
        conflicts.append("actor/profile purpose is not explicit")
    if thailand_scope and "Drama Carousel" in selected and not fictional_support:
        conflicts.append("fictional drama-carousel purpose is not explicit")
    if thailand_scope and "Entertainment News" in selected and not news_support:
        conflicts.append("informational or news purpose is not explicit")
    if thailand_scope and "CP Edit" in selected and not cp_support:
        conflicts.append("real-person BL/GL pair purpose is not explicit")

    # A stronger competing purpose is enough to require review.  This catches
    # actor rankings labelled as news and trope explainers labelled as drama
    # carousels without forcing either label automatically.
    if profile_support and selected and "Actor/Actress Carousel" not in selected:
        conflicts.append("actor/profile evidence conflicts with the selected subtype")
    if news_support and "Drama Carousel" in selected:
        conflicts.append("informational evidence conflicts with Drama Carousel")
    if cp_support and selected and "CP Edit" not in selected:
        conflicts.append("explicit BL/GL pair evidence conflicts with the selected subtype")
    if fictional_support and "Entertainment News" in selected and not news_support:
        conflicts.append("fictional drama evidence conflicts with Entertainment News")

    if not conflicts:
        return output

    scope = "Thailand carousel" if thailand_scope else "Entertainment carousel"
    reason = (
        f"{scope} subtype is ambiguous and requires human review: "
        + "; ".join(dict.fromkeys(conflicts))
    )
    output["needs_human_review"] = True
    for field in ("drama_review_reason", "review_risk_reasons"):
        existing = [
            part.strip()
            for part in _text(output.get(field)).split("|")
            if part.strip()
        ]
        if reason not in existing:
            existing.append(reason)
        output[field] = " | ".join(existing)
    return output


def _evidence_list(value) -> List[str]:
    values = value if isinstance(value, list) else [_text(value)]
    cleaned: List[str] = []
    for item in values:
        text = _text(item)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:5]


def _drama_subtype_evidence_blob(
    result: Mapping,
    response: Mapping,
    row,
    evidence: Iterable[str],
) -> str:
    """Collect model-observed subtype evidence without using campaign audio as story proof."""
    return " ".join(filter(None, [
        _text(result.get("narrative")),
        _text(result.get("content_details")),
        _text(response.get("visual_summary")),
        _text(response.get("review_reason")),
        " ".join(_text(item) for item in evidence if _text(item)),
        _text(_row_get(row, "text")),
        _hashtags(row),
    ])).casefold()


def _has_same_gender_romance_support(blob: str, subtype: str) -> bool:
    """Require explicit BL/GL relationship evidence before keeping the subtype."""
    if subtype == "BL":
        pattern = (
            r"(?:#(?:thai)?bl(?:series|drama|edit|cp)?\b|\bboys?[ '\u2019-]*love\b|"
            r"\bbl (?:drama|series|couple|cp|romance)\b|\bmale[- ]male\b|"
            r"\btwo (?:male(?: actors?| idols?| celebrities?)?|men|boys)\b|"
            r"\bboth (?:male|men)\b|"
            r"\b(?:gay|male) (?:couple|romance|pairing)\b)"
        )
    else:
        pattern = (
            r"(?:#(?:thai)?gl(?:series|drama|edit|cp)?\b|#girlslove\b|#yuri\b|"
            r"#girllovegirl\b|#girlxgirl\b|"
            r"\bgirls?[ '\u2019-]*love(?:[ '\u2019-]*girls?)?\b|"
            r"\bgl (?:drama|series|couple|cp|romance)\b|\bfemale[- ]female\b|"
            r"\btwo (?:female(?: actresses?| idols?| celebrities?)?|women|girls|"
            r"actress(?:es)?)\b|\bboth (?:female|women|actress(?:es)?)\b|"
            r"\bactresses\b.{0,160}\b(?:together|each other|paired?)\b|"
            r"\b(?:together|paired?)\b.{0,160}\bactresses\b|"
            r"\b(?:lesbian|female) (?:couple|romance|pairing)\b)"
        )
    return bool(re.search(pattern, blob, flags=re.I))


def _has_explicit_mixed_gender_romance(blob: str) -> bool:
    romance = re.search(
        r"\b(?:romantic|romance|couple|chemistry|kiss(?:ing)?|embrac(?:e|ing)|"
        r"foreheads? touching|holding hands|wedding|husband|wife|boyfriend|girlfriend)\b",
        blob,
    )
    if not romance:
        return False
    male = r"(?:\bman\b|\bmale\b|\bboy\b|\bhusband\b|\bgroom\b|\bboyfriend\b)"
    female = r"(?:\bwoman\b|\bfemale\b|\bgirl\b|\bwife\b|\bbride\b|\bgirlfriend\b)"
    return bool(
        re.search(rf"{male}.{{0,160}}{female}|{female}.{{0,160}}{male}", blob)
    )


def _explicit_region_from_visual_evidence(
    response: Mapping,
    evidence: Iterable[str],
    result: Optional[Mapping] = None,
    row=None,
) -> str:
    """Return one production region only when its content context is explicit.

    Second-pass evidence sometimes repeats weak campaign context such as the
    uploader market, caption language, hashtags or song language.  Those facts
    describe distribution, not where a drama/show was produced, so a bare
    country adjective must never override the model's structured region.
    """
    fragments = [
        _text(response.get("visual_summary")),
        _text((result or {}).get("narrative")),
        _text((result or {}).get("content_details")),
        *(_text(item) for item in evidence if _text(item)),
    ]
    patterns = {
        "Thailand": r"\b(?:thailand|thai)\b",
        "China": r"\b(?:china|chinese|c-drama)\b",
        "Taiwan": r"\b(?:taiwan|taiwanese)\b",
        "Hong Kong": r"\b(?:hong kong|hongkonger)\b",
        "Korea": r"\b(?:korea|korean|k-drama)\b",
        "Japan": r"\b(?:japan|japanese|j-drama)\b",
        "Malaysia": r"\b(?:malaysia|malaysian)\b",
        "Indonesia": r"\b(?:indonesia|indonesian)\b",
        "Philippines": r"\b(?:philippines|filipino|filipina)\b",
        "Singapore": r"\b(?:singapore|singaporean)\b",
        "Vietnam": r"\b(?:vietnam|vietnamese)\b",
        "United States": r"\b(?:united states|american|u\.s\.)\b",
        "United Kingdom": r"\b(?:united kingdom|british|u\.k\.)\b",
    }
    production_noun = (
        r"(?:drama|series|show|film|movie|production|television|tv|"
        r"web[- ]?series|soap opera|actors?|actresses|cast|cast members?|"
        r"celebrity|celebrities|idols?|"
        r"entertainment industry|production company|network|broadcaster|platform)"
    )

    matches = []
    for region, pattern in patterns.items():
        for raw_fragment in fragments:
            fragment = raw_fragment.casefold()
            region_match = re.search(pattern, fragment)
            if not region_match:
                continue

            # Require a direct production/person phrase.  This accepts
            # "Chinese drama", "Thai BL actors" and "series from Korea",
            # while rejecting "Thai song/caption/hashtags" even if a Chinese
            # drama is mentioned elsewhere in the same sentence.
            direct_context = bool(re.search(
                rf"(?:{pattern})\s+(?:[a-z0-9-]+\s+){{0,2}}{production_noun}\b|"
                rf"\b{production_noun}\s+(?:[a-z0-9-]+\s+){{0,2}}(?:from|of|in)\s+(?:{pattern})|"
                rf"\b(?:produced|production|origin|originates?|country of origin)"
                rf"\s+(?:is|in|from|of)?\s*(?:{pattern})",
                fragment,
                flags=re.I,
            ))
            if direct_context:
                matches.append(region)
                break

    # A source identity can provide supporting origin evidence when it names a
    # dedicated entertainment ecosystem (for example a China-entertainment or
    # C-drama publisher).  Generic creator location, campaign market and song
    # language remain excluded.
    source_identity = " ".join(filter(None, [
        _text(_row_get(row, "Creator")),
        _text(_row_get(row, "creator")),
        _text(_row_get(row, "authorMeta.name")),
        _text(_row_get(row, "authorMeta.uniqueId")),
    ])).casefold()
    normalized_source = re.sub(r"[_\-.]+", " ", source_identity)
    source_regions = {
        "China": r"\b(?:china|chinese)\s*(?:entertain(?:ment)?|drama|tv|series)\b|\bcdrama\b",
        "Korea": r"\b(?:korea|korean)\s*(?:entertain(?:ment)?|drama|tv|series)\b|\bkdrama\b",
        "Japan": r"\b(?:japan|japanese)\s*(?:entertain(?:ment)?|drama|tv|series)\b|\bjdrama\b",
        "Thailand": r"\b(?:thailand|thai)\s*(?:entertain(?:ment)?|drama|tv|series)\b",
    }
    for region, pattern in source_regions.items():
        if re.search(pattern, normalized_source):
            matches.append(region)

    matches = list(dict.fromkeys(matches))
    return matches[0] if len(matches) == 1 else ""


def _is_real_world_interview_or_discussion(
    result: Mapping,
    response: Mapping,
    evidence: Iterable[str],
) -> bool:
    """Recognise real-world actor interviews without trusting caption words alone.

    The row caption and hashtags are intentionally excluded: a fictional drama
    post can mention an "interview" or an actor in its metadata.  The override
    needs visual/model evidence of an interview/press structure, or the more
    specific combination of a real actor plus a meta-discussion about a drama
    and the broad Celebrity Edits signal.
    """
    observed_blob = " ".join(filter(None, [
        _text(result.get("narrative")),
        _text(result.get("content_details")),
        _text(response.get("visual_summary")),
        *(_text(item) for item in evidence if _text(item)),
    ])).casefold()
    broad_labels = {label.casefold() for label in _labels(result.get("creative_type"))}

    # Do not turn explicit negative evidence such as "no host or microphone"
    # into a positive match merely because it contains an interview keyword.
    structure_blob = re.sub(
        r"\b(?:no|not|without|lacks?|missing)\b"
        r"(?=[^.;]{0,100}\b(?:interview|press|q\s*&\s*a|talk[- ]show|reporter|host|"
        r"microphone|panel)\b)[^.;]{0,100}",
        " ",
        observed_blob,
    )

    interview_structure = bool(re.search(
        r"\b(?:interview(?:er|ee|ed|ing|s)?|press (?:q\s*&\s*a|conference|event|"
        r"junket|interview)|q\s*&\s*a|question[- ]and[- ]answer|talk[- ]show|"
        r"media scrum|reporter|host(?:ed|ing)?|panel discussion|answers? questions?|"
        r"(?:holding|speaking into|branded) (?:a )?microphone)\b",
        structure_blob,
    ))
    real_person = bool(re.search(
        r"\b(?:actor|actress|cast member|celebrity|entertainer|performer|idol|star)\b",
        observed_blob,
    ))
    discussion_cue = bool(
        re.search(
            r"\b(?:discuss(?:es|ed|ing|ion)?|talk(?:s|ed|ing)? about|comments? on|"
            r"explains?|reflect(?:s|ed|ing)? on|"
            r"shares? (?:his|her|their) (?:thoughts?|experience)|"
            r"shares? (?:an? )?(?:emotional )?experience)\b.{0,100}"
            r"\b(?:drama|show|series|role|character|episode|story|ending)\b",
            observed_blob,
        )
        or re.search(
            r"\b(?:drama|show|series|role|character|episode|story|ending)\b.{0,100}"
            r"\b(?:discussion|interview|comments?|explains?|thoughts?)\b",
            observed_blob,
        )
    )
    celebrity_signal = "celebrity edits" in broad_labels

    return bool(
        interview_structure and (real_person or celebrity_signal)
        or discussion_cue and real_person and celebrity_signal
    )


def _anime_visual_evidence(
    result: Mapping,
    response: Mapping,
    evidence: Iterable[str],
) -> tuple:
    """Return positive Anime and live-action evidence from visual analysis.

    Caption and hashtag metadata are deliberately excluded.  Those fields can
    be stale, promotional or unrelated to what is actually visible.  Negated
    phrases such as "not anime" are also removed before matching.
    """
    observed_blob = " ".join(filter(None, [
        _text(result.get("narrative")),
        _text(result.get("content_details")),
        _text(response.get("visual_summary")),
        *(_text(item) for item in evidence if _text(item)),
    ])).casefold()
    positive_blob = re.sub(
        r"\b(?:not|no|without|isn['’]?t|is not|doesn['’]?t show|does not show)\s+"
        r"(?:an?\s+)?(?:anime|manga|animated|animation|cartoon)\b",
        " ",
        observed_blob,
    )
    anime_support = bool(re.search(
        r"\b(?:anime(?:\s+(?:series|scene|character|characters|edit|style|footage))?|"
        r"manga(?:\s+(?:panel|panels|character|characters))?|animated\s+(?:scene|character|"
        r"characters|series|footage)|2d\s+(?:animation|character|characters)|cartoon\s+characters?)\b",
        positive_blob,
    ))
    live_action_support = bool(re.search(
        r"\b(?:live[- ]action|real[- ]life\s+(?:actor|actress|person|people)|"
        r"real\s+(?:human\s+)?(?:actor|actress|actors|people)|human\s+actors?|"
        r"soap opera|sinetron|television drama|tv drama|web drama|filmed\s+(?:actor|actress|"
        r"performer)|male and female lead|man and woman\s+in\s+(?:various|real|domestic|"
        r"outdoor|indoor)\s+(?:settings|locations|scenes))\b",
        positive_blob,
    ))
    return anime_support, live_action_support


def _readable_hashtag_title(value: str) -> str:
    token = _text(value).lstrip("#").replace("_", " ").strip()
    if not token:
        return ""
    token = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", token)
    token = re.sub(r"\s+", " ", token).strip(" -:;,.\"'")
    if not token:
        return ""
    return " ".join(word if any(ch.isupper() for ch in word[1:]) else word.capitalize() for word in token.split())


def _explicit_title_from_metadata(response: Mapping, row, evidence: Iterable[str]) -> str:
    """Recover a title only from an explicit title statement or corroboration."""
    caption = _text(_row_get(row, "text"))
    evidence_text = " ".join(filter(None, [
        _text(response.get("visual_summary")),
        *(_text(item) for item in evidence if _text(item)),
    ]))
    search_text = "\n".join(part for part in [caption, evidence_text] if part)
    patterns = (
        r"\b(?:drama|show|series|anime)\s+(?:title|name)\s*[:=\-]\s*([^#|;\n]{2,80})",
        r"\b(?:title|judul|tajuk)\s*[:=\-]\s*([^#|;\n]{2,80})",
        r"\b(?:drama|show|series|anime)\s+(?:is\s+)?(?:titled|called)\s+[\"']([^\"']{2,80})[\"']",
        r"\b(?:drama|show|series|anime)\s+title\s+(?:is\s+)?[\"']([^\"']{2,80})[\"']",
    )
    for pattern in patterns:
        match = re.search(pattern, search_text, flags=re.I)
        if match:
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" -:;,.\"'")
            if candidate.casefold() not in {"unknown", "not specified", "n/a", "none"}:
                return candidate

    raw_hashtags = _row_get(row, "hashtags", [])
    if not isinstance(raw_hashtags, list):
        raw_hashtags = re.findall(r"#([\w]+)", _text(raw_hashtags))
    names = [
        _text(item.get("name", "")) if isinstance(item, Mapping) else _text(item)
        for item in raw_hashtags
    ]
    generic = {
        "fyp", "foryou", "foryoupage", "viral", "edit", "edits", "drama", "cdrama",
        "kdrama", "jdrama", "sinetron", "series", "tv", "movie", "actor", "actress",
        "romance", "love", "anime", "manga",
    }
    for name in names:
        token = name.lstrip("#")
        if not token or token.casefold() in generic:
            continue
        corroborated = bool(
            re.search(
                rf"(?:title|name\s+of\s+(?:the\s+)?(?:drama|show|series|anime)).{{0,80}}#?{re.escape(token)}\b",
                evidence_text,
                flags=re.I,
            )
            or re.search(
                rf"#?{re.escape(token)}\b.{{0,80}}(?:identifies|names|confirms|is)\s+(?:the\s+)?(?:drama|show|series|anime)\s+title",
                evidence_text,
                flags=re.I,
            )
        )
        if corroborated:
            return _readable_hashtag_title(token)
    return ""


def _explicit_fictional_same_gender_drama_subtype(
    result: Mapping,
    response: Mapping,
    row,
    evidence: Iterable[str],
) -> str:
    """Return BL or GL only when metadata and visual story evidence agree.

    A hashtag by itself is not enough: real-world interviews, press clips and
    fan-service posts can also carry BL/GL tags.  Conversely, a BL/GL-series
    hashtag plus an observed fictional scene/montage is strong evidence that
    the detailed category is a drama edit rather than entertainment news.
    """
    metadata_blob = " ".join(filter(None, [
        _text(_row_get(row, "text")),
        _hashtags(row),
    ])).casefold()
    observed_blob = " ".join(filter(None, [
        _text(result.get("narrative")),
        _text(result.get("content_details")),
        _text(response.get("visual_summary")),
        *(_text(item) for item in evidence if _text(item)),
    ])).casefold()

    bl_marker = bool(re.search(
        r"(?:#(?:thai)?bl(?:series|drama|edit)?\b|\bboys?[ '\u2019-]*love\b|"
        r"\bbl (?:drama|series|romance)\b)",
        metadata_blob,
    ))
    gl_marker = bool(re.search(
        r"(?:#(?:thai)?gl(?:series|drama|edit)?\b|#girlslove\b|#yuri\b|"
        r"#girllovegirl\b|#girlxgirl\b|\bgirls?[ '\u2019-]*love\b|"
        r"\bgl (?:drama|series|romance)\b)",
        metadata_blob,
    ))
    drama_metadata = bool(re.search(
        r"(?:#(?:c|k|j|thai)?drama\b|#shortfilm\b|#shortdrama\b|"
        r"#microdrama\b|#webdrama\b|#series\b)",
        metadata_blob,
    ))
    fictional_visual = bool(re.search(
        r"\b(?:drama edit|fictional (?:scene|story|characters?)|scripted scene|"
        r"episode scene|storyline|romantic (?:drama )?scenes?|emotional scenes?|"
        r"scenes? from (?:a |the )?(?:drama|series|show|short film)|"
        r"montage.{0,100}(?:scenes?|characters?|leads?)|"
        r"(?:male|female) lead|drama characters?)\b",
        observed_blob,
    ))
    real_world_visual = bool(re.search(
        r"\b(?:interview|press (?:event|conference|q\s*&\s*a|junket)|"
        r"red carpet|premiere|talk[- ]show|panel discussion|reporter|host|"
        r"behind[- ]the[- ]scenes|on set|filming|rehearsal|fan ?meet|"
        r"off[- ]screen|public appearance)\b",
        observed_blob,
    ))

    if not drama_metadata or not fictional_visual or real_world_visual:
        return ""
    if bl_marker and not gl_marker:
        return "BL"
    if gl_marker and not bl_marker:
        return "GL"
    return ""


def _content_kinds(response: Mapping, result: Mapping, row, evidence: List[str]) -> List[str]:
    explicit = _content_categories(
        response.get("content_categories") or response.get("content_kind")
    )
    blob = " ".join([
        _text(result.get("_drama_content_kind_hint")),
        _text(result.get("narrative")),
        _text(result.get("content_details")),
        _text(response.get("visual_summary")),
        _text(_row_get(row, "text")),
        _hashtags(row),
        *evidence,
    ]).casefold()
    broad_labels = _labels(result.get("creative_type"))
    carousel_observed = bool(
        "Carousel" in broad_labels
        or re.search(
            r"\b(?:photo carousel|carousel|photo slideshow|slideshow|multi[- ]image|"
            r"series of (?:photos?|images)|multiple (?:photos?|images))\b",
            blob,
        )
    )
    fictional_carousel_evidence = bool(re.search(
        r"\b(?:drama (?:characters?|stills?|scenes?)|characters? (?:from|of|in) "
        r"(?:a |the )?(?:drama|series|show)|fictional characters?|in[- ]character|"
        r"character (?:introduction|introductions|profiles?|relationship map)|"
        r"plot (?:overview|summary|points?)|storyline (?:overview|summary)|"
        r"stills? (?:from|of) (?:a |the )?(?:drama|series|show)|"
        r"photos? of .{0,80} (?:drama|series) characters?)\b",
        blob,
    ))
    behind_scenes_evidence = bool(re.search(
        r"\b(?:behind[- ]the[- ]scenes|on set|filming|production|rehearsal|"
        r"wire rigging|camera crew|crew members?|takes? between scenes|bloopers?)\b",
        blob,
    ))
    cp_purpose_evidence = bool(re.search(
        r"\b(?:cp edit|bl cp|gl cp|ship(?:ping)? edit|fan ?service|"
        r"off[- ]screen chemistry|romantic chemistry|affectionate interaction|"
        r"feeding each other|holding hands|couple moments?|pair interaction)\b",
        blob,
    ))

    # Specific content purpose outranks the mere presence of actors or a
    # slideshow format. This keeps Thai CP/BTS posts out of generic carousel
    # buckets and separates real-person profiles from fictional drama slides.
    if "Behind-the-Scenes Edit" in explicit and "CP Edit" in explicit and not cp_purpose_evidence:
        explicit = [item for item in explicit if item != "CP Edit"]
    if carousel_observed and fictional_carousel_evidence:
        explicit = [
            item for item in explicit
            if item not in {
                "Actor/Actress Carousel", "Entertainment News", "Drama Edit"
            }
        ]
        if "Drama Carousel" not in explicit:
            explicit.insert(0, "Drama Carousel")
    fictional_same_gender_subtype = _explicit_fictional_same_gender_drama_subtype(
        result,
        response,
        row,
        evidence,
    )
    if (
        fictional_same_gender_subtype
        and "Drama Carousel" not in explicit
        and "Behind-the-Scenes Edit" not in explicit
    ):
        # The model sometimes mistakes a fictional BL/GL montage for real-world
        # entertainment coverage.  Agreement between explicit series metadata
        # and observed fictional scenes is strong enough to correct it.
        return ["Drama Edit"]
    anime_support, live_action_support = _anime_visual_evidence(result, response, evidence)
    if anime_support and not live_action_support:
        return ["Anime Edit"]
    if "Anime Edit" in explicit and live_action_support and not anime_support:
        # A weak Anime suggestion cannot overrule explicit live-action people,
        # soap-opera or filmed-actor evidence.  Removing it lets the confirmed
        # drama-family fallback resolve to Drama Edit below.
        explicit = [item for item in explicit if item != "Anime Edit"]
    content_hint = _text(result.get("_drama_content_kind_hint"))
    # Re-check purpose after the scene-frame pass. The broad pass cannot see
    # second-pass observations such as a release schedule or a real-actress
    # look comparison, so those strong cues must be able to correct an unsafe
    # generic Drama Carousel proposal.
    observed_purpose_blob = " ".join(filter(None, [
        _text(result.get("narrative")),
        _text(result.get("content_details")),
        _text(response.get("visual_summary")),
        *(_text(item) for item in evidence if _text(item)),
    ])).casefold()
    observed_fictional_scene = _has_observed_fictional_scene_purpose(
        observed_purpose_blob
    )
    observed_real_world_news = bool(
        _has_observed_real_world_news_purpose(observed_purpose_blob)
        or _is_real_world_interview_or_discussion(result, response, evidence)
    )
    second_pass_news = _has_entertainment_news_purpose(observed_purpose_blob)
    second_pass_profile = bool(
        carousel_observed
        and _has_profile_look_purpose(observed_purpose_blob)
        and not fictional_carousel_evidence
    )
    specific_hint = content_hint in {
        "CP Edit", "Behind-the-Scenes Edit", "K-pop Show Cut",
        "Actor/Actress Daily Vlog", "Anime Edit",
    }
    if (
        observed_fictional_scene
        and not observed_real_world_news
        and not (carousel_observed and fictional_carousel_evidence)
    ):
        # A model-proposed Entertainment News label cannot overrule direct
        # visual evidence of a fictional scene montage. Caption/hashtag words
        # are deliberately excluded from this correction.
        explicit = [
            item for item in explicit
            if item not in {"Entertainment News", "Actor/Actress Carousel"}
        ]
        if "Drama Edit" not in explicit:
            explicit.insert(0, "Drama Edit")
        content_hint = "Drama Edit"
    elif second_pass_profile and not specific_hint:
        content_hint = "Actor/Actress Carousel"
    elif (
        (second_pass_news or observed_real_world_news)
        and not fictional_carousel_evidence
        and not specific_hint
    ):
        content_hint = "Entertainment News"
    if content_hint in CONTENT_KINDS:
        if content_hint == "K-pop Show Cut":
            # K-pop Show Cut is the specific subtype; do not keep the broader
            # Entertainment News label merely because the model used it first.
            explicit = [item for item in explicit if item != "Entertainment News"]
        elif content_hint == "Actor/Actress Daily Vlog":
            # The daily-vlog subtype is more specific than a generic drama or
            # entertainment-news label. A true carousel can still remain as a
            # second, separate format category.
            explicit = [
                item
                for item in explicit
                if item not in {"Drama Edit", "Entertainment News"}
            ]
        elif content_hint == "CP Edit":
            # The broad drama label is only a router.  Explicit real-person
            # chemistry is the more precise detailed category; preserve a
            # genuinely separate purpose such as Entertainment News.
            explicit = [
                item for item in explicit
                if item not in {"Drama Edit", "Actor/Actress Carousel"}
            ]
        elif content_hint == "Actor/Actress Carousel":
            # This is a real-public-figure photo/slideshow format, not a
            # fictional Drama Carousel or generic Drama Edit.
            explicit = [
                item
                for item in explicit
                if item not in {
                    "Drama Edit", "Drama Carousel", "Entertainment News", "CP Edit"
                }
            ]
        elif content_hint == "Entertainment News":
            # A real-world interview, recommendation, trope explainer or
            # industry update is not a fictional drama/character carousel.
            # Keep a second category only when the evidence independently
            # supports it (for example, an explicit actor comparison carousel).
            explicit = [
                item
                for item in explicit
                if item not in {"Drama Edit", "Drama Carousel"}
                and not (item == "CP Edit" and not cp_purpose_evidence)
            ]
        if content_hint not in explicit:
            explicit.insert(0, content_hint)
        return explicit[:2]
    if _is_real_world_interview_or_discussion(result, response, evidence):
        # The broad Movie/Tv/Drama Edits label is the routing umbrella.  At the
        # detailed level, a real actor interview is Entertainment News rather
        # than a fictional Drama Edit.  Preserve a genuinely separate second
        # purpose such as CP Edit, but remove the contradicted Drama Edit.
        corrected = [item for item in explicit if item != "Drama Edit"]
        if "Entertainment News" not in corrected:
            corrected.insert(0, "Entertainment News")
        return corrected[:2]
    if explicit:
        return explicit
    if re.search(
        r"\b(?:entertainment news|editorial|magazine|zine|actor comparison|"
        r"compares? (?:the )?(?:actor|actress|cast)|casting news|interview|"
        r"press event|red carpet|premiere|fashion media|celebrity news)\b",
        blob,
    ):
        return ["Entertainment News"]
    return ["Drama Edit"]


def _resolve_drama_format(
    value,
    categories,
    evidence_blob: str = "",
    region: str = "Unknown",
    drama_title: str = "",
) -> str:
    """Return a usable production format without leaking Unknown as N/A.

    Production format applies only to a real ``Drama Edit``.  Short-form Drama
    needs positive evidence; otherwise the product uses Long-form as
    its explicit operational default.  This avoids presenting a failed
    detection for Entertainment News, K-pop Show Cut, Daily Vlog, Anime, etc.
    """
    category_set = set(_content_categories(categories))
    if "Drama Edit" not in category_set:
        return "Not applicable"

    selected = _choice(value, FORMATS, DRAMA_FORMAT_ALIASES)
    blob = _text(evidence_blob).casefold()
    micro_cue = bool(re.search(
        r"\b(?:micro[- ]?drama|mini[- ]?drama|vertical drama|vertical series|"
        r"short[- ]?drama|short[- ]?form drama|short web drama)\b",
        blob,
    ))
    reviewed_short_title = _clean_title(drama_title) in KNOWN_SHORT_FORM_DRAMA_TITLES
    # Strong reviewed title/format evidence outranks a model-selected Long-form
    # value. This avoids repeating an incorrect model guess across every post
    # from a known short-form production.
    if micro_cue or reviewed_short_title:
        return "Short-form Drama"
    if selected == "Short-form Drama":
        return selected
    if selected == "Long-form Drama":
        return selected
    return "Long-form Drama"


def _structured_details(base_details: str, fields: Mapping[str, str]) -> str:
    categories = _content_categories(
        fields.get("content_categories") or fields.get("content_kind")
    ) or ["Drama Edit"]
    kind = categories[0]
    visual = _text(fields.get("visual_summary")) or _text(base_details) or "Drama-related post detected."
    lines = [
        f"Visual Summary: {visual}",
        f"Content Category: {', '.join(categories)}",
    ]
    # Entertainment News is a real-world reporting/interview route. When it is
    # selected alongside an older secondary suggestion (for example CP Edit),
    # it remains the controlling review mode and must not expose or export
    # fictional-drama fields.
    if "Entertainment News" in categories:
        lines.append(f"Country/Region: {fields['country_region']}")
    elif "Drama Edit" in categories:
        lines.extend([
            f"Drama Type: {fields['drama_type']}",
            f"Edit Focus: {fields['edit_focus']}",
            f"Format: {fields['drama_format']}",
            f"Country/Region: {fields['country_region']}",
            f"Drama Title: {fields['drama_title']}",
        ])
    elif "CP Edit" in categories:
        lines.extend([
            f"Drama Type: {fields['drama_type']}",
            f"Edit Focus: {fields['edit_focus']}",
            f"Country/Region: {fields['country_region']}",
            f"Drama Title: {fields['drama_title']}",
        ])
    elif kind == "Anime Edit":
        lines.extend([
            f"Country/Region: {fields['country_region']}",
            f"Anime Title: {fields['drama_title']}",
        ])
    elif kind in {"Drama Carousel", "Behind-the-Scenes Edit"}:
        lines.extend([
            f"Country/Region: {fields['country_region']}",
            f"Drama Title: {fields['drama_title']}",
        ])
    else:
        lines.append(f"Country/Region: {fields['country_region']}")
    lines.extend([
        f"Detected Audio: {fields['detected_audio']}",
        f"Audio Version: {fields['audio_version']}",
    ])
    return "\n".join(lines)


def parse_structured_details(value: str) -> Dict[str, str]:
    """Read line-by-line drama details from current or older Content Details."""
    parsed: Dict[str, str] = {}
    labels = {
        "visual summary": "visual_summary",
        "content category": "content_kind",
        "drama type": "drama_type",
        "edit focus": "edit_focus",
        "format": "drama_format",
        "country/region": "country_region",
        "drama title": "drama_title",
        "anime title": "drama_title",
        "detected audio": "detected_audio",
        "audio version": "audio_version",
    }
    for line in _text(value).splitlines():
        if ":" not in line:
            continue
        label, content = line.split(":", 1)
        key = labels.get(label.strip().casefold())
        if key and _text(content):
            parsed[key] = _text(content)
    return parsed


def drama_review_defaults(row: Mapping) -> Dict[str, str]:
    """Return validated field defaults for the conditional human-review form."""
    parsed = parse_structured_details(_row_get(row, "Content Details"))
    detected_audio = (
        _row_get(row, "detected_audio")
        or _row_get(row, "Detected Audio")
        or parsed.get("detected_audio")
        or "Unknown"
    )
    campaign_song = _review_campaign_song(row)
    if campaign_song and (
        _text(detected_audio).casefold() in {"", "unknown", "not specified", "n/a", "na"}
        or _generic_audio_title(detected_audio)
    ):
        detected_audio = campaign_song
    raw = {
        "visual_summary": _row_get(row, "visual_summary") or parsed.get("visual_summary") or _text(_row_get(row, "Content Details")),
        # Review must show the validated/exported values. Raw lowercase fields
        # can still contain the pre-guardrail Gemini proposal.
        "content_categories": _row_get(row, "Drama Content Category") or _row_get(row, "content_categories") or _row_get(row, "content_kind") or parsed.get("content_kind") or "Drama Edit",
        "drama_type": _row_get(row, "Drama Type") or _row_get(row, "drama_type") or parsed.get("drama_type") or "Unknown",
        "edit_focus": _row_get(row, "Drama Edit Focus") or _row_get(row, "edit_focus") or parsed.get("edit_focus") or "Unknown",
        "drama_format": _row_get(row, "Drama Format") or _row_get(row, "drama_format") or parsed.get("drama_format") or "Unknown",
        "country_region": _row_get(row, "Drama Country/Region") or _row_get(row, "country_region") or parsed.get("country_region") or "Unknown",
        "drama_title": _row_get(row, "Drama Title") or _row_get(row, "drama_title") or parsed.get("drama_title") or "Unknown",
        "detected_audio": detected_audio,
        "campaign_song_match": _row_get(row, "campaign_song_match") or _row_get(row, "Campaign Song Match") or parsed.get("campaign_song_match") or "Unknown",
        "audio_version": _row_get(row, "Audio Version") or _row_get(row, "audio_version") or parsed.get("audio_version") or "Unknown",
    }
    categories = _content_categories(raw["content_categories"]) or ["Drama Edit"]
    region = _choice(raw["country_region"], REGIONS)
    drama_format = _resolve_drama_format(
        raw["drama_format"],
        categories,
        evidence_blob=" ".join([
            _text(raw["visual_summary"]),
            _text(_row_get(row, "Content Details")),
            _text(_row_get(row, "Narrative")),
            _text(_row_get(row, "Caption")),
        ]),
        region=region,
        drama_title=raw["drama_title"],
    )
    return {
        "visual_summary": _text(raw["visual_summary"]) or "Drama-related post detected.",
        "content_categories": categories,
        "drama_type": _choice(raw["drama_type"], DRAMA_TYPES),
        "edit_focus": _choice(raw["edit_focus"], EDIT_FOCUS),
        "drama_format": drama_format,
        "country_region": region,
        "drama_title": _text(raw["drama_title"]) or "Unknown",
        "detected_audio": _text(raw["detected_audio"]) or "Unknown",
        "campaign_song_match": _choice(raw["campaign_song_match"], AUDIO_MATCHES),
        "audio_version": _choice(raw["audio_version"], AUDIO_VERSIONS),
    }


def build_review_drama_updates(values: Mapping) -> Dict[str, str]:
    """Build consistent internal fields and Content Details from human edits."""
    defaults = drama_review_defaults(values)
    categories = defaults["content_categories"]
    kind = categories[0]
    entertainment_news_mode = "Entertainment News" in categories
    if entertainment_news_mode or (
        "Drama Edit" not in categories and "CP Edit" not in categories
    ):
        defaults["drama_type"] = "Unknown"
        defaults["edit_focus"] = "Unknown"
    if entertainment_news_mode:
        defaults["drama_format"] = "Not applicable"
        defaults["drama_title"] = "Unknown"
    cp_only_mode = (
        not entertainment_news_mode
        and "CP Edit" in categories
        and "Drama Edit" not in categories
    )
    if cp_only_mode:
        # CP Edit already records the representation in Edit Focus. Derive the
        # hidden internal type so a stale UI value such as General Drama cannot
        # leak into Content Details or QA exports.
        defaults["drama_type"] = {
            "BL CP Edit": "BL Drama",
            "GL CP Edit": "GL Drama",
        }.get(defaults["edit_focus"], "Unknown")
    defaults["drama_format"] = _resolve_drama_format(
        defaults["drama_format"],
        categories,
        evidence_blob=defaults["visual_summary"],
        region=defaults["country_region"],
        drama_title=defaults["drama_title"],
    )
    if entertainment_news_mode or not set(categories) & {
        "Drama Edit", "CP Edit", "Anime Edit", "Drama Carousel",
        "Behind-the-Scenes Edit",
    }:
        defaults["drama_title"] = "Unknown"
    result = {
        "creative_type": [DRAMA_LABEL],
        **defaults,
        "content_details": _structured_details("", defaults),
        "drama_evidence": [],
        "drama_review_reason": "",
    }
    return {"Content Details": result["content_details"], **drama_export_values(result)}


def apply_drama_enrichment(result: Dict, response: Mapping, row=None, http_get=None) -> Dict:
    """Attach structured drama fields while preserving the broad label result."""
    output = dict(result)
    if not has_drama_label(output):
        return output

    response = dict(response or {})
    drama_type = _choice(response.get("drama_type"), DRAMA_TYPES, {
        "bl": "BL Drama", "boys love": "BL Drama",
        "gl": "GL Drama", "girls love": "GL Drama",
        "general": "General Drama", "drama": "General Drama",
    })
    edit_focus = _choice(response.get("edit_focus"), EDIT_FOCUS, {
        "bl cp": "BL CP Edit", "bl cp edits": "BL CP Edit",
        "gl cp": "GL CP Edit", "gl cp edits": "GL CP Edit",
        "actor edit": "Cast/Actor Edit", "cast edit": "Cast/Actor Edit",
        "scene edit": "Fictional Story", "story": "Fictional Story",
    })
    proposed_drama_format = _choice(
        response.get("drama_format"), FORMATS, DRAMA_FORMAT_ALIASES
    )
    region = _choice(response.get("country_region"), REGIONS, {
        "thai": "Thailand", "chinese": "China", "korean": "Korea",
        "japanese": "Japan", "malaysian": "Malaysia", "indonesian": "Indonesia",
        "filipino": "Philippines", "vietnamese": "Vietnam",
    })
    evidence = _evidence_list(response.get("evidence"))
    title = _text(response.get("drama_title")) or "Unknown"
    if title.casefold() in {"n/a", "na", "none", "not sure", "unknown title"}:
        title = "Unknown"
    if title == "Unknown":
        title = _explicit_title_from_metadata(response, row, evidence) or "Unknown"

    content_categories = _content_kinds(response, output, row, evidence)
    content_kind = content_categories[0]
    guardrail_review_reasons: List[str] = []
    proposed_categories = _content_categories(
        response.get("content_categories") or response.get("content_kind")
    )
    anime_support, live_action_support = _anime_visual_evidence(output, response, evidence)
    if "Anime Edit" in proposed_categories and live_action_support and not anime_support:
        guardrail_review_reasons.append(
            "Anime suggestion contradicted explicit live-action or soap-opera evidence"
        )
    explicit_region = _explicit_region_from_visual_evidence(
        response,
        evidence,
        result=output,
        row=row,
    )
    if explicit_region and region != explicit_region:
        guardrail_review_reasons.append(
            f"Region suggestion {region} contradicted explicit {explicit_region} visual evidence"
        )
        region = explicit_region
    format_evidence = " ".join([
        _text(output.get("narrative")),
        _text(output.get("content_details")),
        _text(response.get("visual_summary")),
        _text(response.get("review_reason")),
        _text(_row_get(row, "text")),
        _hashtags(row),
        title,
        *evidence,
    ]).casefold()
    drama_format = _resolve_drama_format(
        proposed_drama_format,
        content_categories,
        evidence_blob=format_evidence,
        region=region,
        drama_title=title,
    )

    if "Drama Edit" not in content_categories and "CP Edit" not in content_categories:
        drama_type = "Unknown"
        edit_focus = "Unknown"

    # CP focus and fictional-story focus are intentionally mutually exclusive.
    review_reasons = list(guardrail_review_reasons)
    if edit_focus in {"BL CP Edit", "GL CP Edit"} and drama_type == "Unknown":
        drama_type = "BL Drama" if edit_focus == "BL CP Edit" else "GL Drama"
    if edit_focus == "Fictional Story" and drama_type == "Unknown":
        drama_type = "General Drama"
    if edit_focus in {"BL CP Edit", "GL CP Edit"} and re.search(
        r"\b(?:fictional|characters?|scene|episode|storyline)\b",
        " ".join(evidence).casefold(),
    ) and not re.search(
        r"\b(?:actors?|fanmeet|interview|behind[- ]the[- ]scenes|bts|event|off[- ]screen)\b",
        " ".join(evidence).casefold(),
    ):
        edit_focus = "Fictional Story"
        review_reasons.append("CP suggestion lacked real-actor or off-screen evidence")

    subtype_blob = _drama_subtype_evidence_blob(output, response, row, evidence)
    fictional_same_gender_subtype = _explicit_fictional_same_gender_drama_subtype(
        output,
        response,
        row,
        evidence,
    )
    if "Drama Edit" in content_categories and fictional_same_gender_subtype:
        drama_type = (
            "BL Drama"
            if fictional_same_gender_subtype == "BL"
            else "GL Drama"
        )
        edit_focus = "Fictional Story"
    elif (
        "Drama Edit" in content_categories
        and _has_observed_fictional_scene_purpose(subtype_blob)
    ):
        # When the detailed model initially called a scene montage News, its
        # drama-only fields are often blank. Populate the safe general values
        # from the same direct fictional-scene evidence used for correction.
        if drama_type == "Unknown":
            drama_type = "General Drama"
        if edit_focus == "Unknown":
            edit_focus = "Fictional Story"
    if "CP Edit" in content_categories:
        real_person_context = bool(re.search(
            r"\b(?:actors?|actress(?:es)?|celebrit(?:y|ies)|idols?|public figures?|"
            r"fan ?meet|interview|press event|behind[- ]the[- ]scenes|backstage|"
            r"variety show|off[- ]screen|promotional (?:event|appearance)|on stage|"
            r"(?:at|to) (?:the )?camera|selfie|two (?:women|girls|men|boys)|"
            r"casual (?:indoor )?(?:setting|environment)|close[- ]up (?:playful )?shots?)\b",
            subtype_blob,
        ))
        explicit_bl_marker = bool(re.search(
            r"(?:#(?:thai)?bl(?:series|drama|edit|cp)?\b|\bboys?[ '\u2019-]*love\b|"
            r"\bbl (?:drama|series|couple|cp|romance)\b)",
            subtype_blob,
        ))
        explicit_gl_marker = bool(re.search(
            r"(?:#(?:thai)?gl(?:series|drama|edit|cp)?\b|#girlslove\b|#yuri\b|"
            r"#girllovegirl\b|#girlxgirl\b|"
            r"\bgirls?[ '\u2019-]*love(?:[ '\u2019-]*girls?)?\b|"
            r"\bgl (?:drama|series|couple|cp|romance)\b)",
            subtype_blob,
        ))
        pair_interaction_context = bool(re.search(
            r"\b(?:fan ?service|feeding each other|interact(?:ing|ion) with each other|"
            r"playful (?:interaction|shots?|poses?|moments?)|affectionate interaction|"
            r"heart gestures?|make hearts?|hearts? (?:at|to) (?:the )?camera|"
            r"cute (?:gestures?|poses?)|"
            r"pose together|(?:eat|eating|enjoy(?:ing)?) .{0,60} together|"
            r"paired? promotion|promot(?:e|ing) their .{0,50}appearance|"
            r"promotional (?:event|appearance)|"
            r"on stage|appear(?:ing|ance) together)\b",
            subtype_blob,
        ))
        romance_context = bool(re.search(
            r"\b(?:romantic(?:ally)?|romance|couple|chemistry|shipping|ship edit|"
            r"affection(?:ate|ately|ion)?|flirt(?:ing|atious)?|cuddl(?:e|ing)|"
            r"embrac(?:e|ing)|holding hands|off[- ]screen romance)\b",
            subtype_blob,
        )) or pair_interaction_context
        explicit_bl_pair = bool(re.search(
            r"\b(?:male[- ]male|two (?:male(?: actors?| idols?| celebrities?)?|"
            r"men|boys)|both (?:male|men)|"
            r"male (?:couple|romance|pairing))\b",
            subtype_blob,
        )) or explicit_bl_marker
        explicit_gl_pair = bool(re.search(
            r"\b(?:female[- ]female|two (?:female(?: actresses?| idols?|"
            r" celebrities?)?|women|girls|actress(?:es)?)|"
            r"both (?:female|women|actress(?:es)?)|"
            r"female (?:couple|romance|pairing)|"
            r"actresses\b.{0,160}\b(?:together|each other|paired?)|"
            r"(?:together|paired?)\b.{0,160}\bactresses)\b",
            subtype_blob,
        )) or explicit_gl_marker
        fictional_context = bool(re.search(
            r"\b(?:fictional (?:characters?|story|scene)|scripted (?:scene|episode)|"
            r"episode scene|storyline|characters? in (?:a |the )?(?:drama|series|movie))\b",
            subtype_blob,
        ))
        offscreen_context = bool(re.search(
            r"\b(?:fan ?meet|interview|press event|behind[- ]the[- ]scenes|backstage|"
            r"variety show|off[- ]screen|promotional (?:event|appearance)|on stage|"
            r"(?:at|to) (?:the )?camera|selfie|casual (?:indoor )?"
            r"(?:setting|environment)|close[- ]up (?:playful )?shots?)\b",
            subtype_blob,
        ))
        can_resolve_cp_subtype = bool(
            real_person_context
            and romance_context
            and not (fictional_context and not offscreen_context)
        )
        if can_resolve_cp_subtype and explicit_bl_pair and not explicit_gl_pair:
            drama_type = "BL Drama"
            edit_focus = "BL CP Edit"
        elif can_resolve_cp_subtype and explicit_gl_pair and not explicit_bl_pair:
            drama_type = "GL Drama"
            edit_focus = "GL CP Edit"

    subtype = (
        "BL" if drama_type == "BL Drama" or edit_focus == "BL CP Edit"
        else "GL" if drama_type == "GL Drama" or edit_focus == "GL CP Edit"
        else ""
    )
    if subtype and not _has_same_gender_romance_support(subtype_blob, subtype):
        mixed_gender = _has_explicit_mixed_gender_romance(subtype_blob)
        reason = (
            f"{subtype} suggestion contradicted an explicit male-female romantic pairing"
            if mixed_gender
            else f"{subtype} suggestion lacked explicit same-gender romantic evidence"
        )
        guardrail_review_reasons.append(reason)
        review_reasons.append(reason)
        drama_type = "General Drama"
        if edit_focus in {"BL CP Edit", "GL CP Edit"}:
            if "CP Edit" in content_categories:
                edit_focus = "Cast/Actor Edit"
            elif re.search(r"\b(?:fictional|characters?|scene|episode|storyline)\b", subtype_blob):
                edit_focus = "Fictional Story"
            else:
                edit_focus = "General Drama Edit"

    audio = resolve_audio_fields(response, row, http_get=http_get)
    model_review = _text(response.get("review_reason"))
    if model_review:
        review_reasons.append(model_review)
    if set(content_categories) & {"Drama Edit", "CP Edit"} and (drama_type == "Unknown" or edit_focus == "Unknown"):
        reason = "Drama subtype or edit focus remains uncertain"
        review_reasons.append(reason)
        if "CP Edit" in content_categories:
            guardrail_review_reasons.append(reason)
    if region == "Unknown":
        review_reasons.append("Production country/region is not confirmed")

    fields = {
        "content_kind": content_kind,
        "content_categories": content_categories,
        "drama_type": drama_type,
        "edit_focus": edit_focus,
        "drama_format": drama_format,
        "country_region": region,
        "drama_title": title,
        "detected_audio": audio["detected_audio"],
        "campaign_song_match": audio["campaign_song_match"],
        "audio_version": audio["audio_version"],
        "visual_summary": _text(response.get("visual_summary")),
    }
    output.update(fields)
    if drama_format == "Not applicable":
        output["drama_format_basis"] = "not-applicable-to-content-category"
    elif proposed_drama_format in DRAMA_FORMAT_CHOICES:
        output["drama_format_basis"] = "model-or-explicit-evidence"
    else:
        output["drama_format_basis"] = "operational-default-or-evidence-fallback"
    output["drama_evidence"] = evidence
    output["drama_review_reason"] = " | ".join(dict.fromkeys(review_reasons))
    if guardrail_review_reasons:
        output["needs_human_review"] = True
        existing_risks = [
            part.strip()
            for part in _text(output.get("review_risk_reasons")).split("|")
            if part.strip()
        ]
        output["review_risk_reasons"] = " | ".join(dict.fromkeys(
            existing_risks + guardrail_review_reasons
        ))
    output["itunes_track"] = audio["itunes_track"]
    output["itunes_preview_url"] = audio["itunes_preview_url"]
    output["content_details"] = _structured_details(output.get("content_details", ""), fields)
    return output


def drama_export_values(result: Mapping) -> Dict[str, str]:
    """Map backend field names to clear marketing/QA export headers."""
    if not has_drama_label(result):
        return {column: "" for column in DRAMA_EXPORT_COLUMNS}
    evidence = result.get("drama_evidence", [])
    if isinstance(evidence, str):
        evidence_text = evidence
    else:
        evidence_text = " | ".join(_evidence_list(evidence))
    categories = _content_categories(
        result.get("content_categories") or result.get("content_kind")
    )
    entertainment_news_mode = "Entertainment News" in categories
    export_format = _resolve_drama_format(
        result.get("drama_format"),
        categories,
        evidence_blob=" ".join([
            _text(result.get("visual_summary")),
            _text(result.get("content_details")),
            _text(result.get("narrative")),
        ]),
        region=_choice(result.get("country_region"), REGIONS),
        drama_title=_text(result.get("drama_title")),
    )
    return {
        "Drama Content Category": ", ".join(categories),
        "Drama Type": "" if entertainment_news_mode else _text(result.get("drama_type")),
        "Drama Edit Focus": "" if entertainment_news_mode else _text(result.get("edit_focus")),
        # Blank means the field does not apply. It must not look like a failed
        # detection on Entertainment News, K-pop Show Cut, Daily Vlog, Anime,
        # or other non-drama categories.
        "Drama Format": (
            export_format
            if "Drama Edit" in categories and not entertainment_news_mode
            else ""
        ),
        "Drama Country/Region": _text(result.get("country_region")),
        "Drama Title": "" if entertainment_news_mode else _text(result.get("drama_title")),
        "Detected Audio": _text(result.get("detected_audio")),
        "Audio Version": _text(result.get("audio_version")),
        "Drama Evidence": evidence_text,
        "Drama Review Reason": _text(result.get("drama_review_reason")),
    }


def response_from_json_text(text: str) -> Dict:
    """Parse Gemini's raw JSON response defensively for tests and runtime."""
    cleaned = re.sub(r"^```json\s*", "", _text(text), flags=re.I)
    cleaned = re.sub(r"```$", "", cleaned).strip()
    parsed = json.loads(cleaned)
    return dict(parsed) if isinstance(parsed, Mapping) else {}
