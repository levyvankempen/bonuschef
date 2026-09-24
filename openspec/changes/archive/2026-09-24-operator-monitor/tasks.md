## 1. The readers

- [x] 1.1 Add a cached reader returning one row per account: username, whether
      operator, created, last sign-in, last seen (from the sessions table, not
      the sign-in column), store id and store name, and how many recipes saved.
- [x] 1.2 Add a cached reader returning one account's saved recipes with when
      each was saved and last made.
- [x] 1.3 Neither reader selects `password_hash`. Test that the SQL does not
      mention it.
- [x] 1.4 Test that "last opened" comes from the sessions table, because
      `last_sign_in_at` answers a different question.

## 2. The page

- [x] 2.1 Add `monitor_page.render_monitor`, listing every account with its
      activity, its shop by name, and its saved recipes.
- [x] 2.2 Render "never signed in" and "no shop chosen" as their own words
      rather than as a blank or a zero.
- [x] 2.3 Refuse to render for an account that is not an operator, checked
      inside the render function itself.
- [x] 2.4 Register it in `app.py` only for an operator.

## 3. Tests

- [x] 3.1 An operator sees every account, their shops and their saved recipes.
- [x] 3.2 A non-operator calling `render_monitor` directly gets a refusal and
      no data - the page must not rely on being unlinked.
- [x] 3.3 A non-operator's navigation does not list the page.
- [x] 3.4 An account that never signed in, and one with no shop, each read as
      their own state.
- [x] 3.5 No password or hash appears in anything the page renders.

## 4. Verify

- [x] 4.1 Full suite, ruff and ty clean.
- [x] 4.2 Mutate the operator check and confirm a test fails.
- [x] 4.3 After deploy, confirm on the running container that the page renders
      for an operator and refuses for a non-operator.
