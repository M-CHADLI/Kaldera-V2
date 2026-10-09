"""Fabrique du modèle de langage : Azure OpenAI, déploiement gpt-5.4-mini.

Variables : ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_ENDPOINT``, ``AZURE_OPENAI_DEPLOYMENT_NAME``
et, facultatif, ``AZURE_OPENAI_API_VERSION``. Deux formes d'endpoint : l'API « v1 » d'Azure AI
Foundry (``https://<ressource>.services.ai.azure.com/openai/v1``, où ``API_VERSION`` est ignorée)
ou l'API classique (``https://<ressource>.openai.azure.com``).

Aucun modèle n'est nécessaire pour faire tourner Kaldera : il sert à la revue de fond ``llm``
et à l'extraction de dossier ``llm`` ou ``auto``.
"""

from __future__ import annotations

import os

VARIABLES = ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME")


def llm_configure() -> bool:
    """Le modèle est-il configuré ? (sans le contacter)"""
    return all(os.environ.get(nom, "").strip() for nom in VARIABLES)


def delai_s() -> float:
    """Délai maximal d'un appel au modèle (KALDERA_LLM_DELAI_S, 60 s par défaut) : jamais illimité."""
    try:
        return max(5.0, float(os.environ.get("KALDERA_LLM_DELAI_S", "60")))
    except ValueError:
        return 60.0


def description_attendue() -> str:
    """Variables à renseigner, pour les messages d'erreur."""
    return ", ".join(VARIABLES)


def get_llm():
    """Retourne le chat model Azure OpenAI configuré."""
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].strip().rstrip("/")
    # Pas de température : les modèles de raisonnement (gpt-5…) n'acceptent que la valeur par défaut.
    if endpoint.endswith("/openai/v1"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=endpoint,
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            timeout=delai_s(),
            max_retries=1,
        )
    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION") or None,
        timeout=delai_s(),
        max_retries=1,
    )
