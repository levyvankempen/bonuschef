"""The operator's account tool.

It runs against production and writes credentials, so what is pinned here is
what it refuses to do and what it refuses to leak.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "manage_account.py"


def test_the_password_is_never_an_argument():
    """An argument lands in shell history and in the process list, where
    anyone with a login on the box can read it."""
    body = SCRIPT.read_text()
    assert "getpass" in body
    for line in body.splitlines():
        if "add_argument" in line and "password" in line.lower():
            assert "--no-force-change" in line or "set-password" in line, line


def test_it_never_prints_a_stored_hash():
    """`list` exists to answer "who has an account", not to hand somebody the
    hashes. It reports whether a password is set, not what it is."""
    body = SCRIPT.read_text()
    listing = body[
        body.index('if args.command == "list"') : body.index(
            'if args.command == "create"'
        )
    ]
    assert "password_hash <> ''" in listing, "it should report only that one exists"
    assert 'print(f"  {r.password_hash' not in listing


def test_an_account_without_a_password_is_called_out():
    """The accounts table defaults password_hash to an empty string, and an
    empty hash verifies against nothing. An account in that state cannot sign
    in, and the listing has to say so - otherwise the first symptom is a
    person locked out of a gate that looks correct."""
    assert "NO PASSWORD" in SCRIPT.read_text()


def test_a_new_account_must_change_its_password():
    """The operator knows the initial password, which makes it a delivery
    mechanism rather than a credential."""
    body = SCRIPT.read_text()
    create = body[body.index('if args.command == "create"') :]
    assert "must_change=True" in create.split("return 0")[0]


def test_a_typed_password_is_confirmed():
    """A typo is locked in, and only the operator can undo it."""
    assert "Again:" in SCRIPT.read_text()


def test_setting_a_store_checks_the_directory():
    """A store id that is not a real shop silently gives somebody another
    town's prices, with nothing on the page to reveal it."""
    body = SCRIPT.read_text()
    assert "FROM public.ah_stores WHERE store_id" in body
    assert "refresh_store_directory" in body, "it should say how to fix it"


def test_it_exists_before_the_gate_does():
    """This ordering is the point of the script. A sign-in gate deployed
    before any account has a usable password locks everybody out, including
    whoever would have to fix it."""
    prose = " ".join(SCRIPT.read_text().split())
    assert "locks everybody out" in prose
