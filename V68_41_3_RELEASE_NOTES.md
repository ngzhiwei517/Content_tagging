# v68.41.3 accuracy-hardening candidate

## Scope

This candidate starts from the exact v68.41.2 ZIP and changes only general UGC Creative Type classification, evidence verification, review routing, prompts, tests and version metadata. The v41-style workflow and detailed drama logic remain unchanged.

## Reusable changes

- Dance now accepts explicit rhythmic, repeated or coordinated hand/arm and upper-body choreography. Seated or close-up framing can qualify; generic casual gestures do not.
- Quotes takes priority when the post visibly presents an attributed saying or quote format. Reflection or Relationship may remain secondary meanings.
- Lyrics Translation requires explicit bilingual or translated lyric evidence.
- Explicit fictional/drama edits, real-person celebrity fan edits, OOTD/fit checks and relationship-purpose descriptions are reconciled with their Creative Type.
- Travel requires trip/destination/tourism purpose, while ordinary local scenery is routed for review.
- A fan/audience recording of the original live performer is routed for review when labelled Cover.
- Explicit humour without Comedy and camera-angle-only POV are routed for review instead of force-corrected.

## Known limitations

- Subtle hand-only dance trends still depend on Gemini describing the movement as rhythmic, repeated, coordinated or choreographed. If the model describes only generic gestures, the row may remain Lip Sync and should be reviewed.
- Local-language humour may be visually indistinguishable from ordinary Slice of Life without dialogue/audio understanding. The app routes explicit contradictions but cannot guarantee every joke is detected.
- POV boundaries can be subjective when the human label is based only on framing rather than an explicit scenario.
- Some supplied human labels remain marked for adjudication where the visible evidence supports more than one reasonable taxonomy interpretation.
- The targeted regression set measures whether reported failure modes are handled. It is not an unbiased accuracy estimate. Use the separate unseen holdout sheet for accuracy and margin-of-error reporting.

## Validation

- Python compile gate passed for the app and backend modules.
- Full local unit suite passed: 343 tests, including 16 new v68.41.3 cross-market regression tests.
- Streamlit headless health check passed.
- Final archive was extracted and the same compile gate and 343-test suite passed from the packaged files.
