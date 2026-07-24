"""General review-risk routing for Creative Type classification.

The rules use reusable evidence and deterministic QA sampling. They do not use
exact TikTok URL-to-label memory or market/track-specific expected answers.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Tuple


LOW_CONFIDENCE_REVIEW = 0.80
QA_AUDIT_PERCENT = 5


# -----------------------------------------------------------------------------
# Reusable evidence and post-structure helpers
# -----------------------------------------------------------------------------


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _get(row, key, default=""):
    try:
        return row.get(key, default)
    except Exception:
        return default


def _truthy(value) -> bool:
    text = _text(value).lower()
    return value is True or text in {"1", "true", "yes", "y"}


def _labels(result: Dict) -> List[str]:
    labels = result.get("creative_type", []) if isinstance(result, dict) else []
    if isinstance(labels, str):
        labels = [part.strip() for part in labels.split(",")]
    if not isinstance(labels, list):
        return []
    return [str(label).strip() for label in labels if str(label).strip()]


def _blob(result: Dict) -> str:
    parts = [
        result.get("narrative", ""),
        result.get("content_details", ""),
        result.get("reasoning", ""),
    ]
    return " ".join(_text(part) for part in parts if _text(part)).lower()


def _visual_blob(result: Dict) -> str:
    """Return direct visual observations without model/guardrail reasoning."""
    parts = [
        result.get("narrative", ""),
        result.get("content_details", ""),
    ]
    return " ".join(_text(part) for part in parts if _text(part)).lower()


def _has_positive_motion_evidence(blob: str) -> bool:
    """Detect described motion without treating negated labels as evidence.

    Model reasoning often contains phrases such as "no dancing or lip sync" or
    "Fashion was prioritised over unsupported Dance". Those phrases describe a
    rejected label and must not suppress multi-frame verification.
    """
    patterns = [
        r"choreograph(?:y|ed|ic)", r"dance routine", r"dance challenge",
        r"synchroni[sz]ed", r"\bdancing\b", r"body movement",
        r"dance[- ]like (?:motion|movement)",
        r"(?:rhythmic|repeated|coordinated|synchroni[sz]ed) (?:hand|arm) (?:gesture|movement|motion|move)s?",
        r"(?:hand|arm) (?:gesture|movement|motion|move)s?.{0,40}(?:in sync|to the (?:beat|music|song)|choreograph)",
        r"hand[- ]gesture dance", r"hand choreography", r"upper[- ]body choreography",
        r"rhythmic (?:paw|paws|leg|legs|limb|limbs|body|movement).{0,45}(?:music|beat|rhythm)",
        r"moves? (?:its |their )?(?:paw|paws|leg|legs|limb|limbs|body).{0,45}(?:rhythmic|music|beat)",
        r"\bmouthing\b", r"mouths? the lyrics", r"lip[ -]?sync",
        r"sings? along", r"singing live", r"vocal performance",
        r"plays? guitar", r"plays? piano", r"instrument cover",
        r"\bworkout\b", r"\bexercise\b", r"gym training",
    ]
    negation = re.compile(
        r"\b(?:no|not|without|lacks?|neither|unsupported|rejected|removed|"
        r"does not|doesn't|do not|is not|isn't|are not|aren't|cannot|can't)\b",
        flags=re.I,
    )
    contrast = re.compile(r"\b(?:but|however|although|yet)\b", flags=re.I)

    for pattern in patterns:
        for match in re.finditer(pattern, blob, flags=re.I):
            clause_start = max(
                blob.rfind(".", 0, match.start()),
                blob.rfind(";", 0, match.start()),
                blob.rfind("!", 0, match.start()),
                blob.rfind("?", 0, match.start()),
            ) + 1
            prefix = blob[clause_start:match.start()][-120:]
            negations = list(negation.finditer(prefix))
            if negations:
                contrasts = list(contrast.finditer(prefix))
                if not contrasts or contrasts[-1].start() < negations[-1].start():
                    continue
            return True
    return False


def _row_blob(row) -> str:
    parts = [
        _get(row, "text"),
        _get(row, "caption"),
        _get(row, "Caption"),
        _get(row, "desc"),
        _get(row, "Description"),
    ]
    hashtags = _get(row, "hashtags", [])
    if isinstance(hashtags, list):
        for hashtag in hashtags:
            parts.append(hashtag.get("name", "") if isinstance(hashtag, dict) else hashtag)
    return " ".join(_text(part) for part in parts if _text(part)).lower()


def _has(blob: str, terms: Iterable[str]) -> bool:
    return any(term in blob for term in terms)


def _has_entertainment_news_evidence(visual_blob: str) -> bool:
    """Return True only for explicit real-world entertainment reporting cues."""
    explicit_category = bool(re.search(
        r"\bcontent categor(?:y|ies)\s*:\s*[^\n]{0,120}\bentertainment news\b",
        visual_blob,
        flags=re.I,
    ))
    if explicit_category:
        return True

    real_person_subject = bool(re.search(
        r"\breal[- ]life public figures?\b|\breal public figures?\b|"
        r"\bcelebrit(?:y|ies)\b|\bidols?\b|\bactors?\b|\bactresses?\b|"
        r"\bsingers?\b|\bmusic artists?\b",
        visual_blob,
        flags=re.I,
    ))
    reporting_event = bool(re.search(
        r"\b(?:entertainment|celebrity|showbiz) (?:news|update|report|coverage)\b|"
        r"\b(?:news|media|press) (?:report|reports|reported|reporting|coverage|update)\b|"
        r"\breported by (?:a |an )?(?:news|media|press|entertainment) (?:outlet|account|publication)\b|"
        r"\b(?:breakup|dating|relationship|marriage|divorce|casting|release) announcement\b|"
        r"\bofficial statement\b|"
        r"\b(?:announced|confirmed|reported|revealed).{0,80}"
        r"(?:breakup|dating|relationship|marriage|divorce|casting|release)\b|"
        r"\b(?:breakup|dating|relationship|marriage|divorce|casting|release).{0,80}"
        r"(?:announced|confirmed|reported|revealed)\b",
        visual_blob,
        flags=re.I,
    ))
    return real_person_subject and reporting_event


def _url_type(row) -> str:
    url = _text(
        _get(row, "webVideoUrl")
        or _get(row, "submittedVideoUrl")
        or _get(row, "url")
        or _get(row, "Link")
        or _get(row, "tiktok_url")
    ).lower()
    if _truthy(_get(row, "isSlideshow", False)) or _truthy(_get(row, "is_slideshow", False)) or "/photo/" in url:
        return "photo"
    if "/video/" in url:
        return "video"
    return "unknown"


def _slideshow_image_count(row):
    for key in ["slideshowImageLinks", "slideshow_images", "images"]:
        value = _get(row, key, None)
        if isinstance(value, (list, tuple)):
            return len([item for item in value if item not in [None, ""]])
    image_post = _get(row, "imagePostMeta", None)
    if isinstance(image_post, dict) and isinstance(image_post.get("images"), list):
        return len([item for item in image_post["images"] if item not in [None, ""]])
    return None


def _stable_key(row) -> str:
    candidates = [
        _get(row, "id"),
        _get(row, "webVideoUrl"),
        _get(row, "submittedVideoUrl"),
        _get(row, "url"),
        _get(row, "Link"),
        _get(row, "tiktok_url"),
    ]
    return next((_text(value) for value in candidates if _text(value)), "")


# -----------------------------------------------------------------------------
# Deterministic audit sampling and visual escalation
# -----------------------------------------------------------------------------


def deterministic_audit_sample(row, percent: int = QA_AUDIT_PERCENT) -> bool:
    key = _stable_key(row)
    if not key or percent <= 0:
        return False
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < min(int(percent), 100)


def visual_escalation_reasons(
    result: Dict,
    row=None,
    *,
    stage: str = "cover",
    previous_result: Dict | None = None,
) -> List[str]:
    """Return reusable reasons to request stronger visual evidence.

    Confidence alone is not enough for labels that depend on movement, text
    across several frames, or whether an edit shows a real or fictional person.
    These reasons trigger the existing 3-frame/9-frame/full-video cascade; they
    do not change labels and do not use exact URL memory.
    """
    if not isinstance(result, dict) or _url_type(row) == "photo":
        return []

    labels = set(_labels(result))
    if not labels:
        return []
    # Escalation evidence must come from direct observations, not reasoning.
    # Reasoning frequently names labels that the model explicitly rejected.
    visual_blob = _visual_blob(result)
    combined_blob = f"{visual_blob} {_row_blob(row)}"
    reasons: List[str] = []

    motion_labels = {"Dance", "Lip Sync", "Cover", "Fitness"}
    performance_alternatives = {
        "Comedy", "POV", "Relationship", "Slice of Life", "Fashion",
        "Beauty", "Quotes", "Reflection", "Celebrity Edits",
    }
    text_labels = {
        "Lyrics", "Lyrics Translation", "Quotes", "Reflection", "POV",
        "Relationship", "Media/Infotainment",
    }
    edit_labels = {"Celebrity Edits", "Movie/Tv/Drama Edits"}

    motion_evidence = _has_positive_motion_evidence(visual_blob)
    human_subject = _has(visual_blob, [
        "young woman", "young man", "woman", "man", "girl", "boy",
        "person", "creator", "selfie", "face filter", "cat-ear filter",
        "cat ear filter", "wearing",
    ])
    non_creator_subject = not human_subject and _has(visual_blob, [
        "cat", "cats", "dog", "dogs", "pet", "animal", "food dish",
        "product shot", "car showcase", "vehicle showcase", "scenery", "landscape",
    ])
    creator_performance = not non_creator_subject and _has(visual_blob, [
        "close-up", "close up", "faces the camera", "looks at the camera",
        "looks directly into the camera", "looks directly into camera",
        "looking directly into the camera", "looking directly into camera",
        "looking at the camera", "facing the camera", "front-facing camera",
        "to camera", "selfie", "poses", "posing", "gestures", "facial expression",
        "smiles at the camera", "creator performs", "person performs",
    ])
    text_evidence = _has(combined_blob, [
        "text overlay", "overlaid text", "on-screen text", "onscreen text",
        "subtitle", "lyrics", "lyric text", "quote", "caption ideas",
        "bilingual", "translated", "translation",
    ])
    edit_evidence = _has(combined_blob, [
        "fan edit", "montage", "scene edit", "drama scene", "movie scene",
        "anime", "fictional character", "celebrity", "idol", "actor",
        "artist edit", "fancam", "public figure",
    ])

    if stage == "cover":
        if labels & motion_labels:
            reasons.append("Motion-dependent label needs multi-frame verification")
        if creator_performance and labels & performance_alternatives:
            if motion_evidence:
                reasons.append("Observed motion may require Dance or Lip Sync rather than the cover label")
            else:
                reasons.append("Creator performance may be Dance or Lip Sync rather than a static-scene label")
        if text_evidence and labels & text_labels:
            reasons.append("Text meaning should be checked across multiple frames")
        if edit_evidence and labels & edit_labels:
            reasons.append("Real-person versus fictional-source edit needs multi-frame verification")
    else:
        previous_labels = set(_labels(previous_result or {}))
        if previous_labels and not (previous_labels & labels):
            reasons.append("Successive visual passes produced different labels")
        if labels & motion_labels and not motion_evidence:
            reasons.append("Motion label still lacks explicit motion evidence")
        full_video_resolved_non_motion = result.get("tier_used") == "tier2c_full_video" and not motion_evidence
        if (
            creator_performance
            and labels & performance_alternatives
            and not labels & motion_labels
            and not full_video_resolved_non_motion
        ):
            if motion_evidence:
                reasons.append("Observed motion still conflicts with the selected non-motion label")
            else:
                reasons.append("Creator performance remains visually ambiguous")

        translation_evidence = _has(visual_blob, [
            "translated lyrics", "lyrics translation", "bilingual lyrics",
            "original and translated", "translation beneath", "translation below",
            "translated subtitle",
        ]) or bool(re.search(
            r"(?:\bbilingual\b.{0,60}\blyrics?\b|\blyrics?\b.{0,60}\b(?:translated|translation|bilingual)\b)",
            visual_blob,
            flags=re.I,
        ))
        if "Lyrics Translation" in labels and not translation_evidence:
            reasons.append("Lyrics Translation lacks explicit translation or bilingual evidence")
        if "Lyrics" in labels and translation_evidence:
            reasons.append("Visible translation evidence conflicts with plain Lyrics")

        educational_evidence = _has(visual_blob, [
            "explains", "tutorial", "how to", "step-by-step", "step by step",
            "tips", "review", "news", "facts", "recommendation", "educational",
        ])
        if "Media/Infotainment" in labels and text_evidence and not educational_evidence:
            reasons.append("Text post lacks clear educational or informational purpose")

    return list(dict.fromkeys(reasons))


# -----------------------------------------------------------------------------
# Final review-risk composition and routing policy
# -----------------------------------------------------------------------------


def review_risk_reasons(
    result: Dict,
    row=None,
    include_audit: bool = False,
    include_guardrail_changes: bool = True,
) -> List[str]:
    """Return concise, evidence-based reasons that require human review."""
    if not isinstance(result, dict):
        return ["Unsupported AI result format"]

    reasons: List[str] = []
    labels = _labels(result)
    primary = labels[0] if labels else ""
    blob = _blob(result)
    # Review evidence excludes model reasoning because rejected label names in a
    # guardrail explanation must not create new visual evidence.
    visual_blob = " ".join(
        _text(result.get(key, "")) for key in ["narrative", "content_details"]
    ).lower()
    evidence_blob = f"{visual_blob} {_row_blob(row)}"
    try:
        confidence = float(result.get("confidence", 0) or 0)
    except Exception:
        confidence = 0.0

    if not labels:
        reasons.append("No Creative Type was produced")
    elif primary == "Others":
        reasons.append("Creative Type is Others")

    if confidence < LOW_CONFIDENCE_REVIEW:
        reasons.append(f"AI confidence below {LOW_CONFIDENCE_REVIEW:.0%} ({confidence:.0%})")

    before = [str(label).strip() for label in result.get("_pre_guardrail_labels", []) if str(label).strip()]
    labels_changed = bool(result.get("_guardrail_changed_labels")) or (bool(before) and before != labels)
    structural_carousel = (
        labels_changed
        and _url_type(row) == "photo"
        and labels
        and labels[0] == "Carousel"
    )
    if include_guardrail_changes and labels_changed and not structural_carousel:
        before_text = ", ".join(before) if before else "blank"
        after_text = ", ".join(labels) if labels else "blank"
        reasons.append(f"Guardrail changed Creative Type: {before_text} -> {after_text}")

    dance = bool(re.search(
        r"choreograph|dance (?:routine|challenge|performance|moves?)|"
        r"synchroni[sz]ed (?:dance|movement)|coordinated dance|"
        r"perform(?:s|ing)? (?:a |the )?(?:rhythmic )?dance|hand[- ]gesture dance|"
        r"dance[- ]like (?:motion|movement)|"
        r"(?:rhythmic|repeated|coordinated|synchroni[sz]ed) (?:hand|arm) (?:gesture|movement|motion|move)s?|"
        r"(?:hand|arm) (?:gesture|movement|motion|move)s?.{0,40}(?:in sync|to the (?:beat|music|song)|choreograph)|"
        r"hand choreography|upper[- ]body choreography|"
        r"rhythmic.{0,28}(?:paws?|legs?|limbs?|body|movement).{0,24}(?:music|beat|rhythm)|"
        r"moves? (?:its |their |his |her )?(?:paws?|legs?|limbs?|body).{0,35}(?:rhythmic|to the (?:music|beat))",
        visual_blob,
        flags=re.I,
    )) and "dancing slightly" not in visual_blob
    lip_sync = _has(visual_blob, ["lip sync", "lip-sync", "mouthing", "mouths the lyrics", "sings along"])
    fitness = _has(visual_blob, [
        "fitness", "workout", "exercise", "gym", "muscular", "physique",
        "flexing", "flexes", "stretching", "sports training", "training drill",
    ])
    beauty = bool(re.search(
        r"(?:apply|applies|applying).{0,20}makeup|makeup (?:tutorial|routine|transformation|makeover)|"
        r"(?:makeup|beauty|eyeliner|eyeshadow|eye shadow) (?:tips|advice|guide|recommendations?)|"
        r"(?:tips|advice|guide|recommendations?).{0,45}(?:makeup|beauty|eyeliner|eyeshadow|eye shadow)|"
        r"(?:eye|face) shape.{0,35}(?:makeup|eyeliner|eyeshadow|eye shadow)|"
        r"skincare (?:tutorial|routine|application)|cosmetic (?:procedure|application|review)|"
        r"nose (?:surgery|procedure)|nail art|hair tutorial|contact lenses?.{0,25}(?:showcase|product|review)|"
        r"(?:distinct|distinctive|creative|graphic|doll[- ]like).{0,30}makeup",
        visual_blob,
        flags=re.I,
    ))
    fashion = bool(re.search(
        r"\bootd\b|fit check|lookbook|outfit showcase|fashion showcase|styling showcase|"
        r"trying on (?:clothes|layers)|full[- ]outfit (?:display|showcase|transition)|"
        r"outfit transition|(?:focus(?:es|ing)? on|showcases?|displays?|presents?).{0,35}(?:the |an? )?(?:full )?outfit",
        visual_blob,
        flags=re.I,
    ))
    lyrics = bool(re.search(
        r"(?:visible|displayed|written|overlaid|on[- ]screen|onscreen|spotify[- ]style).{0,35}lyrics?|"
        r"lyrics?.{0,35}(?:visible|displayed|written|overlaid|on[- ]screen|onscreen)|lyric (?:video|text|card)",
        visual_blob,
        flags=re.I,
    ))
    carousel = _has(visual_blob, ["slideshow", "photo carousel", "series of photos", "series of images", "multiple photos"])
    tutorial = _has(visual_blob, [
        "tutorial", "demonstrates how", "step-by-step", "step by step",
        "explains how", "teaches how", "instructional steps",
        "pricing information", "clinic recommendation",
    ])
    # A short model-generated narrative such as "Dance tutorial" often names a
    # dance trend rather than an instructional post. Require actual teaching or
    # step evidence before routing a clearly described dance performance to
    # Media/Infotainment review.
    if (
        tutorial
        and dance
        and re.search(r"\bdance tutorial\b", visual_blob, flags=re.I)
        and not _has(visual_blob, [
            "demonstrates how", "step-by-step", "step by step", "explains how",
            "teaches how", "instructional steps", "breaks down the moves",
        ])
    ):
        tutorial = False
    relationship = any(re.search(pattern, evidence_blob, flags=re.I) for pattern in [
        r"wedding (?:photo|photos|photoshoot|photo shoot|portrait|portraits|attire)",
        r"pre[- ]wedding", r"bride and groom", r"romantic couple",
        r"couple (?:photoshoot|photo shoot|portraits?)", r"marriage proposal",
        r"engagement (?:ring|photoshoot|portrait)", r"husband and wife",
        r"romantic sentiment.{0,50}(?:partner|love|relationship)",
        r"relationship advice", r"dating advice", r"anxiety.{0,30}blind date",
        r"romantic partner", r"choosing (?:a|their|your) partner",
        r"bộ ảnh cưới", r"chụp ảnh cưới", r"ảnh cưới", r"đám cưới",
        r"cô dâu.{0,30}chú rể", r"chú rể.{0,30}cô dâu", r"vợ chồng",
    ])

    lyrics_contradiction = bool(re.search(
        r"(?:not|rather than|instead of|without).{0,28}(?:song )?lyrics?|"
        r"(?:subtitle|caption)s?.{0,40}(?:speech|spoken|dialogue|conversation)|"
        r"(?:speech|spoken|dialogue|conversation).{0,40}(?:subtitle|caption)s?|"
        r"not (?:a |the )?lyric display",
        visual_blob,
        flags=re.I,
    ))
    comedic_tone = bool(re.search(
        r"\bfunny\b|humorous|comedic|\bjoke\b|\bmeme\b|\bprank\b|\bpun\b|"
        r"absurd|mock kiss|playful and humorous",
        visual_blob,
        flags=re.I,
    ))
    reflective_tone = bool(re.search(
        r"(?:personal|emotional|relationship|life) reflection|introspection|reflecting on|"
        r"relationship advice|personal advice|emotional message|supportive message|"
        r"encouraging message|comforting message|melancholic|life goals?",
        visual_blob,
        flags=re.I,
    ))
    quote_format = bool(re.search(
        r"(?:prominent|main|central|overlaid|on[- ]screen) (?:text )?(?:quote|quotation|saying)|"
        r"(?:on[- ]screen|onscreen|overlaid) text.{0,80}(?:quote|quotation|saying)|"
        r"(?:quote|quotation|saying).{0,80}(?:on[- ]screen|onscreen|overlaid) text|"
        r"(?:quote|quotation) (?:card|post|text|overlay)|standalone (?:quote|saying)|"
        r"(?:teacher|mother|father|friend|someone) once (?:said|told)|"
        r"(?:attributed|presented) (?:as|to).{0,35}(?:quote|saying)|"
        r"\b(?:wise|motivational|inspirational|emotional|relationship) (?:teacher )?(?:quote|saying)\b|"
        r"\b(?:teacher|mother|father|friend|someone)(?:'s)? (?:quote|saying)\b|"
        r"(?:quote|saying).{0,80}(?:displayed|shown|presented).{0,35}(?:on[- ]screen|overlay)",
        visual_blob,
        flags=re.I,
    ))

    if primary == "Dance" and not dance and _has(visual_blob, [
        "fitness flex", "showcase his muscular physique", "showcase her muscular physique",
        "contact lenses", "makeup tutorial", "cooking tutorial", "product tutorial",
        "static quote", "lyrics displayed", "outfit showcase", "trying on layers", "knitwear",
    ]):
        reasons.append("Dance label conflicts with the AI's own visual description")
    if primary == "Lip Sync" and dance:
        reasons.append("Lip Sync label conflicts with visible choreography cues")
    if "Dance" in labels and primary != "Dance" and not dance:
        reasons.append("Secondary Dance label lacks explicit choreography evidence")
    direct_speech = _has(visual_blob, [
        "talks directly to the camera", "talks directly to camera",
        "speaks directly to the camera", "speaks directly to camera",
        "addresses the camera", "offers advice", "gives advice",
        "personal announcement",
    ])
    if set(labels) & {"Dance", "Lip Sync"} and direct_speech and not dance and not lip_sync:
        reasons.append("Motion label conflicts with direct-to-camera speech")
    if "Lyrics" in labels and not lyrics and _has(visual_blob, ["lip sync", "mouthing", "mouths the lyrics", "dance", "tutorial", "scene edit"]):
        reasons.append("Lyrics label lacks confirmed visible lyric-text evidence")
    if set(labels) & {"Lyrics", "Lyrics Translation"} and lyrics_contradiction:
        reasons.append("Lyrics label conflicts with speech or dialogue-subtitle evidence")
    if comedic_tone and reflective_tone:
        reasons.append("Comedy versus Reflection tone remains ambiguous")
    if comedic_tone and "Comedy" not in labels:
        reasons.append("Explicit joke, meme or comedic evidence is missing the Comedy label")
    if quote_format and "Quotes" not in labels and not lyrics:
        reasons.append("Attributed quote format is missing the Quotes label")
    if "Carousel" in labels and _url_type(row) == "video":
        reasons.append("Carousel label conflicts with video post metadata")
    if "Carousel" in labels and _slideshow_image_count(row) == 1:
        reasons.append("Carousel label conflicts with a confirmed single-image post")
    if primary == "Fitness" and not fitness and (beauty or fashion or tutorial):
        reasons.append("Fitness label lacks matching workout or sports evidence")
    if primary == "Beauty" and not beauty and fashion:
        reasons.append("Beauty versus Fashion evidence is ambiguous")
    if primary == "Fashion" and not fashion and beauty:
        reasons.append("Fashion versus Beauty evidence is ambiguous")
    if beauty and "Beauty" not in labels:
        reasons.append("Explicit beauty action is missing the Beauty label")
    if lip_sync and not dance and "Lip Sync" not in labels:
        reasons.append("Explicit mouthing/lip-sync evidence is missing the Lip Sync label")
    if relationship and "Relationship" not in labels:
        reasons.append("Explicit wedding/couple evidence is missing the Relationship label")

    travel = _has(visual_blob, ["beach vacation", "tropical beach", "vacation", "travel destination", "tourist destination", "trip vlog", "tourism", "jet skis on the ocean"])
    everyday_scenery = bool(re.search(
        r"(?:casual|ordinary|local|city) (?:drive|road|commute|highway|scenery)|"
        r"(?:drive|commute|highway).{0,55}(?:sunset|rainbow|city view)|"
        r"(?:sunset|rainbow) (?:view|capture|scene)",
        visual_blob,
        flags=re.I,
    ))
    reflection = bool(re.search(
        r"relationship reflection|emotional reflection|personal reflection|reflecting on|personal introspection|"
        r"(?:emotional|supportive|encouraging|comforting) (?:message|sentiment|statement)|"
        r"(?:express(?:es|ing)|shares?|offers?).{0,55}(?:care|support|encouragement|reassurance)",
        visual_blob,
        flags=re.I,
    )) and not lyrics
    non_human = _has(visual_blob, ["hamster", " cat ", " cats ", " dog ", " dogs ", " pet ", "animal"])
    synthetic_subject = bool(re.search(
        r"ai[- ]generated.{0,35}(?:character|child|person|performer|singer|musician|figure)|"
        r"(?:synthetic|virtual) (?:character|child|person|performer|singer|musician)|"
        r"computer[- ]generated (?:character|child|person|performer|singer)",
        evidence_blob,
        flags=re.I,
    ))
    animated_fictional_character = bool(re.search(
        r"(?:animated|illustration[- ]style|cartoon|anthropomorphic|fictional).{0,60}"
        r"(?:characters?|figures?|creatures?)|"
        r"(?:characters?|figures?|creatures?).{0,60}"
        r"(?:animated|cartoon|anthropomorphic|fictional)",
        visual_blob,
        flags=re.I,
    ))
    fictional = synthetic_subject or animated_fictional_character or _has(
        evidence_blob,
        ["anime character", "fictional character", "manga", "webtoon", "deltarune", "haikyuu", "saiki"],
    )
    explicit_pov = bool(re.search(
        r"(?:on[- ]screen|onscreen|overlaid|overlay) text.{0,80}(?<![a-z0-9])pov(?![a-z0-9])|"
        r"\bpov\s*[:\-]|\bpoint of view\b|\bfirst[- ]person (?:perspective|view|journey|experience|scenario|roleplay)|"
        r"(?:from|through) (?:the )?(?:viewer|creator|camera)(?:'s)? perspective",
        visual_blob,
        flags=re.I,
    ))
    camera_angle_only = bool(re.search(
        r"first[- ]person (?:camera|shot|footage|angle)|camera[- ]held (?:shot|footage)|"
        r"camera (?:shows|follows|captures).{0,50}(?:hand|road|receipt|object)",
        visual_blob,
        flags=re.I,
    ))
    audience_prompt = bool(re.search(
        r"(?:text|caption|post) (?:asks|prompts|invites) (?:the )?(?:viewer|audience|followers?)|"
        r"asks? (?:the )?(?:viewer|audience|followers?) to|"
        r"\b(?:name|guess|choose|pick) .{0,55}(?:initial|answer|option|flower|person)|"
        r"\bcomment (?:your|the) .{0,35}(?:answer|choice|initial)|"
        r"\btag (?:a |your )?(?:friend|partner|crush|someone)",
        evidence_blob,
        flags=re.I,
    ))
    abstract_template = _has(visual_blob, ["capcut template video", "oscillating abstract graphic", "abstract graphic animation", "template edit featuring abstract visual effects"])
    if travel and "Travel" not in labels:
        reasons.append("Explicit vacation/destination evidence is missing the Travel label")
    if primary == "Travel" and everyday_scenery and not travel:
        reasons.append("Travel label lacks trip or destination context; everyday scenery may be Slice of Life")
    if reflection and "Reflection" not in labels:
        reasons.append("Explicit reflection evidence is missing the Reflection label")
    if fashion and "Fashion" not in labels and ("Dance" in labels or primary == "Dance"):
        reasons.append("Outfit showcase evidence is stronger than Dance")
    if tutorial and "Media/Infotainment" not in labels:
        reasons.append("Explicit tutorial/review evidence is missing Media/Infotainment")
    if non_human and "Dance" in labels and not dance:
        reasons.append("Animal Dance label lacks explicit rhythmic or choreographed movement")
    if non_human and set(labels) & {"Lip Sync", "Cover"}:
        reasons.append("Animal vocal-performance label lacks explicit supporting evidence")
    if fictional and "Celebrity Edits" in labels:
        reasons.append("Celebrity Edits conflicts with a fictional/anime/game subject")
    if explicit_pov and "POV" not in labels:
        reasons.append("Explicit first-person/viewer-perspective evidence is missing the POV label")
    if "POV" in labels and audience_prompt and not explicit_pov:
        reasons.append("Audience prompt lacks first-person evidence required for POV")
    if "POV" in labels and camera_angle_only and not explicit_pov:
        reasons.append("POV appears based only on camera angle without an explicit scenario")
    synthetic_music_performance = synthetic_subject and bool(re.search(
        r"sings? (?:into|on|to|while)|singing (?:into|on|to|while)|vocal performance|"
        r"performs? (?:a |the )?song|concert performance|"
        r"plays? (?:the )?(?:guitar|piano|drums?|violin|instrument)|(?:virtual )?band performs?",
        visual_blob,
        flags=re.I,
    ))
    if synthetic_music_performance and "Cover" not in labels:
        reasons.append("AI-generated/virtual musical performance is missing the Cover label")
    fictional_edit = fictional and _has(evidence_blob, [
        "anime edit", "fan edit", "montage of scenes", "scenes from the anime",
        "anime montage", "fictional character montage",
    ])
    if fictional_edit and "Movie/Tv/Drama Edits" not in labels and not tutorial:
        reasons.append("Anime/fictional scene montage is missing Movie/Tv/Drama Edits")
    drama_edit = bool(re.search(
        r"k[- ]?drama (?:edit|scene|montage|clips?)|"
        r"(?:movie|tv|drama|anime|web series) (?:edit|scene montage|clip montage)|"
        r"clips? from (?:a |the )?(?:romantic )?(?:k[- ]?drama|movie|tv show|anime|web series)",
        visual_blob,
        flags=re.I,
    ))
    celebrity_edit = bool(re.search(
        r"(?:fan|celebrity|idol|artist|actor|actress|athlete|public figure) (?:edit|montage|compilation)|"
        r"(?:k[- ]?pop|real) (?:celebrity|idol|artist|actor|actress).{0,45}(?:edit|montage|compilation)|"
        r"fancam (?:edit|montage|compilation)",
        visual_blob,
        flags=re.I,
    ))
    if drama_edit and "Movie/Tv/Drama Edits" not in labels:
        reasons.append("Explicit drama/fictional edit evidence is missing Movie/Tv/Drama Edits")
    if celebrity_edit and "Celebrity Edits" not in labels:
        reasons.append("Explicit real-person fan-edit evidence is missing Celebrity Edits")
    if (
        "Movie/Tv/Drama Edits" in labels
        and _has_entertainment_news_evidence(visual_blob)
    ):
        reasons.append(
            "Entertainment News evidence conflicts with Movie/Tv/Drama Edits; "
            "confirm the post's reporting purpose"
        )
    public_figure_fanfiction = bool(re.search(
        r"fan[- ]?fiction|fan[- ]written|text[- ]based.{0,45}(?:story|dialogue|slideshow)|"
        r"written.{0,35}(?:fanfiction|dialogue|story)|prose narrative",
        evidence_blob,
        flags=re.I,
    )) and bool(re.search(
        r"\b(?:idol|k[- ]?pop|celebrity|public figure|actor|actress|music artist)s?\b|"
        r"#(?:kpop|idol|lesserafim|celebrity)",
        evidence_blob,
        flags=re.I,
    ))
    if public_figure_fanfiction:
        reasons.append("Public-figure fanfiction versus Celebrity Edits purpose needs adjudication")
    if (
        animated_fictional_character
        and "Movie/Tv/Drama Edits" not in labels
        and set(labels) & {"Slice of Life", "Comedy", "Relationship", "Others"}
        and not tutorial
    ):
        reasons.append("Animated/fictional character source needs Movie/Tv/Drama Edits verification")
    if abstract_template and "Media/Infotainment" in labels and not tutorial:
        reasons.append("Abstract template content is not informative by itself")

    audience_concert_recording = bool(re.search(
        r"(?:fan|audience member) (?:captures?|records?|films?).{0,70}(?:live|concert|artist|performer)|"
        r"filmed from (?:the )?audience.{0,50}(?:concert|stage|performance)|"
        r"audience (?:cheering|filming).{0,60}(?:artist|singer|band|performer) on stage",
        visual_blob,
        flags=re.I,
    ))
    if "Cover" in labels and audience_concert_recording:
        reasons.append("Cover conflicts with an audience recording of the original live performer")

    relationship_purpose = bool(re.search(
        r"relationship dynamics?|couple.s daily (?:interaction|interactions|life)|"
        r"couple.s relationship moments?|personal photos.{0,60}relationship moments?|"
        r"romantic couple.{0,45}(?:interaction|daily moment|affection)",
        visual_blob,
        flags=re.I,
    ))
    if relationship_purpose and "Relationship" not in labels:
        reasons.append("Explicit couple/relationship purpose is missing the Relationship label")

    # Model-generated details can reveal a contradiction even when confidence is high.
    if primary == "Dance" and fitness and not dance:
        reasons.append("Fitness evidence is stronger than Dance evidence")
    if primary == "Media/Infotainment" and not tutorial and _has(visual_blob, ["dance choreography", "lip sync performance"]):
        reasons.append("Media/Infotainment conflicts with performance evidence")

    if include_audit and not reasons and deterministic_audit_sample(row):
        reasons.append("Routine 5% quality-audit sample")

    # Keep order while removing duplicate messages.
    return list(dict.fromkeys(reasons))


def apply_review_policy(
    result: Dict,
    row,
    status: str,
    score: int,
    issues: List[str],
    *,
    include_audit: bool = False,
    include_guardrail_changes: bool = True,
) -> Tuple[Dict, str, int, List[str]]:
    """Apply review routing without changing the predicted labels."""
    output = dict(result or {})
    output_issues = list(issues or [])
    reasons = review_risk_reasons(
        output,
        row,
        include_audit=include_audit,
        include_guardrail_changes=include_guardrail_changes,
    )
    if reasons:
        output["needs_human_review"] = True
        output["review_risk_reasons"] = " | ".join(reasons)
        status = "review"
        for reason in reasons:
            message = f"Review risk: {reason}"
            if message not in output_issues:
                output_issues.append(message)
    return output, status, score, output_issues
