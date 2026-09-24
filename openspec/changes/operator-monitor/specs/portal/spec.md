## ADDED Requirements

### Requirement: An operator can see the state of what they run

The portal SHALL offer an operator a view of the accounts on it: for each, when
it was made, when it was last used, which shop it is connected to, and what it
has saved.

The view SHALL be reachable only by an operator. It SHALL NOT be listed for
other accounts, and SHALL refuse to render for them even if its address is
reached directly - a page hidden only by being unlinked is not access control.

It SHALL distinguish an account that has never been used from one that is
merely quiet, and an account with no shop from one whose shop is simply not
where the operator expected. Those are the two states that mean somebody got
stuck rather than lost interest.

#### Scenario: The operator opens the view

- **WHEN** an operator opens it
- **THEN** every account is listed with when it was created, when it was last used, its shop, and how many recipes it has saved

#### Scenario: Another account tries to reach it

- **WHEN** an account that is not an operator reaches the view's address directly
- **THEN** it does not render, and says nothing about what it would have shown

#### Scenario: It is not offered to people who cannot use it

- **WHEN** an account that is not an operator is signed in
- **THEN** the view is not listed among the places they can go

#### Scenario: An account that never got started

- **WHEN** an account has been created but never signed in, or has signed in but never chosen a shop
- **THEN** that is shown as its own state rather than as a blank or a zero

#### Scenario: What an account has saved

- **WHEN** the operator looks at one account
- **THEN** the recipes it has saved are named, with when each was saved and when it was last cooked

#### Scenario: No credential is shown

- **WHEN** any account is displayed
- **THEN** no password and no password hash appears anywhere on the page
