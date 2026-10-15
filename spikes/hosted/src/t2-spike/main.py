"""Foundry Hosted Agent entry point: serves the T2 spike workflow over the Responses protocol."""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from spike_workflow import COMMENTATOR_INSTRUCTIONS, FACT_CHECKER_INSTRUCTIONS, build_workflow

load_dotenv()


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )
    def new_workflow_agent():
        # A WorkflowAgent keeps run state in memory, so each request gets a fresh one.
        return build_workflow(
            Agent(client=client, name="commentator", instructions=COMMENTATOR_INSTRUCTIONS),
            Agent(client=client, name="fact_checker", instructions=FACT_CHECKER_INSTRUCTIONS),
        ).as_agent(name="t2-spike")

    ResponsesHostServer(new_workflow_agent).run()


if __name__ == "__main__":
    main()
