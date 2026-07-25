# Technical maintainer handover

This guide is the complete clean-account workflow for installing, running,
testing, changing and publishing the UGC Content Tagging Platform.

Use this guide during the handover rehearsal. A new maintainer should be able to
complete the workflow without private instructions or access to the previous
maintainer's computer.

## 1. What the maintainer receives

The repository contains:

- `app.py` — the Streamlit entry point and six-step user interface;
- `ugc_tagger/` — platform adapters, tagging backend, review routing and drama
  analysis;
- `creative_knowledge/` — approved reusable tagging patterns;
- `tests/` — automated regression tests;
- `run_windows.bat` — one-click Windows setup and launch;
- `run_mac.command` — macOS setup and launch;
- `AGENTS.md` — durable instructions for Codex or another coding agent;
- `docs/CODE_MAP.md` — where each technical responsibility lives;
- `docs/TESTING.md` — automated and manual testing expectations;
- `CHANGELOG.md` — current release behavior and recent changes.

The runtime version in `ugc_tagger/final_update2_adapter.py` and the latest
entry in `CHANGELOG.md` are the version sources of truth.

## 2. Account and access setup

The repository is public, so anyone can clone and run it. Pushing changes
requires one of these arrangements:

### Recommended for the real maintainer

1. Create or use a personal GitHub account.
2. Ask the repository owner to add the account as a collaborator.
3. Enable two-factor authentication.
4. Accept the repository invitation.
5. Never share a GitHub password, personal access token, Gemini key or Apify
   token.

### Recommended for the rehearsal

Use a new GitHub account to fork the repository. This proves that the written
instructions work without giving the test account access to production.

1. Open `https://github.com/ngzhiwei517/Content_tagging`.
2. Select **Fork**.
3. Create the fork under the test account.
4. Clone the fork and perform the rehearsal there.
5. Do not merge the rehearsal changes into the production repository.

## 3. Software required

### Windows

Install:

1. Git for Windows;
2. Python 3.14, including the Python Launcher for Windows;
3. a web browser;
4. optional: GitHub Desktop or GitHub CLI;
5. optional: Codex desktop app for assisted maintenance.

Confirm the installation in PowerShell:

```powershell
git --version
py -3.14 --version
```

### macOS

Install:

1. Git;
2. Python 3.14 or a compatible Python 3.11+ environment;
3. a web browser;
4. optional: GitHub Desktop or GitHub CLI;
5. optional: Codex desktop app.

Confirm the installation in Terminal:

```bash
git --version
python3 --version
```

## 4. Clone the repository

### Production maintainer

```powershell
git clone https://github.com/ngzhiwei517/Content_tagging.git
cd Content_tagging
git switch main
git pull --ff-only origin main
```

### Clean-account rehearsal using a fork

Replace `NEW_ACCOUNT` with the test account's GitHub username:

```powershell
git clone https://github.com/NEW_ACCOUNT/Content_tagging.git
cd Content_tagging
git remote add upstream https://github.com/ngzhiwei517/Content_tagging.git
git remote -v
```

Before every new change, synchronize the fork:

```powershell
git switch main
git fetch upstream
git merge --ff-only upstream/main
git push origin main
```

If the readability pull request has not been merged during the rehearsal, test
its remote branch directly:

```powershell
git fetch upstream agent/readability-refactor
git switch --create agent/readability-refactor --track upstream/agent/readability-refactor
```

## 5. First local run

### Windows one-click run

Double-click:

```text
run_windows.bat
```

The launcher:

1. changes to the repository folder;
2. creates `.venv` with Python 3.14 when available, with Python 3.13 and 3.11
   as supported fallbacks;
3. installs `requirements.txt` when dependencies are missing or the
   requirements file has changed;
4. starts Streamlit with `app.py`.

The browser normally opens at:

```text
http://localhost:8501
```

Keep the terminal window open while using the app. Press `Ctrl+C` in the
terminal to stop it.

### Windows manual fallback

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### macOS one-click run

The first time:

```bash
chmod +x run_mac.command
./run_mac.command
```

If macOS blocks the file, right-click it, choose **Open**, and confirm.

### macOS manual fallback

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

## 6. API keys

The app requires:

- a Gemini API key;
- an Apify API token.

### Create a Gemini API key

Each maintainer must use their own key:

1. Open `https://aistudio.google.com/apikey`.
2. Sign in and accept the Google AI Studio terms.
3. Use the default project and key created for a new account, or select
   **Create API key**.
