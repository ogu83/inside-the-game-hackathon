"""Foundry Hosted Agent entry point: serves the commentary workflow over the Responses protocol."""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure vendored app package in current directory takes precedence (container/hosted runtime),
# falling back to repository root for local development and tests when not vendored.
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

if not (CURRENT_DIR / "app").exists():
    REPO_ROOT = CURRENT_DIR.parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.append(str(REPO_ROOT))

from agent_framework import Agent, Workflow
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer, WorkflowTurn
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from app.agents.analyst import FoundryDirector, RuleDirector
from app.agents.commentator import FoundryCommentator
from app.agents.fact_checker import FactChecker, FoundryWordingJudge
from app.agents.fakes import AlwaysVerifies, TemplateCommentator
from app.agents.prompts import ANALYST_INSTRUCTIONS, COMMENTATOR_INSTRUCTIONS, FACT_CHECKER_INSTRUCTIONS
from app.agents.workflow import build_workflow

load_dotenv()


def request_json(request: Any) -> str:
    """Extract candidate moment JSON from incoming Responses request."""
    raw = request.request.get("input", "")
    if isinstance(raw, str):
        return raw
    parts: list[str] = []
    for item in raw:
        content = item.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.extend(c.get("text", "") for c in content)
    return "\n".join(parts)


def build_hosted_workflow(agent_mode: str = "foundry") -> Workflow:
    """Build the commentary workflow for the hosted agent server."""
    if agent_mode == "template":
        return build_workflow(TemplateCommentator(), FactChecker(AlwaysVerifies()), RuleDirector())

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    credential = DefaultAzureCredential()
    frontier_model = os.environ.get("FRONTIER_MODEL_DEPLOYMENT", os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini"))
    small_model = os.environ.get("SMALL_MODEL_DEPLOYMENT", frontier_model)

    def make_agent(model: str, name: str, instructions: str) -> Agent:
        return FoundryChatClient(project_endpoint=endpoint, model=model, credential=credential).as_agent(
            name=name, instructions=instructions
        )

    return build_workflow(
        writer=FoundryCommentator(make_agent(frontier_model, "commentator", COMMENTATOR_INSTRUCTIONS)),
        checker=FactChecker(FoundryWordingJudge(make_agent(small_model, "fact_checker", FACT_CHECKER_INSTRUCTIONS))),
        director=FoundryDirector(make_agent(small_model, "analyst", ANALYST_INSTRUCTIONS)),
    )


def create_server() -> ResponsesHostServer:
    def new_workflow(_request: Any) -> Workflow:
        mode = "template" if os.environ.get("AGENT_MODE") == "template" else "foundry"
        return build_hosted_workflow(mode)

    return ResponsesHostServer(
        workflow=new_workflow,
        parse_response=lambda request: WorkflowTurn(input=request_json(request)),
    )


def main() -> None:
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
