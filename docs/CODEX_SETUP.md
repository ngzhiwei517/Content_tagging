# Codex Setup

Open Codex from this repository root, where `app.py`, `AGENTS.md` and `docs/` are visible.

Recommended first prompt:

```text
Read AGENTS.md and docs/PROJECT_CONTEXT.md first. Do not edit code yet. Summarize the current v68.9 architecture, accepted UI baseline and safest next change.
```

For implementation work, ask Codex to preserve the six-step UI, label audit fields, selection/removal rules and marketing-versus-QA export separation. Require syntax and unit tests before packaging.

Never paste or commit real Gemini keys, Apify tokens, raw downloaded media, private datasets or internal answer keys.