4. Copy the key without including it in a screenshot, document or chat.

If AI Studio reports that project creation failed or shows no available
projects:

1. Open `https://console.cloud.google.com/projectcreate` with the same account.
2. Create a project such as `UGC Content Tagging`.
3. Return to AI Studio and open **Projects > Import projects**.
4. Import the new project, then create the API key under that project.

If **No organization** cannot be selected, the account is normally managed by
a company or school and lacks project-creation permission. For a rehearsal, use
a personal Google account. For production, ask the organization administrator
for the appropriate Project Creator and API-key permissions.

### Create an Apify API token

1. Create or sign in to an Apify account.
2. Open `https://console.apify.com/settings/integrations`.
3. Under **Personal API tokens**, create a dedicated token such as
   `UGC tagging local`.
4. Copy the token and monitor that account's Actor usage and available credits.

Enter both values only on the app's **Setup / API Keys** page.
The app keeps them in the active Streamlit session; it does not require them to
be written into the repository.

Never:

- paste keys into source code;
- add keys to `AGENTS.md`, documentation or test files;
- commit `.streamlit/secrets.toml`;
- send keys in screenshots or chat messages;
- use the previous maintainer's credentials.

The clean-account rehearsal must use the test maintainer's own credentials.

## 7. First functional smoke test

Use a small batch of approximately six public direct-post URLs:

- two ordinary TikTok videos;
- one TikTok photo/carousel post;
- two Instagram Reels;
- one deliberately unavailable or private test link, when available.

Direct URLs are the most reliable:

```text
https://www.tiktok.com/@creator/video/123...
https://www.tiktok.com/@creator/photo/123...
https://www.instagram.com/reel/SHORTCODE/
https://www.instagram.com/p/SHORTCODE/
```

Avoid redirect/share URLs for the first test. See
`docs/LINK_COMPATIBILITY.md` for the tested link boundary.

Complete the full workflow:

1. Open **Setup / API Keys** and enter the two test credentials.
2. Open **Add Posts**.
3. Upload a small CSV/XLSX file, paste additional links, or do both.
4. Confirm uploaded and pasted rows appear in one **Current Batch**.
5. Confirm TikTok and Instagram are detected automatically.
6. Confirm duplicates are removed.
7. Open **Select Posts**.
8. Choose **Tag every link** for the smoke test.
9. Use Gemini 3.1 Flash-Lite unless testing a specific model comparison.
10. Run tagging and keep the terminal open for logs.
11. Confirm unavailable/private posts are removed automatically.
12. Confirm uncertain or restricted-but-viewable posts enter Human Review.
13. On **Review**, keep one post, edit one post and remove one post.
14. Confirm Original AI Labels remain preserved in the QA output.
15. Confirm blank Instagram Shares/Saves display as `Not available`, not zero.
16. Open **Summary & Export**.
17. Download the final CSV, grouped XLSX and internal QA workbook.
18. Confirm TikTok and Instagram remain together in the same exports.
19. Confirm technical confidence and guardrail fields appear only in QA, not in
    the marketing summary.

Record:

- date and time;
- computer and operating system;
- Python version;
- branch and commit;
- test link count;
- successful rows;
- removed/unavailable rows;
- Human Review rows;
- any error message or screenshot.

## 8. Automated checks

Run these checks before pushing any code change.

### Windows

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py
.\.venv\Scripts\python.exe -m compileall -q ugc_tagger
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### macOS

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m compileall -q ugc_tagger
.venv/bin/python -m unittest discover -s tests -v
```

Also inspect the change:

```powershell
git status --short
git diff --check
git diff
```

Automated tests confirm software behavior. They do not prove tagging accuracy.
Accuracy changes require a locked, human-labelled validation dataset.

## 9. Starting a maintenance task with Codex

Open the cloned repository folder in Codex. Start each important task in a new
conversation so the task has a clear objective.

Use this read-first prompt:

```text
Read AGENTS.md, docs/PROJECT_CONTEXT.md, docs/CODE_MAP.md,
docs/TESTING.md and CHANGELOG.md completely.

Do not edit anything yet.

Tell me:
1. the current Git branch and whether the worktree is clean;
2. the current app version;
3. the active runtime path for this request;
4. the important rules that must remain unchanged;
5. the tests required before completion.

