# Open Production Decisions

Streamlit Secrets is the current credential store, and detailed drama analysis
already runs conditionally after a drama label is confirmed. The following
decisions remain open before production use:

1. What authentication and role model should protect batches, recovery links,
   dashboards and internal QA exports?
2. What shared job queue or database lease should coordinate paid fallback
   across multiple Streamlit replicas and concurrent users?
3. Who owns Apify hard limits, warning thresholds, private alert delivery and
   investigation of unusual usage?
4. Which persistent checkpoint backend and retention period should be approved,
   and who will perform the live restart/redeployment recovery test?
5. Who approves reviewed rows before they update the Creative Knowledge Base?
6. Will the GitHub repository remain private, or must learned creator/track KB
   files remain outside the repository and be regenerated locally?
7. Who owns monitoring external Actor pricing, entitlement and output-schema
   changes?
8. What fresh locked TikTok and Instagram samples and acceptance criteria will
   be used for formal accuracy evaluation?
