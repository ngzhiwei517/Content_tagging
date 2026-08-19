# AGENTS.md - UGC Content Tagging Tool

## Project summary
This repository contains a Streamlit prototype for AI-assisted TikTok and
Instagram Reels analysis in music-marketing workflows. It accepts CSV/XLSX
files or pasted post links, retrieves public post metrics and media evidence,
classifies creative content with Gemini, applies reusable guardrails, supports
human review, and exports marketing-ready reports.

The tool has two run modes:

- **AI tagging**: collect evidence and metrics, classify the content, review it,
  and build the dashboard and exports.
- **Metrics only**: collect available public metrics and calculate engagement
  fields without Gemini classification.

Treat this as a functional internal prototype/pilot. Do not describe it as an
enterprise multi-user production system without additional backend,
authentication, job-queue, monitoring, and governance work.

## Source-of-truth and Git rules
- The top-level `codex_tag` folder is an archive/work area and may not be a
  usable Git checkout. Do not assume its `.git` directory is authoritative.
- Before changing application code, locate the intended Git checkout or
  worktree, inspect its branch and dirty state, fetch `origin/main`, and confirm
  which baseline the user wants.
- Use current `origin/main` as the product baseline unless the user explicitly
  names another branch, PR, or candidate.
- Preserve unrelated user changes. Stage and commit only the intended files.
- Use a dedicated feature branch/worktree for code changes. Never push, merge,
  rebase, or update `main` unless the user explicitly asks.

## Current product direction
- Preserve the accepted v41-style five-step flow unless the user requests a
  deliberate redesign.
- Support TikTok and Instagram Reels through one shared downstream workflow.
- General UGC tagging is the default. Do not add a General-versus-Drama mode
  selector.
- Detailed drama enrichment is already integrated conditionally for confirmed
  `Movie/Tv/Drama Edits`; do not run it for unrelated creative types.
- Marketing users are the primary audience. Keep wording direct,
  non-technical, and decision-oriented.
- User-facing terms should be `Post`, `TikTok post`, `Instagram Reel`, or
  `UGC post`. Avoid MelodyIQ- or CreatorCore-specific wording except when
  describing input compatibility.

## Main workflow
1. **Add Posts**
   - Choose `AI tagging` or `Metrics only`.
   - Upload one or more CSV/XLSX files and/or paste supported post links.
   - Uploaded rows and pasted links are additive in one Current Batch.
2. **Select Posts**
   - Choose Top posts or Tag every link.
   - Apply optional platform, market, track, source, grouping, and date rules
     only when requested.
   - When bare pasted links need metric-based ranking, collect the eligible
     metrics before selecting the true Top N.
3. **Run Tagging / Fetch Metrics**
   - AI tagging runs the shared evidence and classification pipeline.
   - Metrics only skips Gemini classification and proceeds to downloadable
     metric results.
4. **Review**
   - Keep, edit, or remove posts; preserve the automated recommendation in QA.
   - Allow detailed drama fields to be reviewed and corrected when present.
5. **Summary & Export**
   - Present marketing KPIs, comparisons, creators, posts, recommendations,
     and downloads without exposing internal implementation noise.

API keys are deployment-managed through Streamlit Secrets rather than a normal
user workflow step.

## Input and normalization rules
- Every input row requires a supported TikTok or Instagram post URL.
- Track name is required in the current Add Posts flow. Suggest it from the
  filename or platform metadata when possible, but let the user correct it.
- Artist is optional. An Apple Music/iTunes lookup may fill it when the track
  match is reliable; an explicit user value remains authoritative.
- Market is optional. Keep it blank in working data when unknown and group or
  export it as `Other` only where needed.
- Support multiple mixed CSV/XLSX files and mixed pasted links.
- Preserve `Platform`, `Source`, market, track, artist, original sound, and
  input order where applicable.
- Deduplicate by TikTok video ID, Instagram shortcode, or normalized URL.
- Shortened, profile, hashtag, Story, private, deleted, or blocked links may be
  unavailable. Do not fabricate data for them.
- Deleted/private/unavailable posts should be removed from AI tagging rather
  than sent to manual label review. Top-N flows should backfill with the next
  ranked available item when enough candidates exist.
- A blank final AI label becomes `Others`, never an empty creative type.

