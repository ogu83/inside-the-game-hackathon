import importlib

import pytest


@pytest.mark.parametrize("module", ["app", "app.simulator", "app.ledger", "app.agents", "app.api"])
def test_package_imports(module: str) -> None:
    assert importlib.import_module(module) is not None
