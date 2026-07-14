# Project Context — TikTok UGC Creative Type Tagger

## Current release

v68.15 is the current demo release. It preserves the accepted v41-style UI and the v68.14 General UGC tagging pipeline, adds reconnect recovery for non-secret workflow data, and presents the Summary in a clearer marketing sequence: Market, Track, then Creative Type.

The verifier checks consistency between existing Narrative, Content Details and labels; it is not an independent second view of the original media and must not be presented as a proven accuracy lift until a fresh locked holdout is scored.

## Goal and users

The tool helps marketing teams tag TikTok UGC posts into broad Creative Type labels and analyse performance. The UI must remain direct, non-technical and marketing-friendly.

## Accepted workflow

1. Setup / API Keys
2. Add Posts
3. Select Posts
4. Run Tagging
5. Review
6. Summary & Export

General UGC is the default. Do not add a General-versus-Drama selector unless explicitly requested.

## Accepted input behaviour

- Upload one or more CSV/XLSX files.
- Paste TikTok links.
- Uploaded and pasted sources are additive.
- TikTok link is the only required field.
- Market and Track are optional.
- Deduplicate by TikTok video ID or normalized URL.

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

Marketing-facing Summary includes KPIs, Creative Type Mix, performance by type, Market Summary, KOL Size Performance, Track Summary, Top Posts and downloads. It must not expose confidence, tier, validation or label history.

## Backend architecture

```text
Input → Apify → Gemini → global/semantic guardrails → optional Creative KB
      → market guardrails → temporal validation → targeted evidence verifier when needed
      → human review → export
```

Normal videos start at temporal Tier 1 and escalate through 3 frames, 9 frames and full video only while unresolved. Review is the final fallback.

## Knowledge Base policy

- Learn only from reviewed or explicitly approved rows.
- Store reusable patterns, not exact TikTok URL answers.
- Do not auto-learn from raw AI output.
- Learned creator/track files are local/private by default and are ignored by Git.

## Validation baseline

The locked v66.6 Core-100 run produced 93 evaluable rows, 73.1% exact legacy-label agreement and 95.7% conservative adjudicated semantic acceptance for the final human-assisted workflow. v67 fixes the measurement gap that prevented a pure AI-only accuracy calculation and targets the two remaining Lyrics contradictions.
