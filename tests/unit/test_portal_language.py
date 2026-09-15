"""The portal speaks one language, and the suite is what keeps it that way.

Three separate changes each shipped a page that mixed Dutch headings with
English copy, and every one of them was found by reading the screen rather
than by running the tests. This walks the source instead: any string the
reader can actually see, in any portal module, checked against English words
that have no Dutch spelling.
"""

import ast
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "portal"

# Words with no Dutch homograph, so a match is never a false positive on a
# Dutch sentence. Deliberately function words and UI verbs rather than domain
# nouns: "bonus", "product" and "per" are Dutch too, and a list that flagged
# them would be silenced within a week.
ENGLISH_ONLY = frozenset(
    """
    the and with for from this that these those your you are were have has
    been not but they their what which when where only also more than then
    some any all save saving search select click loading unknown none add
    remove show hide price total change changes history check analysis
    connection running reachable recipe ingredients products matched
    inflated tracked date name servings details step
    """.split()
)

# Rendered by Streamlit as literal text. Anything else on `st` takes config,
# keys or data rather than copy.
_ST_TEXT_CALLS = frozenset(
    """
    title header subheader caption markdown write text info warning error
    success badge metric button form_submit_button download_button
    text_input text_area number_input selectbox multiselect radio checkbox
    slider date_input time_input file_uploader toggle segmented_control
    pills expander tab popover toast spinner page_link
    """.split()
)


# Keyword arguments that carry copy. Everything else on a widget is plumbing:
# ``key`` is a session-state identifier, ``icon`` is a Material Symbols name,
# and ``options`` is data. Flagging those is how a guard like this gets deleted.
_COPY_KEYWORDS = frozenset(
    ("label", "help", "placeholder", "body", "text", "caption", "title")
)


def _visible_text(node: ast.AST, out: list[str]) -> None:
    """Collect only what a reader sees.

    Subscript slices and f-string placeholders are skipped: ``row["total_cost"]``
    is a column name, not copy. Flagging those would train the next person to
    delete this test rather than fix the string.
    """
    if isinstance(node, ast.Subscript):
        _visible_text(node.value, out)
        return
    if isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                _visible_text(part.value, out)
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            out.append(node.value)
        return
    for child in ast.iter_child_nodes(node):
        _visible_text(child, out)


def _copy_in(path: Path) -> list[tuple[int, str]]:
    """Every user-visible string in a module, with its line number."""
    found: list[tuple[int, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        base = func.value
        if not (isinstance(base, ast.Name) and base.id == "st"):
            continue
        if func.attr not in _ST_TEXT_CALLS:
            continue
        texts: list[str] = []
        args = [*call.args]
        args += [kw.value for kw in call.keywords if kw.arg in _COPY_KEYWORDS]
        for arg in args:
            _visible_text(arg, texts)
        found.extend((call.lineno, text) for text in texts if text.strip())
    return found


def _english_words(text: str) -> set[str]:
    """Words a Dutch reader would not recognise.

    ``_`` counts as a word character so that a snake_case identifier stays one
    token: telling someone to start the ``recipe_pool_refresh`` job is naming a
    thing they must type into Dagster, not writing English at them. Ordinary
    prose never contains an underscore, so this cannot hide a real offence.
    """
    word = ""
    words: set[str] = set()
    for char in text.lower():
        if char.isalpha() or char == "_":
            word += char
            continue
        if word in ENGLISH_ONLY:
            words.add(word)
        word = ""
    if word in ENGLISH_ONLY:
        words.add(word)
    return words


@pytest.mark.parametrize("module", sorted(PORTAL.glob("*.py")), ids=lambda p: p.name)
def test_the_portal_speaks_dutch(module):
    offences = [
        f"{module.name}:{line}: {text!r} -> {sorted(hits)}"
        for line, text in _copy_in(module)
        if (hits := _english_words(text))
    ]
    assert not offences, "English copy on a Dutch surface:\n" + "\n".join(offences)


def test_the_guard_would_catch_a_regression(tmp_path):
    """A test that can only pass is worth nothing; prove it still bites."""
    sample = tmp_path / "regression_page.py"
    sample.write_text(
        "import streamlit as st\n"
        'st.subheader("Recent Price Changes")\n'
        'st.caption("Alles in orde")\n',
        encoding="utf-8",
    )
    hits = [(line, text) for line, text in _copy_in(sample) if _english_words(text)]
    assert hits == [(2, "Recent Price Changes")]
