# v68.41.6 final unseen-validation candidate

## Decision

Gemini 3.1 Flash-Lite remains the recommended default. Gemini 3.5 Flash is optional only when explicitly selected. Targeted evidence verification now stays on the selected model so model attribution and runtime remain predictable.

## Changes from v68.41.5

- Reuses the robust Gemini JSON decoder for verifier responses and retries malformed JSON safely.
- Removes verifier calls triggered only by a guardrail change or a known-confusion label pair.
- Lets optional verifier outages fail open while preserving deterministic hard review reasons.
- Recomputes review state after a confirmed/change decision so stale earlier-tier flags do not survive.
- Prioritises a clearly presented on-screen quote over incidental Fashion.
- Prioritises explicit joke, meme or funny-story purpose over incidental Lip Sync.
- Uses Celebrity Edits when a written fanfiction narrative explicitly concerns real idols or public figures.
- Prioritises literal visible `POV:` framing and asks Gemini to preserve that cue in Content Details.
- Treats explicit Singapore CCA/school-life wording as Slice of Life without overriding teacher quotes or instructional posts.
- Stops incidental clothing mentions from being treated as strong Fashion evidence.
- Avoids false Media/Infotainment review from a performance-only "Dance tutorial" phrase.
- Avoids a false motion-versus-non-motion conflict when Dance is already paired with Beauty or another supported secondary label.

## Honest limitations

- Local humour, mock-kiss animation and dance-as-joke intent may remain invisible when Gemini omits the decisive action from Narrative and Content Details.
- Hand-only choreography can remain ambiguous when temporal evidence is weak.
- The completed 24-post set is a targeted regression diagnostic, not an accuracy estimate. Only the separate unseen holdout can support a final accuracy figure and 95% margin of error.
