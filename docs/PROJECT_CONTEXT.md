# Project Context — UGC Creative Type Tagger

## Current release

v68.42.12 is the app version represented by this documentation. It preserves
the accepted v41-style five-step UI and General UGC pipeline, keeps Gemini 3.1
Flash-Lite as the recommended default, removes the Pro preview option, and
retains Gemini 3.5 Flash as an optional slower run. Targeted verification stays
on the explicitly selected run model; a 3.1 run does not make hidden 3.5 calls.

The app tries direct public retrieval first and uses Apify selectively when
required fields remain unavailable. Instagram Reels uses a platform-specific
adapter before the shared Gemini taxonomy, review queue and exports. The
adapter supports both current flat actor results and the earlier nested result
shape. Missing public Shares or Saves remain `Not available`; the app never
reports an unavailable metric as a confirmed zero.

Large runs save completed work and can resume from the first unfinished post.
Local checkpoints are always available. Optional Supabase/Postgres persistence
supports recovery after a restart or redeployment only after it has been
configured and verified in the target deployment.

The verifier checks consistency between existing Narrative, Content Details and labels; it is not an independent second view of the original media and must not be presented as a proven accuracy lift until a fresh locked holdout is scored.

## Goal and users

The tool helps marketing teams tag TikTok and Instagram Reels UGC posts into broad Creative Type labels and analyse performance. The UI must remain direct, non-technical and marketing-friendly.

## Accepted workflow

1. Add Posts
2. Select Posts
3. Run Tagging
4. Review
5. Summary & Export

Provider credentials are managed through Streamlit Secrets and are not exposed
as a marketing-facing workflow page.

General UGC is the default. Do not add a General-versus-Drama selector unless explicitly requested.

## Accepted input behaviour

- Upload one or more CSV/XLSX files.
- Paste TikTok or Instagram post/Reel links.
- Uploaded and pasted sources are additive.
- A supported TikTok or Instagram post link and a Track name are required for
  each row added to the Current Batch.
- Artist and Market are optional.
- The platform is detected from each link; unfamiliar column names are
  accepted when their values contain supported direct post URLs.
- Deduplicate by TikTok video ID, Instagram shortcode or normalized URL.

## Accepted selection behaviour

- Top posts ranks by the selected metric and can group by Market, Track, Source or Market + Track.
- Tag every link preserves batch order.
- Unavailable/private/deleted and sensitive posts are excluded automatically.
- Top posts can backfill from the next ranked candidate; Tag every link does not replace exclusions.
- A date window filters eligible rows but does not invent rows outside the selected window.
- The default is one shared date. When several tracks are present, users can instead set an independent centre date for each track.
- `Days before / after = 7` means an inclusive range from seven days before through seven days after each centre date.
- Per-track date filtering happens before Top N ranking and before the replacement pool is built.

## Accepted review and audit behaviour

- Review shows preview/link, creator, market, track, caption, metrics, suggested labels and Content Details.
- Users can keep, edit or remove.
- QA must preserve `Original AI Labels`, `Final Labels`, `Human Reviewed`, `Human Edited` and ordered `Label History`.
- When the targeted verifier runs, QA also preserves its input labels, output labels, status, confidence, reason, evidence and trigger.
- `Creative Type` remains the operational final-label alias for Summary/export compatibility.
- Human review must never destroy the original automated recommendation.

## Accepted Summary behaviour

Marketing-facing Summary includes KPIs, Creative Type Mix, performance by
type, Market Summary, KOL Size Performance, Track Summary, Top Creators, Top
Posts, Taggy assistance and downloads. Creator profile metrics remain separate
from post-level batch metrics. It must not expose confidence, tier, validation
or label history.

## Backend architecture

```text
Input → normalize and deduplicate → direct public retrieval
      → selective Apify fallback → normalized evidence → Gemini
      → global/semantic guardrails → optional Creative KB → market guardrails
      → temporal validation → targeted evidence verifier when needed
      → human review → summary and export
```

Normal videos start at temporal Tier 1 and escalate through 3 frames, 9 frames and full video only while unresolved. Review is the final fallback.

This remains an internal beta/pilot. It is not a coordinated multi-user
production system without additional authentication, shared job management,
monitoring and governance. Remote checkpoints and live provider behavior must
be verified in the target deployment before they are described as working.

## Knowledge Base policy

- Learn only from reviewed or explicitly approved rows.
- Store reusable patterns, not exact TikTok URL answers.
- Do not auto-learn from raw AI output.
- Learned creator/track files are local/private by default and are ignored by Git.

## Validation baseline

The locked v66.6 Core-100 run produced 93 evaluable rows, 73.1% exact legacy-label agreement and 95.7% conservative adjudicated semantic acceptance for the final human-assisted workflow. v67 fixes the measurement gap that prevented a pure AI-only accuracy calculation and targets the two remaining Lyrics contradictions.
