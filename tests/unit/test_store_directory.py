"""Choosing a store by name rather than by number.

A store is an integer everywhere in this system. That was fine while one
operator knew 1876 meant their own shop; asking somebody else to type "1661"
is not a way to pick a supermarket, and a typo silently gives them another
town's prices with nothing on the page to reveal it.
"""

from contextlib import contextmanager

import pytest

from bonuschef.utils.ah_stores import Store, fetch_stores


class FakeManager:
    """Answers the stores query from pages, and records what it was asked."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls: list[dict] = []

    def graphql(self, query, variables):
        self.calls.append(dict(variables))
        page = self.pages.pop(0) if self.pages else []
        return {"storesSearch": {"result": page}}


def _rows(*pairs):
    return [{"id": i, "name": n} for i, n in pairs]


def test_it_reads_every_page():
    """1,199 stores against a server-chosen page size. Reading one page would
    offer a person the first hundred shops in the country and no others."""
    manager = FakeManager(
        _rows((1, "Amsterdam Osdorp")),
        _rows((2, "Tiel Kamperfoelie")),
        [],
    )
    stores = fetch_stores(manager=manager)
    assert [s.store_id for s in stores] == [1, 2]
    assert len(manager.calls) == 3, "it must ask again until a page comes back empty"


def test_it_advances_by_what_it_received():
    """Not by the page size it asked for. A short page would otherwise skip
    the stores between what arrived and what was requested."""
    manager = FakeManager(_rows((1, "A"), (2, "B")), [])
    fetch_stores(manager=manager)
    assert manager.calls[1]["start"] == 2


class EndlessManager:
    """Never runs out of pages.

    A finite fake cannot test a loop ceiling: it terminates because it ran out
    of answers, so the test passes whether or not the ceiling exists. Proved
    by mutation - with a 199-page fake, deleting the bound changed nothing.
    """

    def __init__(self):
        self.calls = 0

    # Raises rather than answering forever. Without this the test does not
    # fail when the ceiling is removed - it HANGS, and a hang in CI burns the
    # whole job until the runner's timeout instead of naming the problem.
    # Measured: with a plain endless fake, deleting the bound produced a run
    # that was still going after 45 seconds.
    LIMIT = 60

    def graphql(self, query, variables):
        self.calls += 1
        if self.calls > self.LIMIT:
            raise AssertionError(
                f"asked {self.calls} times without stopping; the loop has no "
                "upper bound and would run against AH until the server tires"
            )
        start = variables["start"]
        size = variables["size"]
        return {
            "storesSearch": {
                "result": [
                    {"id": start + n, "name": f"Store {start + n}"} for n in range(size)
                ]
            }
        }


def test_it_stops_rather_than_looping_forever():
    """A server that always answers is otherwise an unbounded loop against
    somebody else's API - and this runs against AH, not against us."""
    endless = EndlessManager()
    stores = fetch_stores(manager=endless)
    assert stores, "it should still return what it read"
    assert endless.calls < 100, f"asked {endless.calls} times"


def test_a_store_without_a_name_is_not_offered():
    """An unnamed entry in a picker is a row a person cannot choose between."""
    manager = FakeManager([{"id": 1, "name": ""}, {"id": 2, "name": "Tiel"}], [])
    assert [s.store_id for s in fetch_stores(manager=manager)] == [2]


def test_the_label_is_how_people_name_their_shop():
    assert Store(1661, "Eindhoven Kamperfoelielaan").label() == (
        "AH Eindhoven Kamperfoelielaan"
    )


# --- writing it down --------------------------------------------------------


class RecordingEngine:
    def __init__(self):
        self.statements: list[str] = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, params=None):
        self.statements.append(" ".join(str(statement).split()))
        return None


def test_the_directory_is_replaced_not_merged():
    """A shop that closed must stop being offered. A merge would keep it on
    the list forever."""
    from bonuschef.portal.db import replace_store_directory

    engine = RecordingEngine()
    written = replace_store_directory(engine, [Store(1, "A"), Store(2, "B")])
    assert written == 2
    assert any("DELETE FROM public.ah_stores" in s for s in engine.statements)


def test_an_empty_fetch_does_not_wipe_the_directory():
    """Nothing fetched is not evidence that nothing exists. Wiping would leave
    a person unable to choose a store at all, which is worse than a stale
    list."""
    from bonuschef.portal.db import replace_store_directory

    engine = RecordingEngine()
    assert replace_store_directory(engine, []) == 0
    assert engine.statements == [], engine.statements


def test_the_directory_is_not_cached_for_seconds():
    """It changes on a scale of years. Giving it the price readers' TTL would
    re-query it constantly for an answer that never moves."""
    from bonuschef.portal import db

    assert db._STORE_DIRECTORY_TTL_S >= 3600


@pytest.mark.parametrize("name", ["read_store_directory"])
def test_the_directory_is_the_same_for_everybody(name):
    """Unlike the price readers, this one SHOULD share a cache: it is the list
    you pick from, not a thing that depends on who is asking."""
    import inspect

    from bonuschef.portal import db

    fn = getattr(db, name)
    params = inspect.signature(getattr(fn, "func", fn)).parameters
    assert "store_id" not in params
