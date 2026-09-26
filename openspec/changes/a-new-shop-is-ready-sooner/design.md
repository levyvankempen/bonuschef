## Context

See proposal.md. What already exists:

`markdowns_refresh` reads the shops to scrape from the accounts table, so a new
shop needs no configuration - only a run. `portal/rebuild.py` already holds one
fire-and-forget trigger (`start_recipe_rebuild`) with the right shape: it never
raises, it returns a run id so the caller can say something, and it warns rather
than failing the action that prompted it.

Runs are serialised instance-wide (`max_concurrent_runs: 1`), which is why "only
for a shop nobody has scraped" is a correctness property and not a nicety.

## Goals / Non-Goals

**Goals:**

- A new person's first Laatste kans has something on it.
- No new job, schedule, asset or config.

**Non-Goals:**

- Not blocking the save while the scrape runs. That takes a minute and the
  person is on the profile page, not the shop floor.
- Not polling to completion or rendering progress. `render_rebuild_status`
  exists for the recipe rebuild and could be extended later; it is not needed to
  answer "is anything happening".
- Not a rebuild of the recipe marts. The scrape loads clearance and the dbt step
  in the same job publishes it.

## Decisions

### Trigger on "this shop has never been scraped", not on "the shop changed"

Runs are serialised for the whole instance. A run per selection would let
somebody queue a queue by changing a dropdown, and the queued work would sit in
front of the hourly scrape, which is unbackfillable. Keying on the absence of
data makes the trigger idempotent in the only sense that matters: once the shop
has been scraped once, no amount of switching starts anything.

*Alternative considered:* rate-limit the trigger per account or per minute.
Rejected as a second mechanism answering a question the data already answers.

### Ask the warehouse, not the scraper

"Has this shop been scraped" is answered by whether `fct_store_clearance` holds
rows for it. That is the same table Laatste kans reads, so the trigger fires
exactly when the page would otherwise be empty - which is the condition being
fixed, rather than a proxy for it.

### The trigger never fails the save

The shop is the person's choice and is theirs whether or not a scraper can be
reached. A failed trigger downgrades the message from "we are fetching it" to
"it will appear within the hour", which is what would have happened anyway.

## Risks / Trade-offs

- **A shop with genuinely no clearance ever** - a small shop AH never marks down
  - would be re-triggered on every selection, because the absence of rows is
  indistinguishable from never having looked. In practice the scrape covers all
  accounts' shops each hour, so the second selection finds rows from the
  scheduled run; and a shop that never yields a single markdown across an hourly
  scrape is hypothetical rather than observed. Worth revisiting if it appears.
- **The person waits a minute for something they were told is running.** Better
  than an empty page with no explanation, and the alternative - blocking the
  save - is worse.
