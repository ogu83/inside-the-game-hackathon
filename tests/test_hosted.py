import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest

from app.agents.models import MomentResult
from app.agents.workflow import run_moment
from app.ledger.state import detect_all
from app.simulator.engine import simulate
from hosted.src.commentary.main import build_hosted_workflow, create_server, request_json
from hosted.sync_app import REPO_ROOT, sync


@pytest.fixture(scope="module")
def sample_moment():
    moments = detect_all(simulate(7))
    return moments[0]


async def test_hosted_workflow_template_mode(sample_moment) -> None:
    workflow = build_hosted_workflow("template")
    assert workflow.name == "commentary"
    result = await run_moment(workflow, sample_moment)
    assert isinstance(result, MomentResult)
    assert result.moment_id == sample_moment.moment_id
    assert result.decision.say is True
    assert result.verdict is not None
    assert result.verdict.status == "verified"


def test_request_json_extraction() -> None:
    class FakeReq:
        def __init__(self, data):
            self.request = data

    assert request_json(FakeReq({"input": '{"test": 1}'})) == '{"test": 1}'
    assert request_json(FakeReq({"input": [{"content": "hello"}]})) == "hello"


def test_create_server_initialization() -> None:
    server = create_server()
    assert server is not None


def test_hosted_agent_self_contained_packaging(tmp_path: Path) -> None:
    """Verify commentary agent imports and builds without repo root on sys.path."""
    main_src = REPO_ROOT / "hosted" / "src" / "commentary" / "main.py"
    main_dst = tmp_path / "main.py"
    shutil.copy2(main_src, main_dst)

    sync(tmp_path / "app")

    script = (
        "import sys, os\n"
        "from pathlib import Path\n"
        f"repo_root = Path(r'{REPO_ROOT}').resolve()\n"
        "sys.path = [p for p in sys.path if Path(p).resolve() != repo_root]\n"
        "import main\n"
        "import app\n"
        "app_path = Path(app.__file__).resolve()\n"
        "assert str(repo_root) not in sys.path, f'repo_root in sys.path: {sys.path}'\n"
        "assert app_path.is_relative_to(Path.cwd()), f'app not local: {app_path}'\n"
        "assert hasattr(main, 'build_hosted_workflow')\n"
        "wf = main.build_hosted_workflow('template')\n"
        "assert wf.name == 'commentary'\n"
        "print('PASS')\n"
    )

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    res = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "PASS" in res.stdout

