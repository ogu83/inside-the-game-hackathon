"""T2 spike, local run: Commentator -> Fact-Checker graph workflow with a conditional reject edge.

The workflow lives in spikes/hosted/src/t2-spike/spike_workflow.py so the hosted agent runs the same graph.
`--inject-false` replaces the first draft with a claim that contradicts the evidence, to prove the reject edge.

    python spikes/two_agents.py [--inject-false] [--trace]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from agent_framework_foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "hosted" / "src" / "t2-spike"))
from spike_workflow import COMMENTATOR_INSTRUCTIONS, FACT_CHECKER_INSTRUCTIONS, build_workflow  # noqa: E402


def configure_tracing(connection_string: str) -> None:
    from agent_framework.observability import enable_instrumentation
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=connection_string)
    enable_instrumentation(enable_sensitive_data=True)


async def main(inject_false: bool, trace: bool) -> None:
    load_dotenv()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    async with DefaultAzureCredential() as credential:
        if trace:
            from azure.ai.projects.aio import AIProjectClient

            async with AIProjectClient(endpoint=endpoint, credential=credential) as project:
                configure_tracing(await project.telemetry.get_application_insights_connection_string())

        def client(model_env: str) -> FoundryChatClient:
            return FoundryChatClient(project_endpoint=endpoint, model=os.environ[model_env], credential=credential)

        workflow = build_workflow(
            client("FRONTIER_MODEL_DEPLOYMENT").as_agent(name="commentator", instructions=COMMENTATOR_INSTRUCTIONS),
            client("SMALL_MODEL_DEPLOYMENT").as_agent(name="fact_checker", instructions=FACT_CHECKER_INSTRUCTIONS),
        )
        request = "inject-false" if inject_false else "comment on this moment"
        result = await workflow.run(request)
        for output in result.get_outputs():
            print(f"FINAL: {output}")

    if trace:
        from opentelemetry import trace as otel_trace

        otel_trace.get_tracer_provider().force_flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inject-false", action="store_true")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.inject_false, args.trace))
