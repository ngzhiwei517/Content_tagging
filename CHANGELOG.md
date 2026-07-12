# Changelog

## v68.9 — Flexible CSV import compatibility

- Added automatic comma, semicolon, tab and pipe delimiter detection.
- Added UTF-8 BOM and UTF-16 CSV support.
- Added common generic, Creator-style and Apify link/metric header aliases.
- Added six CSV compatibility regression tests and a local cross-format test kit.

## v68.8 — Bordered track rows and automatic replacement

- Added a bordered container around every per-track date row.
- Removed the replacement checkbox from the user flow.
- Made replacement of unavailable and sensitive Top N posts always active.

## v68.7 — Date-filter usability cleanup

- Simplified the date-window label and per-track helper text.
- Renamed `Use date` to `Include` and shortened the replacement option.
- Replaced the long technical active-filter warning with a concise status line.

## v68.6 — Persistent date-mode highlight and audit fix

- Replaced the version-sensitive segmented control with two stateful primary/secondary buttons.
- Ensured the active Date setup choice remains purple after clicking.
- Corrected `Current Sort Metric` in the QA Summary to record the actual selection ranking.

## v68.5 — Selected date choice highlight

- Added a strong purple background and white text to the selected Date setup choice.
- Added selected-state selectors for newer and older Streamlit markup.

## v68.4 — Summary card copy cleanup

- Removed redundant helper text from Posts, Views, Markets, Most Common Format, Main Market and Track / Source.
- Kept the Engagements formula, Engagement Rate formula and Best Reach Type view total.
- Omitted empty helper elements from rendered card HTML.

## v68.3 — Grouped export cleanup

- Removed duplicate source-file worksheets from the grouped XLSX export.
- Kept source provenance as a column in the remaining worksheets.
- Added an export regression test covering multiple source files.

## v68.2 — Date setup visibility fix

- Made both date-scope choices white with readable dark text.
- Added compatible selectors for newer and older Streamlit segmented-control markup.
- Kept the active choice highlighted and left date-filter behaviour unchanged.

## v68.1 — Streamlit compatibility fix

- Removed `required` and `width` from the new date-scope segmented control for compatibility with the user's existing Mac Streamlit runtime.
- Added a regression contract for the supported segmented-control arguments.

## v68 — Per-track viral-date selection

- Added optional separate viral dates for multiple tracks in one batch.
- Kept the existing shared date window as the default and preserved inclusive ±7-day behaviour.
- Added per-track opt-out for non-viral tracks.
- Added optional prefill from supported uploaded viral-date columns.
- Applied track windows before Top N ranking and replacement-candidate selection.
- Added a 40-row Mastering-derived external fixture, answer key and dedicated regression tests.

## v67 — Auditable final release candidate

- Added separate Original AI Labels and Final Labels.
- Added Human Reviewed, Human Edited and ordered Label History fields.
- Added a Lyrics contradiction safeguard for speech/dialogue subtitles and personal reflection.
- Added an unsupported-secondary-Dance safeguard.
- Added review routing for mixed Comedy/Reflection tone.
- Kept QA diagnostics out of marketing exports.
- Replaced deprecated Streamlit `use_container_width` arguments.
- Added GitHub-ready documentation, Windows runner and CI checks.

## v66.6 — Final candidate accuracy safeguards

- Prioritized supportive/personal text as Reflection unless explicit song-lyric evidence exists.
- Required direct first-person evidence for POV.
- Prevented creator/track history from overriding stronger Narrative and Content Details.
- Improved Beauty recovery for makeup advice and cosmetic content.
- Improved AI-generated/fictional performer handling.

## v66.5 — Selection and summary cleanup

- Excluded sensitive posts in every selection mode.
- Backfilled Top posts from the next eligible candidate.
- Kept Tag every link without replacement.
- Simplified Summary headings while preserving performance sections.

## v60–v66.4 — Evidence-first classifier development

- Enforced cover → 3-frame → 9-frame → full-video escalation when unresolved.
- Added deterministic 5% QA sampling.
- Added Lyrics versus Lyrics Translation rules.
- Reduced false Dance, Lip Sync, POV, Beauty and Carousel assignments.
- Added Movie/Tv/Drama Edits, Celebrity Edits, Relationship, Reflection, Travel, Fashion, Fitness and Media/Infotainment consistency rules.
- Added KOL Size performance reporting and filter-aware Summary views.
- Kept rules general: no exact TikTok URL-to-label prediction memory.
