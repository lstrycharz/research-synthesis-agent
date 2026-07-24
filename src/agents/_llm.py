"""Shared LLM plumbing for agent nodes: model construction + optional Langfuse tracing.

Every node that calls Claude builds the model the same way (explicit SecretStr api_key —
env-reading is unreliable) and attaches the Langfuse callback only when Langfuse is
configured. Kept in one place so the three node modules don't each reimplement it.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import RunnableConfig
from pydantic import SecretStr

from src.config import Settings
from src.observability import get_langfuse_client


def build_chat_model(settings: Settings, *, model_name: str, max_tokens: int) -> ChatAnthropic:
    """Construct a ChatAnthropic with the key passed explicitly (never read from env)."""
    return ChatAnthropic(  # type: ignore[call-arg]  # model/max_tokens are pydantic aliases
        model=model_name,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens=max_tokens,
    )


def langfuse_config(settings: Settings) -> RunnableConfig:
    """RunnableConfig carrying a Langfuse callback when configured, else empty (no-op).

    Constructing the client registers it in the global registry that CallbackHandler()
    resolves — the return value's side effect is load-bearing.
    """
    if get_langfuse_client(settings) is None:
        return {}
    from langfuse.langchain import CallbackHandler

    return {"callbacks": [CallbackHandler()]}
