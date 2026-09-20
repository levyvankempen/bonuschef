# Record the recognisability floor

## Why

Four changes shipped today altered how matching decides what to propose, and
the specs still describe the behaviour from before them. Two statements in
`recipe-catalogue` are now false, and the rule that replaced them is written
down nowhere.

This is the gap that matters most in a spec-driven repo: a spec that is merely
incomplete tells you less than it could, while a spec that is wrong tells you
something untrue with the same authority as the rest.

## What Changes

- **MODIFIED** "Only candidates of the same kind as the best one are proposed" —
  its unclassified-best scenario promised nothing would be narrowed. An
  unrecognisable best candidate now withholds the whole cohort.
- **MODIFIED** "Resolutions already recorded are re-checked" — the re-check
  judged form and department only, which both reported failures passed. It now
  applies the naming test, and withdraws unconditionally when a product is not
  the ingredient at all.
- **ADDED** "A candidate that is not recognisably the ingredient is not
  proposed" — the floor itself.

## Impact

Specs only. The behaviour is already live in v1.11.8 via #70 and #72.
