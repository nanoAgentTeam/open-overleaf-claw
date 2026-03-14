import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from providers.base import LLMResponse
from providers.openai_provider import OpenAIProvider


class TestOpenAIProviderMaxTokens(unittest.IsolatedAsyncioTestCase):
    async def test_default_max_tokens_is_capped_for_non_reasoning_models(self):
        provider = OpenAIProvider(api_key="x", api_base="https://example.com", default_model="gpt-4o-mini")

        create_mock = AsyncMock(return_value=SimpleNamespace())
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        with patch.object(provider, "get_client", return_value=fake_client), patch.object(
            provider, "_parse_response", return_value=LLMResponse(content="ok")
        ):
            await provider.chat(messages=[{"role": "user", "content": "hi"}], retries=1)

        kwargs = create_mock.await_args.kwargs
        self.assertEqual(kwargs.get("max_tokens"), 8192)

    async def test_explicit_max_tokens_above_cap_is_clamped(self):
        provider = OpenAIProvider(api_key="x", api_base="https://example.com", default_model="gpt-4o-mini")

        create_mock = AsyncMock(return_value=SimpleNamespace())
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )

        with patch.object(provider, "get_client", return_value=fake_client), patch.object(
            provider, "_parse_response", return_value=LLMResponse(content="ok")
        ):
            await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=20000,
                retries=1,
            )

        kwargs = create_mock.await_args.kwargs
        self.assertEqual(kwargs.get("max_tokens"), 8192)


if __name__ == "__main__":
    unittest.main()
