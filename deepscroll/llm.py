"""
LLMInterface - Unified interface for LLM providers.

Supports Anthropic Claude and OpenAI models with automatic fallback
and rate limiting handling.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Configurable defaults via environment variables
DEFAULT_MAX_TOKENS = int(os.environ.get("RLM_MAX_TOKENS", "4096"))
DEFAULT_TEMPERATURE = float(os.environ.get("RLM_TEMPERATURE", "0.2"))


@dataclass
class LLMResponse:
    """Response from an LLM."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None = None


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """Generate text from a prompt."""
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        pass


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """
        Initialize Claude provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Model to use (defaults to claude-sonnet-4-20250514)
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable."
            )

        self.model = model or self.DEFAULT_MODEL
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazy-load the Anthropic client."""
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("anthropic package required. Install with: pip install anthropic")
        return self._client

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """Generate text using Claude."""
        messages = [{"role": "user", "content": prompt}]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system

        if temperature != 0.7:
            kwargs["temperature"] = temperature

        # Retry with exponential backoff for rate limits
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(**kwargs)
                return response.content[0].text

            except Exception as e:
                error_str = str(e)
                if "rate_limit" in error_str.lower() or "429" in error_str:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise

        raise RuntimeError("Max retries exceeded for Claude API")

    def count_tokens(self, text: str) -> int:
        """Estimate token count for Claude."""
        # Claude uses roughly 4 chars per token on average
        return len(text) // 4


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider."""

    DEFAULT_MODEL = "gpt-4o-mini"

    # Models that use max_completion_tokens instead of max_tokens
    # and don't support temperature parameter
    REASONING_MODELS = {"o1", "o1-mini", "o1-pro", "o3", "o3-mini", "o3-pro"}

    # Models that use the new API format (max_completion_tokens)
    NEW_API_PREFIXES = ("gpt-5", "gpt-5.4", "gpt-4.1", "gpt-4.5")

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use (defaults to gpt-4o-mini)
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable."
            )

        self.model = model or self.DEFAULT_MODEL
        self._client: Any = None
        self._tiktoken_encoding: Any = None

    @property
    def client(self) -> Any:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            try:
                import openai

                self._client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("openai package required. Install with: pip install openai")
        return self._client

    def _is_reasoning_model(self) -> bool:
        """Check if the current model is a reasoning model (o1, o3 series)."""
        model_base = self.model.split("-")[0] if "-" in self.model else self.model
        return model_base in self.REASONING_MODELS or any(
            self.model.startswith(prefix) for prefix in ("o1", "o3")
        )

    def _uses_new_api(self) -> bool:
        """Check if model uses max_completion_tokens instead of max_tokens."""
        return (
            self._is_reasoning_model() or
            any(self.model.startswith(prefix) for prefix in self.NEW_API_PREFIXES)
        )

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """Generate text using OpenAI."""
        messages: list[dict[str, str]] = []

        is_reasoning = self._is_reasoning_model()
        uses_new_api = self._uses_new_api()

        # Reasoning models don't support system messages - prepend to user message
        if system and is_reasoning:
            prompt = f"{system}\n\n{prompt}"
        elif system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        # Retry with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if uses_new_api:
                    # New API: max_completion_tokens, no temperature for reasoning models
                    kwargs: dict[str, Any] = {
                        "model": self.model,
                        "messages": messages,
                        "max_completion_tokens": max_tokens,
                    }
                    # Only add temperature for non-reasoning models
                    if not is_reasoning:
                        kwargs["temperature"] = temperature
                    response = self.client.chat.completions.create(**kwargs)
                else:
                    # Legacy API: max_tokens with temperature
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                return response.choices[0].message.content or ""

            except Exception as e:
                error_str = str(e)
                if "rate_limit" in error_str.lower() or "429" in error_str:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise

        raise RuntimeError("Max retries exceeded for OpenAI API")

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        if self._tiktoken_encoding is None:
            try:
                import tiktoken

                self._tiktoken_encoding = tiktoken.encoding_for_model(self.model)
            except ImportError:
                # Fallback to estimation
                return len(text) // 4
            except KeyError:
                # Model not found, use cl100k_base
                import tiktoken

                self._tiktoken_encoding = tiktoken.get_encoding("cl100k_base")

        return len(self._tiktoken_encoding.encode(text))


class LLMInterface:
    """
    Unified interface for multiple LLM providers.

    Automatically selects provider based on name and handles fallback.
    """

    PROVIDERS = {
        # Anthropic
        "claude": ClaudeProvider,
        "anthropic": ClaudeProvider,
        # OpenAI - generic
        "openai": OpenAIProvider,
        "gpt": OpenAIProvider,
        # OpenAI - GPT-4 series
        "gpt-4": OpenAIProvider,
        "gpt-4o": OpenAIProvider,
        "gpt-4o-mini": OpenAIProvider,
        "gpt-4-turbo": OpenAIProvider,
        # OpenAI - GPT-4.1 series (newer)
        "gpt-4.1": OpenAIProvider,
        "gpt-4.1-nano": OpenAIProvider,
        "gpt-4.1-mini": OpenAIProvider,
        # OpenAI - GPT-4.5 series
        "gpt-4.5": OpenAIProvider,
        "gpt-4.5-preview": OpenAIProvider,
        # OpenAI - GPT-5 series
        "gpt-5": OpenAIProvider,
        "gpt-5.4": OpenAIProvider,
        "gpt-5.4-nano": OpenAIProvider,
        "gpt-5.4-mini": OpenAIProvider,
        # OpenAI - Reasoning models (o-series)
        "o1": OpenAIProvider,
        "o1-mini": OpenAIProvider,
        "o1-pro": OpenAIProvider,
        "o3": OpenAIProvider,
        "o3-mini": OpenAIProvider,
    }

    def __init__(
        self,
        provider: str | BaseLLMProvider = "claude",
        model: str | None = None,
        api_key: str | None = None,
        fallback_provider: str | None = None,
    ):
        """
        Initialize the LLM interface.

        Args:
            provider: Provider name ("claude", "openai") or BaseLLMProvider instance
            model: Specific model to use
            api_key: API key (if not using environment variable)
            fallback_provider: Provider to use if primary fails
        """
        if isinstance(provider, BaseLLMProvider):
            self.provider = provider
        else:
            provider_lower = provider.lower()
            if provider_lower not in self.PROVIDERS:
                raise ValueError(
                    f"Unknown provider: {provider}. "
                    f"Available: {list(self.PROVIDERS.keys())}"
                )

            provider_class = self.PROVIDERS[provider_lower]
            self.provider = provider_class(api_key=api_key, model=model)

        self.fallback: BaseLLMProvider | None = None
        if fallback_provider:
            fallback_lower = fallback_provider.lower()
            if fallback_lower in self.PROVIDERS:
                try:
                    fallback_class = self.PROVIDERS[fallback_lower]
                    self.fallback = fallback_class()
                except ValueError:
                    logger.warning(f"Could not initialize fallback provider: {fallback_provider}")

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """
        Generate text using the configured provider.

        Args:
            prompt: User prompt
            system: System prompt (optional)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Generated text
        """
        try:
            return self.provider.generate(
                prompt=prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:
            if self.fallback:
                logger.warning(f"Primary provider failed ({e}), trying fallback...")
                return self.fallback.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            raise

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return self.provider.count_tokens(text)

    def summarize(
        self,
        content: str,
        query: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """
        Summarize content in relation to a query.

        Args:
            content: Content to summarize
            query: Original query for context
            max_tokens: Maximum tokens for summary

        Returns:
            Summary text
        """
        prompt = f"""Summarize the following content in relation to this query:

Query: {query}

Content:
{content[:10000]}

Provide a clear, concise summary focusing on information relevant to the query."""

        return self.generate(prompt, max_tokens=max_tokens)


# Convenience functions
def get_provider(
    name: Literal["claude", "openai"] = "claude",
    model: str | None = None,
) -> BaseLLMProvider:
    """
    Get an LLM provider by name.

    Args:
        name: Provider name
        model: Specific model (optional)

    Returns:
        Configured provider instance
    """
    if name == "claude":
        return ClaudeProvider(model=model)
    elif name == "openai":
        return OpenAIProvider(model=model)
    else:
        raise ValueError(f"Unknown provider: {name}")
