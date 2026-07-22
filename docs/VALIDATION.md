# Validation and Accuracy Reporting

## Locked baseline result

The final blind Core-100 test was run on v66.6 immediately before v67:

| Metric | Result |
|---|---:|
| Posts tested | 100 |
| Correctly excluded | 7 |
| Evaluable posts | 93 |
| Exact top-two legacy benchmark agreement | 68/93 (73.1%) |
| Conservative adjudicated semantic acceptance | 89/93 (95.7%) |
| Broad acceptance including two borderline rows | 91/93 (97.8%) |
| Clear remaining errors | 2/93 (2.2%) |
| Human-reviewed rows | 9/93 (9.7%) |

## Interpretation

The exact benchmark uses one historical label per post, while the product accepts up to two labels and considers the result acceptable when at least one label is materially correct. Twenty-one of the 25 exact disagreements were defensible alternatives. Two were borderline tone cases and two were clear Lyrics contradictions.

## Required wording

Use:

> On a locked blind test of 100 posts, 93 posts were available for evaluation. The final human-assisted workflow achieved 95.7% adjudicated semantic acceptance, with a 2.2% clear-error rate. Exact agreement with the legacy single-label benchmark was 73.1%.

Do not call 95.7% pure AI-only accuracy. The v66.6 QA export overwrote original labels after human review, so AI-only performance could not be reconstructed.

## What v67 changes

v67 preserves original and final labels separately and targets the two Lyrics contradictions. A future fresh holdout can therefore report:

- automated AI/guardrail accuracy before review;
- review routing recall;
- final human-assisted workflow accuracy;
- edit rate and error-correction rate.

Do not publish a new v67 blind accuracy number until that fresh holdout is completed.

## Instagram Reels directional pilot

Instagram was checked separately because the TikTok benchmark cannot be reused as Instagram evidence.

| Measure | Directional result |
|---|---:|
| Source Reels supplied | 60 |
| Available Reels | 49 |
| Unavailable/removed | 11 |
| Manually adjudicated pilot | 18 |
| Accepted/defensible | 17/18 (94.4%) |
| Exact-label agreement | 16/18 (88.9%) |
| Difficult cases accepted | 11/12 |
| Normal controls correct | 6/6 |
| Confirmed errors | 1 |
| App-routed human review | 3/49 available Reels |

This is an encouraging directional pilot, not a formal Instagram accuracy claim. The 18 reviewed Reels deliberately included difficult examples and are too few to support a narrow population estimate. If treated like a random sample, the approximate 95% interval for 17/18 would still be wide (about 74.2% to 99.0%).

The confirmed error was scenic yoga content labelled Dance/Travel instead of Fitness. Cycling content also showed that scenic exercise can reasonably attract Travel even when Fitness is a more useful primary label. Report the current Instagram limitation as:

> Scenic exercise content may be classified as Travel or Dance instead of Fitness.

Public metric coverage is a separate issue from tagging quality. The full-metrics actor can return public Views, Likes, Comments, Shares and Saves when available. Actor failure or missing platform fields trigger the broad fallback actor, and unavailable Shares/Saves remain blank and labelled `Not available`.
