"""Fabrique du modèle de langage (Azure AI — Kimi-K2.6)."""

from __future__ import annotations

import os


def get_llm():
    """Retourne un chat model Azure AI configuré sur Kimi-K2.6."""
    from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel

    return AzureAIChatCompletionsModel(
        endpoint=os.environ["AZURE_AI_ENDPOINT"],
        credential=os.environ["AZURE_AI_API_KEY"],
        model=os.environ.get("AZURE_AI_MODEL", "Kimi-K2.6"),
    )
