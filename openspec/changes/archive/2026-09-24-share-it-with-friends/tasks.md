## 0. What was already there

Planning this found the throttle already built and tested: `sign_in_attempts`
in Postgres, `MAX_FAILURES = 5` inside a 15-minute `LOCKOUT`, the check made
*before* the password is looked at, failures recorded for unknown usernames too
so the throttle is not an existence oracle, and 44 tests across
`test_accounts.py` and `test_registration.py` covering it.

It ships unspecified: no requirement in `openspec/specs/` mentions throttling at
all, and the one that governs registration says the opposite of what runs. So
sections 1-3 of this change are the spec catching up with the code, not new code.

- [x] 0.1 Confirm the throttle persists in Postgres rather than in process.
- [x] 0.2 Confirm a correct password is refused during a lockout.
- [x] 0.3 Confirm an unknown username is throttled identically to a real one.
- [x] 0.4 Confirm registration is closed when no code is configured.

## 1. Say what the sign-in wall actually does

- [x] 1.1 Add the throttling requirement to `user-accounts`, describing the
      behaviour that ships.
- [x] 1.2 Add the one test the existing set does not have: that a locked account
      and an absent one are refused with the *same message*, not merely both
      refused.
- [x] 1.3 Add the test that locking one account leaves others able to sign in.

## 2. Reconcile registration with what ships

- [x] 2.1 Rewrite the requirement so that holding the invitation is the
      invitation, and closed-when-unconfigured is the rule it keeps.
- [x] 2.2 Add the test that rotating the code stops the old one while leaving
      existing accounts able to sign in.

## 3. Publish the portal, and only the portal

- [x] 3.1 Enable Funnel on 8501. Report to the operator anything that needs the
      Tailscale admin console, rather than working around it.
- [x] 3.2 Verify the address answers over HTTPS from outside the tailnet, with
      a valid certificate, and that the gate is on. NOTE: the sign-in *form*
      could not be driven end to end - Streamlit renders over a websocket and
      the browser extension was not connected - so this is verified as
      `gate.sign_in_required() is True` on the running container plus the
      existing gate tests, not by a real session. Opening it once on a phone is
      the step nobody has done.
- [x] 3.3 Verify Dagster and Postgres are still bound to loopback and named in
      no serve config, *after* publishing.
- [x] 3.4 Verify the throttle against the published address: a run of wrong
      passwords is refused, and the refusal does not reveal the account.
- [x] 3.5 Write the path and the one-command withdrawal into docs/deployment.md.

## 4. Verify for real

- [x] 4.1 Full suite green; ty and ruff clean.
- [x] 4.2 Mutate the threshold and the lockout-beats-correct-password rule and
      confirm a test fails for each.
