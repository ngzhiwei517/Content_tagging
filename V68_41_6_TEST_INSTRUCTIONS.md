# Test v68.41.6

## Final unseen holdout

1. Start this isolated local candidate.
2. Upload only the final blinded 97-post holdout provided separately.
3. Choose **Tag every link** and keep all available posts.
4. Leave **Analysis model** on **Gemini 3.1 Flash-Lite — recommended**.
5. Run tagging and complete every genuinely required human-review decision.
6. Do not use AI Suggest when scoring; make the human decision from the post evidence.
7. Download the Review / QA Report and return it to Codex.

Only the 97 unseen rows count toward the final accuracy and confidence interval. The earlier 24-post diagnostic is excluded.

Report AI-only exact preferred-label agreement, semantic acceptance, clear-error rate, human-review rate, runtime, and `95% MoE = 1.96 × sqrt(p × (1-p) / n)` using the actual available-row denominator.