Then wait for my change request.
```

For a good change request, include:

- **Goal** — the result required;
- **Context** — relevant page, file, screenshot, error or example;
- **Boundaries** — what must remain unchanged;
- **Done when** — tests and behavior that prove completion.

This follows OpenAI's Codex prompting guidance: clear goal, context,
constraints and completion conditions make repository changes easier to scope
and review. See [Codex best practices](https://learn.chatgpt.com/guides/best-practices)
and [Prompting](https://learn.chatgpt.com/docs/prompting).

## 10. Prompt templates for common changes

### A. Diagnose a bug without changing code

```text
Diagnose this problem but do not implement a fix yet:
[paste the error and attach the screenshot]

Reproduce it if possible, identify the root cause, list the affected files and
tell me the smallest safe fix. Preserve the current tagging rules and UI flow.
```

### B. Fix a confirmed bug

```text
Fix this confirmed bug:
[describe the expected and actual behavior]

Context:
[attach screenshot, error or example input]

Boundaries:
- preserve the v41-style six-step workflow;
- do not change prompts, taxonomy, confidence threshold or drama logic unless
  required for this bug;
- do not add secrets or real campaign data;
- make a focused regression test.

Done when:
- the bug no longer reproduces;
- existing tests pass;
- Streamlit starts without exceptions;
- you show me the changed files and remaining limitations.

Do not push until I review the local result.
```

### C. Change UI wording or layout

```text
Update this Streamlit UI area:
[describe the page and desired result]

Use the existing visual style. Keep the current workflow, session-state
behavior, tagging backend and exports unchanged.

Run syntax checks and a Streamlit smoke test. Tell me the exact manual steps I
should test locally. Do not push yet.
```

### D. Change a reusable tagging rule

```text
Review this recurring classification problem:
[provide several examples, expected labels and reasons]

Implement only a reusable pattern. Do not memorize exact post URLs and do not
learn from unreviewed AI output.

Preserve unrelated categories and the accepted drama pipeline. Add focused
regression cases for both positive and negative examples. Run the full test
suite, then give me a validation dataset to test manually.

Do not claim an accuracy improvement until the locked holdout is adjudicated.
Do not push yet.
```

### E. Change Instagram ingestion or metrics

```text
Update Instagram Reels ingestion for:
[describe the actor field, missing metric or error]

Keep TikTok and Instagram in one shared UI, taxonomy, review queue and export.
Do not change the TikTok classifier. Preserve unavailable metrics as
Not available rather than zero.

Test nested and flat Instagram payloads, actor failure fallback and export
preservation. Do not push yet.
```

### F. Experiment with confidence or review routing

```text
Create an isolated experiment for the Human Review threshold:
[state the thresholds and dataset]

Do not change the production default yet. Compare:
- auto-pass accuracy;
- Human Review rate;
- confirmed high-confidence errors still missed;
- unavailable rows;
- sample size.

Use the same locked outputs for every threshold. Report whether the improvement
is practically meaningful. Keep the production branch untouched.
```

### G. Documentation-only change

```text
Update only the documentation for:
[describe the missing or incorrect guidance]

Verify every command and file path against the current repository. Do not
change runtime behavior. Show me the diff and do not push yet.
```

### H. Ask Codex to review the completed change

```text
Review the current uncommitted change against main.

Look for functional regressions, duplicated logic, broken session state,
incorrect metrics, exposed secrets, missing tests and documentation that no
longer matches the code.

Do not edit during the first review. List findings by severity and include the
file and line number.
```

### I. Publish only after approval

```text
The local change is approved.

Confirm the worktree contains only the intended files, rerun all required
checks, commit to a separate branch, push the branch and open a draft pull
request against main.

