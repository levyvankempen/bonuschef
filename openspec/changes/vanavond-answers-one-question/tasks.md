## 1. The operator gate, first, because it is a hole

- [x] 1.1 Refuse `confirm_resolution` for an account that is not an operator -
      in the function, not only by hiding the control.
- [x] 1.2 Stop offering "Klopt niet" and "Ingrediënten koppelen" to anyone else.
- [x] 1.3 Test that a non-operator reaching the correction writes nothing, and
      that an operator still can.

## 2. Alternatives chosen for difference

- [x] 2.1 Pick the shortlist by driving ingredient: first recipe per ingredient
      in rank order, filling from the largest groups if too few remain. Lead
      unchanged.
- [x] 2.2 Offer "Meer met <ingredient> (n)" by setting the existing pill.
- [x] 2.3 Test: many recipes sharing one ingredient yield cards driven by
      different ones; the lead is still the best overall; too few groups still
      fills the page; the drill-down sets the pill rather than a second control.

## 3. The ingredient control above the answer

- [x] 3.1 Move the pills above the lead card and render their counts.
- [x] 3.2 Demote the free-text box into a popover.
- [x] 3.3 Test that arriving shows what is on offer with counts, and that
      naming an ingredient still works from the popover.

## 4. The two prices on the card face

- [x] 4.1 Render the driving ingredient's current and ordinary price on the card,
      from the row the badge already reads. No new query.
- [x] 4.2 Say the reference's age when it is no longer fresh.
- [x] 4.3 One shared was/now renderer beside `offers.euro`, so Vanavond and
      Recepten cannot render one fact two ways.
- [x] 4.4 Test both prices appear without opening the list, that a stale
      reference is marked, and that no new query is issued.

## 5. Excluding food

- [x] 5.1 Add `account_ingredient_blocks` to `schema.py`'s statements, keyed
      `(account_id, concept_id)`, cascading on account deletion so the invitee
      promise stays true.
- [x] 5.2 Readers: what this account excludes, and which recipes contain it.
      Uncached, bounded.
- [x] 5.3 Exclude on the card, offering the sibling concepts by name before
      confirming.
- [x] 5.4 Review and reverse on Profiel.
- [x] 5.5 Filter before ranking is consulted, in `_render_answer`.
- [x] 5.6 Test: an excluded ingredient's recipes disappear however cheap; one
      account's exclusion leaves others alone; siblings are offered; removal
      brings recipes back; excluding everything says why rather than reading as
      nothing on offer.

## 6. The console moves to Beheer

- [ ] 6.1 Move pipeline detail, flagged concepts, the unresolved count and the
      review entry to Beheer.
- [ ] 6.2 Keep the credential failure on Vanavond.
- [ ] 6.3 Test that Vanavond's first element after its title is a recipe or a
      control, and that the operator can still reach every moved number.

## 7. Honesty about the shortlist

- [x] 7.1 Say how many were ranked, how many are shown, and why the rest are not.
- [x] 7.2 Test the caption accounts for both dedup and exclusions.

## 8. Verify

- [ ] 8.1 Full suite, ruff, ty clean.
- [ ] 8.2 Mutate each new rule and confirm a test fails.
- [ ] 8.3 After deploy, check on the running container that the shortlist is
      diverse for a real store and that a non-operator cannot correct a match.
