## Why

Vanavond does not answer "what shall I cook tonight". It answers "which product
is most discounted today", six times.

`saving_total` is the sum of each line's saving, and on live data **every one of
the 40 ranked recipes has exactly one discounted ingredient**. So the sum
collapses to a single line, which is a property of the product rather than of the
recipe: every recipe containing `biologische spekreepjes` scores exactly €2.00.
Ties break on `recipe_id`, which is why the bacon runs contiguously. Of the top
twenty for one shop, eleven were the same salmon and five were bacon.

The operator's report is the whole diagnosis: *"Seeing all recipes on Vanavond
with spekjes since spekjes are in laatste kans is unwanted. Moreover I don't even
like spekjes."* Two separate problems in one sentence - no variety, and no way to
say what you do not eat - and neither is solved by the other.

Three more findings from the same review:

- The saving is shown as a difference (`− €2.00`) and the two prices are behind a
  tap. A difference cannot be checked against a shelf, and checking against the
  shelf is what a person is doing while reading it.
- Vanavond carries an operator's console for every account: unresolved concepts,
  flagged matches, job names, and a button into the matcher.
- That console includes a real authorisation hole. `confirm_resolution` takes no
  account and writes a table with no account column, and the dialogs that reach
  it are not gated - so any invited person's guess at what an ingredient means
  silently changes the prices on everybody else's cards.

## What Changes

- **The alternatives are chosen for difference.** At most one recipe per
  discounted ingredient in the shortlist, filling up from the largest groups only
  if too few remain. "Meer met zalm (11)" reaches the rest through the ingredient
  control that already exists, rather than a second one.
- **The ingredient control moves above the answer, with its counts.** It is the
  page's table of contents and the only thing that answers "this is on offer,
  what do I cook with it". The counts are already fetched and discarded today.
  The free-text box moves into a popover: typing one-handed in a shop is the
  interaction being removed, and Recepten already owns name search.
- **The driving ingredient's two prices move onto the card face**, with the
  reference's age when it is no longer fresh.
- **A person can exclude an ingredient permanently**, from the card where the
  dislike is felt and reviewably on Profiel, keyed on the retailer's concept.
  Because one food answers to many names - eight concepts contain "spek" in one
  shop - excluding one says what else it hides before confirming.
- **The operator's console moves to Beheer**, except the credential failure,
  which stays where the prices are because it means they may be wrong.
- **Correcting a match becomes an operator's act**, gated in the function and not
  offered to anyone else.
- **The coverage caption gains what it hides**, which the honesty requirement
  demands the moment the shortlist is narrower than the ranking.

Not in this change: ranking on saving per serving. It needs a mart change and a
dbt build, and choosing for difference removes most of the pain it would address.

## Capabilities

### Modified Capabilities

- `portal`: alternatives are chosen for difference rather than magnitude; the
  card shows what a discounted product costs now and ordinarily; a person can
  exclude an ingredient they do not eat; changing a shared match is an operator's
  act; diagnostics move to the operator's surface while a failure that changes
  what to buy stays with the prices; and the page says what it is not showing.

## Impact

- `src/bonuschef/portal/tonight_page.py` - the shortlist, the control order, the
  card's prices, the exclusion entry point, the console's removal.
- `src/bonuschef/portal/profile_page.py` - reviewing and reversing exclusions.
- `src/bonuschef/portal/monitor_page.py` - the console's new home.
- `src/bonuschef/portal/review.py`, `db.py` - the operator gate, the exclusion
  table and its readers.
- `src/bonuschef/portal/schema.py` - one statement for the exclusions.
- No mart change, no pipeline change, no new query shape on the hot path.
