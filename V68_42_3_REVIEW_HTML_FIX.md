# v68.42.3 review-card HTML fix

This isolated candidate fixes raw `<div>` markup appearing beneath Instagram
metrics on the Review page.

When Instagram returned both Shares and Saves, the optional missing-metrics
message was empty. Markdown could then treat the remaining indented HTML lines
as a code block. The review information card now uses Streamlit's pure HTML
renderer, so an empty optional message cannot expose markup.

The Instagram metrics adapter, TikTok classifier, drama logic, taxonomy and
review decisions are unchanged.
