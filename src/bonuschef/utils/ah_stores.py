"""The Albert Heijn store directory: which store is which.

A store is an integer everywhere in this system - `AH_STORE_ID`, the markdown
rows, the clearance grain. That was fine while there was one operator who
knew that 1876 meant their own shop. It stops being fine the moment somebody
else has to choose: asking a person to type "1661" is not a way to pick a
supermarket, and a typo silently gives them another town's prices with
nothing on the page to reveal it.

`storesSearch` answers with both halves. Measured 2026-09-20: 1,199 stores,
each carrying an id and a name of the form "Eindhoven Kamperfoelielaan" -
which is how people actually refer to their shop.

Paged deliberately rather than asked for in one request. The field caps a
page at a size the server chooses, and `size` is a `PageSize` scalar rather
than an `Int`, so an oversized request is refused outright rather than
truncated quietly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from bonuschef.utils.ah_auth import manager_from_env


class SupportsGraphQL(Protocol):
    """All this needs of a token manager is the one call it makes.

    Typed as a protocol rather than as AHTokenManager so a test can pass a
    fake without a credential, a token file, or a network - which is what
    keeps this module's tests inside the suite's no-network rule.
    """

    def graphql(self, query: str, variables: dict[str, Any]) -> dict: ...


_STORES_QUERY = """query Stores($size: PageSize!, $start: Int!) {
  storesSearch(size: $size, start: $start) {
    result { id name }
  }
}"""

# The server's own page size, not a guess: 100 is accepted and a larger value
# is rejected by the PageSize scalar rather than silently clipped.
_PAGE = 100

# 1,199 stores at the time of writing. The ceiling exists so that a change at
# AH's end cannot turn this into an unbounded loop against their API; it is
# generous enough that hitting it means something has genuinely changed.
_MAX_STORES = 3000


@dataclass(frozen=True)
class Store:
    store_id: int
    name: str

    def label(self) -> str:
        """What a person sees when choosing. "AH" is the only chain here, and
        prefixing it is how the shop is spoken about: "AH Kamperfoelielaan"."""
        return f"AH {self.name}"


def fetch_stores(*, manager: SupportsGraphQL | None = None) -> list[Store]:
    """Every store AH will name, ordered by id.

    Returns what it managed to read rather than raising on a short page: a
    directory that is missing its tail is still a usable directory, while an
    exception leaves the person with no way to choose at all.
    """
    manager = manager or manager_from_env()
    found: dict[int, str] = {}
    start = 0
    while start < _MAX_STORES:
        data = manager.graphql(_STORES_QUERY, {"size": _PAGE, "start": start})
        page = ((data or {}).get("storesSearch") or {}).get("result") or []
        if not page:
            break
        for row in page:
            store_id, name = row.get("id"), (row.get("name") or "").strip()
            if isinstance(store_id, int) and name:
                found[store_id] = name
        start += len(page)
    return [Store(store_id=i, name=found[i]) for i in sorted(found)]