## Public-data retrieval and cost control
- Use direct public retrieval first. Use Apify selectively only when direct
  retrieval fails or required fields remain unavailable.
- TikTok direct retrieval is normally more complete. Instagram often requires
  more fallback, especially for profile, Shares, or Saves data.
- Merge direct and fallback results metric by metric; never discard a valid
  direct value merely because another source is incomplete.
- Distinguish a confirmed numeric zero from an unavailable metric. Display
  `Not available`/`None` when neither source returns the field.
- Reuse credible metrics already present in uploaded files for selection. Fetch
  missing metrics only when the workflow requires them; do not trigger an
  unbounded paid refresh for a large upload without warning the user.
- Metrics-only mode must not call Gemini classification.
- Engagement and rate calculations must use only available source metrics and
  must avoid treating missing values as zero.
- Media may be downloaded temporarily for analysis, but must be deleted after
  use and never written to checkpoints or committed to the repository.

## AI-tagging pipeline
Supported posts -> direct retrieval -> selective Apify fallback -> normalized
evidence -> Gemini multimodal analysis -> global/semantic guardrails ->
reviewed Creative Knowledge Base -> conditional drama enrichment -> validation
and targeted verification -> human review when needed -> export.

- Start with lighter metadata/cover/frame evidence and inspect more frames or
  the full video only when necessary.
- Preserve accepted classification, tagging, UI, and export behavior unless the
  task explicitly changes it.
- Software tests prove code behavior, not classification accuracy. Accuracy
  claims require a fixed human-reviewed benchmark or a controlled regression
  set.

## Drama-analysis rules
- Run detailed drama analysis only after the broad creative type is confirmed
  as `Movie/Tv/Drama Edits`.
- Classify by the purpose of the post, not actor presence alone. Keep fictional
  drama scenes, anime edits, behind-the-scenes footage, real-person CP edits,
  actor profiles, and entertainment news distinct.
- Exact, relevant BL/GL caption or hashtag evidence can override a generic
  model subtype, but conflicting BL and GL evidence must remain reviewable.
- `Long-form Drama` versus `Short-form Drama` describes the source production,
  not the duration or vertical layout of the TikTok/Instagram clip.
- `Short-form Drama` requires independent production evidence such as an
  explicit micro/mini/vertical/short-drama format, platform, episode, title, or
  reviewed title mapping. A lone generic `shortfilm`/`shortdrama` tag or the
  model repeating `Short-form Drama` is insufficient.
- For a confirmed drama edit without reliable short-form evidence, use
  `Long-form Drama` as the operational default and keep it editable in review.
- Prefer generic evidence-based guardrails and regression tests. Never add an
  exact post-URL-to-label exception.

## Human review and audit trail
- Preserve `Original AI Labels` separately from `Final Labels`.
- Human edits must not overwrite the stored automated recommendation.
- Record `Human Reviewed`, `Human Edited`, and ordered `Label History` fields in
  internal QA outputs.
- Keep verifier status, input/output labels, confidence, evidence, and triggers
  in internal QA only.
- `Creative Type` remains the operational alias of `Final Labels` for dashboard
  and export compatibility.
- User-edited tables must recalculate dependent values such as KOL Size and
  Engagement Rate safely.

## Checkpoint and recovery rules
- Large or interruption-prone work must save protected progress after completed
  results and resume from the first unfinished item without repeating completed
  Gemini work.
- Local JSON checkpoints remain the fallback with no database configuration.
- Supabase REST or direct Postgres persistence is optional. Use the schema in
  `checkpoint_schema.sql` and the configuration documented in
  `docs/PERSISTENT_CHECKPOINTS.md`.
- Recovery links carry a private recovery ID in `?run=`. Treat them like access
  links and do not expose them publicly.
- Store only sanitized workflow state and tagging objects. Never store Gemini
  keys, Apify tokens, database credentials, secret-like columns, downloaded
  media, binary data, or local media paths.
- Remote persistence is best-effort and must not break the local fallback.
  Verify a real remote write/read before claiming restart or redeployment
  recovery is working.

## Taggy assistant rules
- Taggy first retrieves approved answers from
  `ugc_tagger/taggy_knowledge.json` for workflow, recovery, metric, cost, and
  limitation questions.
