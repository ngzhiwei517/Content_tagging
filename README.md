# TikTok UGC Post Tagging Tool — v68.8

An AI-assisted Streamlit tool for marketing teams to select, tag, review and export TikTok UGC posts. It accepts generic CSV/XLSX exports or pasted TikTok links, collects post metadata with Apify, analyses visual content with Gemini, applies reusable guardrails and an optional Creative Knowledge Base, then routes uncertain rows to human review.

v68.8 is the final track-row and replacement-policy cleanup of v68.7. It keeps the accepted UI, complete v67 audit contract, the same tagging backend and the per-track viral-date feature.

## What changed in v68.8

- Places every track/date control in its own bordered row.
- Removes the unavailable/sensitive replacement checkbox.
- Always replaces unavailable and sensitive posts for Top N selections.

## What changed in v68.7

- Shortened the date-window labels and instructions.
- Simplified each track row to Track, Include and Date.
- Replaced the long technical date warning with a concise active-filter status.
- Shortened the unavailable/sensitive replacement option.

## What changed in v68.6

- Replaced the unreliable Date setup segmented control with two stateful buttons.
- The active date mode now stays purple after every click on older and newer Streamlit versions.
- The QA Summary now records the actual selection ranking metric rather than the Summary table sort.

## What changed in v68.5

- Highlights the selected Date setup choice in purple with white text.
- Supports newer and older Streamlit selected-state markup.

## What changed in v68.4

- Removed redundant helper lines from the Summary cards.
- Kept the engagement formulas and the Best Reach Type view total.

## What changed in v68.3

- Removed duplicate source-file worksheets from the grouped XLSX export.
- Kept `Source` as a normal column in `All Posts`, market worksheets and `Links Only`.

## What changed in v68.2

- Keeps both **Date setup** choices white with readable dark text on newer and older Streamlit versions.
- Keeps the selected choice visibly highlighted without changing date-filter behaviour.

## What changed in v68.1

- Removed new-only `segmented_control` arguments so the date setup works on the user's existing Mac Streamlit installation.
- Kept the v68 date-selection logic and all outputs unchanged.

## What changed in v68

- Keeps the existing shared date window as the default.
- Adds **Different date by track** when a filtered batch contains more than one track.
- Lets users enable or disable the date window independently for each track.
- Prefills a track date when the uploaded file contains one consistent `Viral Date`, `2026 Viral Date`, `First Viral Date` or `Track Viral Date` value.
- Applies each track's date window before Top N ranking and replacement-candidate selection.
- Keeps the verified `Days before / after = 7` meaning: seven days before through seven days after, inclusive.

## v67 audit foundation retained

- Preserves `Original AI Labels` separately from `Final Labels`.
- Records `Human Reviewed`, `Human Edited` and JSON `Label History` in the internal QA report.
- Keeps the marketing CSV/XLSX clean; audit fields appear only in the Review / QA Report.
- Prevents speech, dialogue subtitles and personal reflection from being labelled as Lyrics when song-lyric evidence is absent.
- Preserves genuine lyric videos, karaoke, displayed song lyrics and bilingual/translated lyrics.
- Removes unsupported secondary Dance labels when no choreography is described.
- Keeps Dance when explicit choreography, synchronized movement or a dance routine is present.
- Routes unresolved Comedy-versus-Reflection tone conflicts to human review.
- Uses current Streamlit `width="stretch"` parameters instead of deprecated `use_container_width`.
- Adds a clean Windows runner, GitHub Actions checks and release documentation.

See [CHANGELOG.md](CHANGELOG.md) for the earlier guardrail and UI history.

## Workflow

1. **Setup / API Keys** — enter Gemini and Apify credentials for the current browser session.
2. **Add Posts** — upload one or more CSV/XLSX files and/or paste TikTok links.
3. **Select Posts** — choose Top posts or Tag every link, with optional grouping and date filters.
4. **Run Tagging** — scrape metadata, analyse visual evidence and apply guardrails.
5. **Review** — keep, edit or remove uncertain posts.
6. **Summary & Export** — review marketing performance and download results.

## Input requirements

The only required field is a TikTok link. Column detection accepts common link-column names.

- `Market` is optional. Missing values remain blank in working data and display as **Other** where grouping is needed.
- `Track` is optional. Missing values display as **Not specified** in summaries.
- A viral-date column is optional. When available and consistent per track, it prefills the editable per-track date control.
- Uploaded files and pasted links are additive.
- Duplicate TikTok posts are deduplicated by video ID or normalized URL.
- Multiple CSV and XLSX files are supported.

## Selection and removal rules

- **Top posts** ranks by the selected metric and can take Top N per market, track, source or combined group.
- **Tag every link** processes the current batch in order without ranking.
- Unavailable, private and deleted posts are excluded automatically.
- Sensitive posts are excluded automatically.
- In Top posts mode, an excluded post is replaced by the next eligible ranked candidate when replacement is enabled.
- In Tag every link mode, excluded rows remain in internal QA without replacement.
- Blank AI output becomes `Others` and is routed appropriately.
- Date filtering can use one shared centre date or a different centre date for every detected track.
- A track whose date option is unchecked remains unfiltered, supporting non-viral campaign tracks.
- Date windows are applied before ranking. If fewer than N eligible posts exist inside a track's window, the app returns the available count rather than taking rows from outside the window.

