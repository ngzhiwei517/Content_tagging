# Creative Knowledge Base

The app loads approved reusable rules from this directory when the corresponding JSON files exist.

Committed rule files:

- `hashtag_rules.json`
- `keyword_rules.json`
- `market_rules.json`
- `url_type_rules.json`

Local/private learned files:

- `creator_rules.json`
- `track_rules.json`
- `metadata.json`

The local files may contain creator usernames, track patterns and source-workbook metadata learned from reviewed campaign data. They are included in the internal runtime ZIP to preserve the tested behaviour, but `.gitignore` prevents accidental GitHub publication.

Use the `.example.json` files to understand the structure. Do not auto-learn from raw AI outputs and do not use exact TikTok URL-to-label memory.