- Use Gemini for open-ended questions and dashboard interpretation, grounded in
  the current page, approved help, and current filtered results.
- If Gemini is unavailable, return a matching trusted local answer when one
  exists rather than a generic failure.
- Taggy may explain the page, summarize evidence, recommend creators or tests,
  and suggest campaign hypotheses. It must not invent unavailable audience,
  conversion, cost, private-platform, or forecast data.
- Taggy has no long-term chat memory and must never mutate the batch or results.

## Summary and export rules
- Keep the Summary marketing-focused: KPIs, creative performance, market and
  track/sound views, drama performance where relevant, top creators, top posts,
  suggested next steps, and downloads.
- Do not reintroduce a Source Summary section unless the user asks for it.
- Do not expose confidence tiers, guardrail internals, or technical validation
  details in the marketing-facing dashboard.
- Final CSV: one flat post table, preserving input order when requested.
- Final XLSX: `All Posts` plus one sheet per market when market data exists.
  Source remains a column, not a separate tab.
- Internal Review/QA workbook may include model, confidence, validation,
  verifier, review reason, and label-history fields.
- Include available Views, Likes, Comments, Shares, Saves, Followers, KOL Size,
  Engagements, Engagement Rate, and per-action rates.
- Use `Views`, not `Plays`, in user-facing labels.

## Knowledge Base policy
- Do not learn automatically from every raw AI output.
- Add reusable patterns only from reviewed or approved rows.
- Store generalizable creator, track, market, format, keyword, hashtag, and
  corrected-label evidence.
- Never use exact TikTok/Instagram URL-to-label memory for prediction.

## UI rules
- Keep the five-step v41-style flow and existing shared downstream behavior.
- Prefer a clean, mature, marketing-friendly interface with concise labels and
  short helper text.
- Do not add a large column-mapping panel when upload detection succeeds. Keep
  fixes under a small advanced/optional area only when needed.
- Current Batch is the main preview after adding files or links.
- Keep Review focused on preview/link, creator, market, track, caption, metrics,
  proposed labels, editable fields, and Keep/Edit/Remove actions.
- Keep table-local filtering and editing inside the relevant table. Do not add
  dashboard-wide filters or duplicate tables unless explicitly requested.
- Avoid excessive emojis, long explanations, technical status text, and
  textbook/corporate styling.

## Safety and secrets
- Never hardcode or commit Gemini keys, Apify tokens, Supabase keys, database
  URLs containing credentials, passwords, or other secrets.
- Never commit real campaign/user data, exports, downloaded media, or large
  provider datasets.
- Use placeholders, Streamlit Secrets, or environment variables for deployment
  configuration.
- Do not print secrets in terminal output, screenshots, logs, tests, or PR text.
- If data sensitivity is unclear, ask before saving it in the repository.

## Coding conventions
- Keep input handling, selection, scraping, tagging, drama analysis, review,
  recovery, summary, assistant, and export logic modular.
- Prefer small, reviewable patches and helper functions over broad rewrites or
  duplicated logic.
- Use pandas defensively: handle missing/duplicate columns, NaN, nullable and
  fractional metrics, mixed CSV/XLSX schemas, and stable row identifiers.
- Preserve unrelated working behavior and user changes.
- Keep user-facing text concise and consistent.

## Testing expectations
For application changes, run at minimum:

```text
python -m py_compile app.py
python -m compileall -q ugc_tagger
python -m unittest discover -s tests
```

Also run focused regression tests for the changed behavior. For UI changes,
perform a Streamlit smoke/health check and describe the exact manual path
tested. For recovery, scraping, Gemini, Apify, or Supabase changes, distinguish
mock/local test coverage from a controlled live-service verification.

For documentation-only changes, validate formatting, links, and the final diff;
the full application test suite is not required unless code also changed.

## Definition of done
A task is complete only when:

- the requested behavior or documentation is implemented in the intended
  checkout;
- the app still imports and starts for code changes;
- focused and baseline tests pass in proportion to the risk;
- existing core flows remain intact;
- known limitations and live-service verification gaps are stated clearly;
- no secrets, private data, downloaded media, or unrelated changes are included;
  and
- nothing is pushed or merged without the user's explicit approval.
