from __future__ import annotations

import os
import sys
from collections.abc import Callable


AZURE_AI_SCOPE = "https://ai.azure.com/.default"
TEST_PROMPT = "What is the capital of France?"


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def resolve_api_key() -> str | Callable[[], str]:
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key

    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    except ImportError as exc:
        raise RuntimeError(
            "AZURE_OPENAI_API_KEY is not set and azure-identity is unavailable. "
            "Install azure-identity or provide AZURE_OPENAI_API_KEY."
        ) from exc

    return get_bearer_token_provider(DefaultAzureCredential(), AZURE_AI_SCOPE)


def main() -> None:
    base_url = required_env("AZURE_OPENAI_RESPONSES_BASE_URL")
    deployment = required_env("AZURE_OPENAI_CHAT_DEPLOYMENT")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The OpenAI Python client is unavailable. Install the apps/api requirements first."
        ) from exc

    client = OpenAI(base_url=base_url, api_key=resolve_api_key())
    response = client.responses.create(model=deployment, input=TEST_PROMPT)
    print(response.output_text)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - smoke tests should report concise setup or API failures
        print(f"Azure Responses API smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
