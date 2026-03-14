"""Dynamic provider proxy for hot-swapping LLM instances."""

from typing import Any, Dict, List, Optional
from loguru import logger
from providers.base import LLMProvider, LLMResponse
from config.loader import get_config_service
from providers.openai_provider import OpenAIProvider
# Import other providers as needed

class DynamicProviderProxy(LLMProvider):
    """
    A proxy provider that delegates calls to the currently active LLM instance.
    It automatically switches the underlying provider when the configuration changes.
    """

    def __init__(self):
        super().__init__()
        self._current_instance_id: Optional[str] = None
        self._current_provider: Optional[LLMProvider] = None
        self._config_service = get_config_service()
        self._refresh_provider()

    def _refresh_provider(self) -> None:
        """Check if the active LLM instance has changed and update the provider."""
        config = self._config_service.config
        active_llm = config.get_active_provider()

        if not active_llm:
            logger.warning("No active LLM instance configured in proxy.")
            self._current_instance_id = None
            self._current_provider = None
            return

        if active_llm.id != self._current_instance_id:
            logger.info(f"Switching active LLM provider: {self._current_instance_id} -> {active_llm.id} ({active_llm.model_name})")

            # Simple factory for now, can be expanded
            if active_llm.provider in ["openai", "deepseek", "qwen", "step", "openrouter"]:
                self._current_provider = OpenAIProvider(
                    api_key=active_llm.api_key,
                    api_base=active_llm.api_base,
                    default_model=active_llm.model_name
                )
            elif active_llm.provider == "anthropic":
                # Assuming LiteLLM or similar for Anthropic if not using a specific provider class
                # For now, fallback to OpenAI if compatible or add AnthropicProvider if it exists
                # Looking at Glob results, we have litellm_provider.py
                try:
                    from providers.litellm_provider import LiteLLMProvider
                    self._current_provider = LiteLLMProvider(
                        api_key=active_llm.api_key,
                        api_base=active_llm.api_base,
                        default_model=active_llm.model_name
                    )
                except ImportError:
                    logger.error("LiteLLMProvider not found, cannot switch to Anthropic.")
                    return
            else:
                # Default to OpenAI compatible for unknown providers (common for local LLMs)
                self._current_provider = OpenAIProvider(
                    api_key=active_llm.api_key,
                    api_base=active_llm.api_base,
                    default_model=active_llm.model_name
                )

            self._current_instance_id = active_llm.id

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Delegate chat call to the current provider."""
        self._refresh_provider()
        if not self._current_provider:
            return LLMResponse(
                content="Error: No active LLM provider configured.",
                finish_reason="error"
            )

        # Override model if specified, otherwise use the one from config
        return await self._current_provider.chat(
            messages=messages,
            tools=tools,
            model=model or self.get_default_model(),
            **kwargs
        )

    def get_default_model(self) -> str:
        """Get the default model from the active instance."""
        config = self._config_service.config
        active = config.get_active_provider()
        return active.model_name if active else "unknown"
