"""Suite-wide rules. Live tests call Foundry and Voice Live and take minutes; the 30 s guard in pytest.ini is for
the offline suite only, so `python -m pytest tests -m live` works without flags."""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(pytest.mark.timeout(0))
