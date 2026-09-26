## 1. Answer whether a shop has been scraped

- [x] 1.1 Add a reader returning whether the warehouse holds clearance for a
      shop, reading the same table Laatste kans reads.
- [x] 1.2 Test it answers false for an unknown shop and true for a known one.

## 2. The trigger

- [x] 2.1 Add `start_store_first_scrape()` to `rebuild.py` beside the recipe
      rebuild, with the same contract: never raises, returns a run id.
- [x] 2.2 On a warning path, say the shop is saved and the data will arrive on
      the next scheduled scrape.

## 3. Wire it to the save

- [x] 3.1 After a successful shop change, trigger only when the shop has no
      clearance yet.
- [x] 3.2 Say it is running, in the message the page already shows after a save.

## 4. Tests

- [x] 4.1 Picking a shop with no clearance starts the job.
- [x] 4.2 Picking a shop that has clearance starts nothing.
- [x] 4.3 Changing repeatedly between scraped shops starts nothing.
- [x] 4.4 A trigger that raises still saves the shop, and the message says when
      the data will appear rather than that the save failed.
- [x] 4.5 Mutate the has-clearance guard and confirm a test fails.

## 5. Verify

- [x] 5.1 Full suite, ruff and ty clean.
- [x] 5.2 After deploy, confirm on the running container that the guard answers
      correctly for a known and an unknown shop.
