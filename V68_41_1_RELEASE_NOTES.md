# v68.41.1 multilingual Apple/iTunes candidate

- Preserves Chinese, Thai, Korean, Japanese and other Unicode scripts during track-title matching.
- Searches a short regional storefront fallback list based on the title script.
- Keeps successful Apple catalogue results in the existing bounded 24-hour cache.
- Keeps failed or unavailable searches as `Unconfirmed` rather than treating the user's track as invalid.
- Preserves the existing English matching path and optional `Artist - Track` disambiguation.

## Verification

- `python -m py_compile app.py drama_analysis.py final_update2_adapter.py`
- `python -m unittest discover -s tests -p 'test_*.py'` — 312 tests passed.
- Streamlit health endpoint returned HTTP 200.
- Live Apple catalogue checks matched:
  - `漫步香港1999` in the Taiwan storefront.
  - `ตั้งใจจะโสด` in the Thailand storefront.
  - `아크라포빅` in the Korea storefront.

## Limitation

Apple catalogue availability and returned metadata can still vary by region. A missing match remains `Unconfirmed`, and drama audio version should remain `Unknown` unless there is sufficient comparison evidence.
