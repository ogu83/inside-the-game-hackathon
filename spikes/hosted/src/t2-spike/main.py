"""Foundry Hosted Agent entry point: serves the T2 spike workflow over the Responses protocol."""

import os

from agent_framework import Agent, Workflow
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer, WorkflowTurn
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from spike_workflow import COMMENTATOR_INSTRUCTIONS, FACT_CHECKER_INSTRUCTIONS, build_workflow

load_dotenv()


def request_text(request) -> str:
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


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    def new_workflow(_request) -> Workflow:
        return build_workflow(
            Agent(client=client, name="commentator", instructions=COMMENTATOR_INSTRUCTIONS),
            Agent(client=client, name="fact_checker", instructions=FACT_CHECKER_INSTRUCTIONS),
        )

    ResponsesHostServer(
        workflow=new_workflow,
        parse_response=lambda request: WorkflowTurn(input=request_text(request)),
    ).run()


if __name__ == "__main__":
    main()
