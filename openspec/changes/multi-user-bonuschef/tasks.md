# Tasks

## 1. Catalogue content (independent of everything below)

- [ ] 1.1 Adopt R-R1193780, quiche with broccoli and smoked salmon
- [ ] 1.2 Adopt R-R1193969, tacos with kibbeling, red cabbage and aioli
- [ ] 1.3 Withdraw zuurkoolstampot from the catalogue
- [ ] 1.4 Confirm the two new recipes resolve their ingredients, and review
      whatever the matcher withholds rather than leaving it unresolved

## 2. Accounts

- [ ] 2.1 Accounts table: username, password hash, created, last sign-in
- [ ] 2.2 Password hashing with a slow salted algorithm, and a test that
      asserts identical passwords do not produce identical stored values
- [ ] 2.3 Sessions in Postgres, opaque token, idle lifetime, revocable
- [ ] 2.4 One entry point that gates every page, so a new page cannot be
      added unguarded by omission
- [ ] 2.5 Failed sign-in: uniform response for unknown user and wrong
      password, attempts recorded, repeated failures slowed
- [ ] 2.6 Operator path to create an account and force a password change on
      first sign-in
- [ ] 2.7 Sign out

## 3. A store belongs to a person

- [ ] 3.1 Store on the account; `AH_STORE_ID` becomes the default for an
      account that has not chosen, not the source of truth
- [ ] 3.2 Every clearance-dependent reader takes the signed-in account's store
- [ ] 3.3 An account with no store is asked to choose, and clearance figures
      are withheld rather than borrowed from another store
- [ ] 3.4 Test that two accounts with different stores read different
      clearance for the same recipe

## 4. Per-user Albert Heijn credentials

- [ ] 4.1 Encrypted credential column, key from the environment and not from
      the database
- [ ] 4.2 Connect flow: a person authenticates their own AH account
- [ ] 4.3 Disconnect: credential deleted, clearance stops, recipes untouched
- [ ] 4.4 Account settings state what is held, what it is used for, and when
      it was last used
- [ ] 4.5 Assert no credential reaches logs, run output or error text
- [ ] 4.6 One account's expired token does not affect the others

## 5. Clearance becomes per store

- [ ] 5.1 Clearance ingestion fans out over the distinct stores of accounts
      holding a credential
- [ ] 5.2 Clearance tables carry the store dimension explicitly
- [ ] 5.3 Bonus ingestion stays national and stays a single fetch
- [ ] 5.4 An account without a credential sees bonus prices and a stated
      reason for absent clearance

## 6. Recipes: shared catalogue, private everything else

- [ ] 6.1 Saved-recipe join table per account
- [ ] 6.2 Last-made date per account
- [ ] 6.3 Notes per account
- [ ] 6.4 Per-account ingredient overrides layered over the shared recipe on
      read, rather than forking the recipe
- [ ] 6.5 Adopting a recipe another account already added does not duplicate
      it and does add it to this account's collection
- [ ] 6.6 Test that one account's edit is invisible to another

## 7. The recipes page

- [ ] 7.1 Cards with title, cost where known, and last-made date
- [ ] 7.2 Filter to recipes with an ingredient on offer today for this
      person's store, stating what each matched on
- [ ] 7.3 Filter falls back to promotions alone when clearance is not current,
      and says so
- [ ] 7.4 Empty states that read as answers rather than as failures: nothing
      saved, nothing on offer, cost incomplete
- [ ] 7.5 Save a recipe from the page that recommended it
- [ ] 7.6 Edit a saved recipe

## 8. Before friends are invited

- [ ] 8.1 Confirm the portal is reachable only over the tailnet
- [ ] 8.2 Write down, for the people being invited, what is stored about their
      Albert Heijn account and how to end it
- [ ] 8.3 Check that a restart does not sign everyone out
