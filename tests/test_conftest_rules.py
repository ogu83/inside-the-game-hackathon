"""The 30 s per-test guard (pytest.ini) must never apply to live tests, which call Foundry and Voice Live for minutes."""

import pytest

from tests.conftest import pytest_collection_modifyitems


class StubItem:
    def __init__(self, marks: list[str]) -> None:
        self.marks = {m: pytest.mark.__getattr__(m) for m in marks}  # noqa: PLC2801
        self.added: list = []

    def get_closest_marker(self, name: str):
        return self.marks.get(name)

    def add_marker(self, marker) -> None:
        self.added.append(marker)


def test_live_items_get_timeout_zero_and_offline_items_do_not() -> None:
    live, offline = StubItem(["live"]), StubItem([])
    pytest_collection_modifyitems([live, offline])
    assert len(live.added) == 1 and live.added[0].name == "timeout" and live.added[0].args == (0,)
    assert offline.added == []


def test_live_module_is_marked_timeout_zero_too() -> None:
    from tests.agents import test_live

    marks = test_live.pytestmark if isinstance(test_live.pytestmark, list) else [test_live.pytestmark]
    assert {m.name for m in marks} == {"live", "timeout"}
    assert next(m for m in marks if m.name == "timeout").args == (0,)
