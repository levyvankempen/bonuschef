## Why

Clearance is scraped per shop, and the list of shops to scrape is read from the
accounts. So somebody who signs up and picks a shop nobody else uses has no
koopjes at all until the next hourly scrape happens to run - up to an hour of
an empty Laatste kans on their first visit, which is the visit that decides
whether they come back.

Nothing is broken. The scrape does pick up new shops on its own. It simply does
not know that somebody is waiting.

## What Changes

- Choosing a shop the warehouse has never scraped **starts the scrape**, rather
  than waiting for the schedule to come round.
- The person is told it is running and that the page will fill in, because a
  fire-and-forget job that says nothing is indistinguishable from one that did
  not start.
- Choosing a shop that has already been scraped starts nothing. The data is
  already there, and a run per shop change would let somebody queue work by
  toggling a dropdown - runs are serialised instance-wide, so that would hold
  the slot against the scrape that is actually due.
- A trigger that fails does not fail the shop change. The shop is saved either
  way; only the "we are fetching it now" becomes "it will appear within the
  hour".

## Capabilities

### Modified Capabilities

- `portal`: choosing a shop the system has not seen starts the work that
  fetches it, and says so; choosing one it already has does not.

## Impact

- `src/bonuschef/portal/rebuild.py` - one more fire-and-forget trigger beside
  the recipe rebuild that is already there.
- `src/bonuschef/portal/db.py` - a reader answering whether a shop has ever
  been scraped.
- `src/bonuschef/portal/profile_page.py` - the trigger on the save path.
- No new job, no schedule change, no pipeline change. `markdowns_refresh`
  already reads the shops from the accounts; this only asks it to run now.
