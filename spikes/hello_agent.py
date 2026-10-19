"""Smallest Foundry round trip: one agent, one Responses API call, keyless auth."""

import asyncio
import os

from agent_framework_foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    async with DefaultAzureCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["SMALL_MODEL_DEPLOYMENT"],
            credential=credential,
        )
        agent = client.as_agent(name="hello", instructions="Answer in one short sentence.")
        response = await agent.run("Say hello to a football fan.")
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
