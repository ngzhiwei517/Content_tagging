# v68.13 Animal Dance Test

## Changed rule

Dance is based on visible action rather than the subject's species. A person, animal, or animated character may receive Dance when the evidence explicitly describes rhythmic or choreographed movement.

Ordinary pet movement, posing, walking, rolling, or general cuteness must not trigger Dance.

## Quick manual check

Re-run the puppy post that previously returned only `Slice of Life`.

Expected result:

- `Dance` is included because the post describes rhythmic, dance-like paw movement to music.
- The post is not flagged merely because the dancer is an animal.
- A second supported label may remain when it describes a genuine secondary theme.

## Regression checks

- A hamster rolling in dirt remains `Slice of Life` / `Comedy`, not Dance.
- A person stepping forward and backward only to show clothing remains Fashion, not Dance.
- Static animal images and ordinary pet motion remain non-Dance.
