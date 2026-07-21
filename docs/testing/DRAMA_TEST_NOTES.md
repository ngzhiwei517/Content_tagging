# v68.16 automatic drama enrichment — local test candidate

This package is based on the accepted v68.15 General UGC app. It is a local
candidate only and is not intended to replace the demo deployment yet.

## What changed

- There is no General/Drama selector.
- Every post follows the existing General UGC tagging and guardrail pipeline.
- A second drama pass runs only when the final Creative Type contains
  `Movie/Tv/Drama Edits`.
- The detailed pass uses the recurring families found in the supplied MY/TH
  datasets: Drama Edit, CP Edit, Entertainment News, Anime Edit,
  Actor/Actress Carousel, Drama Carousel, Behind-the-Scenes Edit, K-pop Show
  Cut, Actor/Actress Daily Vlog, POV and Other. Up to two categories are
  allowed for genuine combinations.
- BL/GL/general is stored separately from the content category. Long-form and
  Short-form Drama are the only drama formats; Scene Compilation and Fan Edit are
  not used as drama formats.
- Review shows conditional fields for `Movie/Tv/Drama Edits`. Human edits are
  saved directly and are not overwritten by another model call.
- Drama details are kept as one field per line inside Content Details. The final
  marketing CSV/XLSX does not add duplicate drama columns.
- The campaign song title is enough for Apple/iTunes comparison. Artist is an
  optional disambiguator and does not need a separate input field.
- Campaign Song Match is not shown to users. Audio Version first uses explicit
  TikTok speed/remix metadata, then compares the downloaded TikTok audio with
  an Apple/iTunes preview of the entered track using tempo and chroma/DTW
  alignment. A clean exact TikTok sound-title match can still identify
  Original. A moderate original-leading match is also shown as Original.
  Rows stay Unknown when the preview cannot be found or the audio segments do
  not align strongly enough.
- Chinese short-form/vertical web drama is normalized to Short-form Drama.
- Explicit K-pop interview, variety/reality-show, broadcast and member-banter
  clips route to Movie/Tv/Drama Edits and receive the K-pop Show Cut detail
  category. Interview-led montages do not become Dance merely because they
  discuss dance challenges or include supporting choreography clips. Ordinary
  idol stage/photo fan montages remain Celebrity Edits.
- Real actor/actress daily-life montages with clear casual, pet, studio,
  activity or travel-lifestyle evidence route to Actor/Actress Daily Vlog.
  A generic celebrity fan montage still remains Celebrity Edits, and Dance is
  removed from a lifestyle montage only when explicit choreography is absent.
- Final CSV, All Posts and Links Only preserve the uploaded/pasted row order.
- Fictional drama scene montages resolve to Drama Edit. Real-actor interviews,
  role reflections, livestream updates and wellbeing coverage resolve to
  Entertainment News; an ordinary celebrity fan montage does not.

## Suggested first test

1. Run the app normally with `streamlit run app.py`.
2. Upload a small mixed file containing both drama edits and normal UGC posts.
3. Choose **Tag every link** so every row is checked.
   Enter the campaign track name for pasted links; uploaded rows should include
   a Track/Track Name column when Audio Version needs to be checked.
4. Confirm normal UGC rows are unchanged.
5. For rows labelled `Movie/Tv/Drama Edits`, confirm the Content Category is
   appropriate and only relevant detail lines are shown. Anime must not be
   General Drama; Entertainment News must not show drama type or format.
6. On Review, change one suitable row to `Movie/Tv/Drama Edits`, choose its
   detailed category/categories, correct the visible fields, and save it.
7. Download the XLSX/CSV and verify the pasted order is unchanged and the
   drama information appears only inside Content Details.

Expected conservative behaviour: uncertain country, title or format should
show `Unknown` instead of a guess. The first tagging run may be slower while
the bundled audio-analysis libraries initialise. Strong audio matches are
labelled automatically, moderate original-leading matches become `Original`,
and only close or contradictory comparisons go to human review. Weak or
unusable comparisons remain `Unknown` without creating review work.