## API keys

You need:

- a Gemini API key;
- an Apify API token.

Keys entered in the UI are kept only in Streamlit session state. They are not written to project files. Never commit `.env`, `.streamlit/secrets.toml`, tokens, downloaded media or raw Apify datasets.

## Run on Windows

Recommended: Python 3.11.

From Command Prompt inside the extracted folder:

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Or double-click `run_windows.bat`.

## Run on macOS

From Terminal inside the extracted folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

The commands do not require activation, so they avoid common shell permission and activation problems.

## Outputs

### Final CSV

A flat marketing table containing post context, metrics, narrative, final Creative Type and Content Details.

### Grouped XLSX

Contains All Posts plus market worksheets when market values are available. Source remains a column.

### Review / QA Report

Internal audit workbook containing all attempted rows, review status, confidence, tier, validation details and label history:

- `Original AI Labels` — the final automated recommendation after guardrails;
- `Final Labels` — the operational labels after review;
- `Human Reviewed` — whether a reviewer completed an action;
- `Human Edited` — whether final labels differ from the original automated labels;
- `Label History` — ordered automated and human-review events.

These fields make future AI-only accuracy and human-assisted workflow accuracy measurable separately.

## Validation status

The locked Core-100 validation was run on the v66.6 baseline that directly preceded v67:

- 100 posts tested;
- 93 available/evaluable posts;
- 7 correctly excluded;
- 73.1% exact top-two agreement with the legacy single-label benchmark;
- 95.7% conservative adjudicated semantic acceptance for the **final human-assisted workflow**;
- 2 clear remaining errors, both Lyrics contradictions targeted by v67.

The 95.7% result must not be described as pure AI-only accuracy because the old QA export overwrote original labels on reviewed rows. v67 fixes that measurement gap. v67 has focused automated regression coverage, but its post-change blind accuracy should be reported only after a fresh holdout run.

See [docs/VALIDATION.md](docs/VALIDATION.md) for definitions and reporting language.

## Tests

```bash
python -m py_compile app.py final_update2_adapter.py final_update2_backend.py final_update2_backend_source.py review_routing.py
python -m unittest discover -s tests -v
```

The v68.8 package contains 105 unit and contract tests.

## Per-track date selection test

The release is supplied with a separate local-only Mastering-derived test file and answer key; they are intentionally excluded from the GitHub-ready ZIP.

1. Upload `v68_per_track_viral_date_test_40.csv`.
2. Choose **Top posts**, **10** posts per group, rank by **Views**, and group by **Track**.
3. Enable the date window and choose **Different date by track**.
4. Use **04 Jan 2026** for `Nuca - Masa ini, Nanti, dan Masa Indah Lainnya`.
5. Use **08 Mar 2026** for `Bruno Mars - Risk It All`.
6. Keep **Days before / after = 7**.
7. Expect **20 selected posts: 10 per track**. Compare them with `v68_per_track_viral_date_expected_top20.csv` or the supplied test guide workbook.

This is a Step 3 selection test and does not require running Apify or Gemini.

## Architecture

```text
Input posts
  → Apify scraping
  → Gemini multimodal analysis
  → global and semantic guardrails
  → optional Creative Knowledge Base
  → market guardrails
  → temporal validation (cover → 3 frames → 9 frames → full video when unresolved)
  → human review when needed
  → marketing exports + internal QA
```

Main modules:

- `app.py` — accepted Streamlit workflow and exports;
- `final_update2_adapter.py` — schema adaptation and label-audit fields;
- `final_update2_backend.py` — import-safe backend loader;
- `final_update2_backend_source.py` — scraper, Gemini and guardrail pipeline;
- `review_routing.py` — evidence-based escalation and review routing;
- `accuracy_metrics.py` — benchmark scoring helpers;
- `creative_knowledge/` — optional reusable approved patterns.

## Creative Knowledge Base and GitHub privacy

The internal runtime package may contain `creative_knowledge/creator_rules.json`, `track_rules.json` and `metadata.json` learned from reviewed campaign data. The supplied `.gitignore` prevents these three files from being committed accidentally.

The app runs without them, but classification can differ because creator/track priors are unavailable. Do not publish learned creator or campaign patterns to a public repository without confirming data rights. Sanitized examples are included for documentation.

## Known limitations

- TikTok availability, private posts and platform changes can prevent scraping.
- Gemini and Apify calls use external quota and may incur cost.
- Some creative types are genuinely ambiguous; human review remains part of the product design.
- Session state is temporary and is not a production database.
- The detailed Drama / Creator Core mode is not part of v68.
- Approved KB updates are still a controlled/manual process; raw AI output must never update the KB automatically.

## Repository guidance

Use this extracted `marketing_tagger_v68_8_per_track_viral_dates` folder as the GitHub repository root. Do not push the parent `codex_tag` workspace because it contains internal outputs, old versions and temporary tooling.