Do not merge the pull request. Report the branch, commit, PR link and checks.
```

## 11. Branch workflow

Never develop directly on `main`.

Before starting:

```powershell
git switch main
git pull --ff-only origin main
git status --short
git switch -c maintainer/short-description
```

If Codex creates the branch, `agent/short-description` is also acceptable.

During work:

```powershell
git status --short
git diff
```

Before committing:

1. Run automated checks.
2. Run the relevant manual smoke test.
3. Confirm no keys, downloaded media, exports or private datasets are present.
4. Review every changed file.
5. Confirm documentation and version notes remain accurate.

Commit:

```powershell
git add path\to\intended-file1 path\to\intended-file2
git commit -m "Describe the completed change"
```

Push:

```powershell
git push -u origin maintainer/short-description
```

Open a draft pull request into `main`. The pull request must state:

- what changed;
- why it changed;
- what intentionally did not change;
- tests run;
- manual smoke test performed;
- known limitations;
- screenshots for visible UI changes.

## 12. Pull request review

The reviewer should check:

- the change matches the request;
- no unrelated files changed;
- no credentials or real user data were committed;
- `app.py` remains presentation-focused;
- tagging behavior changes live in the correct backend module;
- reviewed rules are reusable and not exact URL memory;
- tests cover both expected and rejection cases;
- Human Review behavior remains understandable;
- marketing exports and QA exports preserve their different purposes;
- the changelog and relevant docs are updated;
- all checks pass.

Do not merge merely because GitHub shows a green check. Complete the manual
smoke test for user-visible or pipeline changes.

## 13. Deployment verification

After an approved PR is merged:

1. Confirm `main` contains the expected commit.
2. Open the Streamlit Cloud app.
3. Check deployment logs for import or dependency errors.
4. Confirm the home/setup page renders.
5. Run a small TikTok and Instagram smoke batch.
6. Confirm Review, Summary and downloads work.
7. Record the deployed commit and test result.

If the deployment fails, do not make random changes on `main`. Reproduce the
problem locally, create a focused hotfix branch and follow the same PR process.

## 14. Rollback

If an approved deployment causes a serious regression:

1. identify the last known-good commit;
2. capture the error and affected workflow;
3. create a revert or hotfix pull request;
4. run automated and manual checks;
5. merge only after review;
6. verify the deployed app again.

Do not use `git reset --hard` on shared branches and do not delete history.

## 15. Tagging accuracy changes

Software tests and Streamlit smoke tests are not accuracy measurements.

For any claim that tagging accuracy improved:

1. freeze the candidate version;
2. use a locked human-labelled dataset not used to create the rule;
3. preserve the untouched AI output;
4. compare AI labels with the original human reference;
5. manually adjudicate every mismatch;
6. separate confirmed AI errors from incorrect or defensible human labels;
7. report exact agreement, accepted/defensible accuracy, confirmed error rate,
   Human Review rate, unavailable posts, sample size and confidence interval;
8. document recurring limitations;
9. do not automatically add adjudicated URLs as prediction memory.

TikTok and Instagram accuracy should be reported separately unless a benchmark
was explicitly designed as a combined platform sample.

## 16. Common problems

### `run_windows.bat` closes immediately

Open PowerShell in the repository and run:

```powershell
cmd /k run_windows.bat
```

Read the error before closing the window.

### A supported Python version is not found

```powershell
py -0p
py -3.14 --version
```

Install Python 3.14 with the Python Launcher, then retry. The launcher also
supports Python 3.13 and 3.11 as fallbacks.

### The existing `.venv` uses the wrong Python version

Check it first:

```powershell
.\.venv\Scripts\python.exe --version
```

If it is older than Python 3.11 or no longer works, remove only the `.venv`
folder and run `run_windows.bat` again. The launcher will recreate the local
environment without changing the project files.

### A dependency is missing

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Port 8501 is already in use

Stop the previous Streamlit terminal with `Ctrl+C`, or run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502
```

### API authentication fails

Confirm the maintainer entered their own active Gemini and Apify credentials.
Do not request that they send the key to another person.

### A post is unavailable

Open the direct URL in a browser. Deleted, private and unopenable posts are
removed. Restricted-but-viewable posts may require manual tagging.

### A short/share URL fails

Open it in the browser and copy the final direct post URL. See
`docs/LINK_COMPATIBILITY.md`.

### Tests fail

Copy the first complete traceback, current branch, commit and command used.
Ask Codex to diagnose before editing.

## 17. Clean-account rehearsal checklist

The handover passes only when the new account can independently:

- clone or fork the repository;
- start the app with the provided launcher;
- create its own virtual environment;
- enter its own API credentials;
- add both TikTok and Instagram posts;
- run tagging and complete Human Review;
- download all exports;
- run the automated tests;
- create a separate branch;
- make a small documentation change;
- review the diff;
- commit and push to its fork or test branch;
- open a draft pull request;
- explain where UI, tagging, Instagram and review-routing changes belong;
- explain that software tests do not prove model accuracy;
- recover from at least one documented setup error.

Record every step that required help. Improve this guide and repeat the
rehearsal until no undocumented help is required.

## 18. Final maintenance report template

```text
Change:
Branch:
Commit:
Pull request:

Reason:

Files changed:

Behavior changed:

Behavior intentionally unchanged:

Automated checks:

Manual smoke test:

Accuracy evaluation required: Yes / No

Known limitations:

Deployment result:

Rollback commit:
```
