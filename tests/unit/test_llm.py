"""Fabrique du modèle de langage : Azure OpenAI (gpt-5.4-mini)."""

from __future__ import annotations

from typing import Any

import pytest

from kaldera import llm

from fabrique import avec_azure_openai, sans_modele


def test_aucun_modele_configure(monkeypatch: pytest.MonkeyPatch) -> None:
    sans_modele(monkeypatch)
    assert llm.llm_configure() is False
    assert "AZURE_OPENAI_API_KEY" in llm.description_attendue()


def test_une_configuration_partielle_n_est_pas_un_modele(monkeypatch: pytest.MonkeyPatch) -> None:
    sans_modele(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "cle")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "   ")
    assert llm.llm_configure() is False


def test_le_modele_est_reconnu_une_fois_configure(monkeypatch: pytest.MonkeyPatch) -> None:
    avec_azure_openai(monkeypatch)
    assert llm.llm_configure() is True


def test_endpoint_classique_recoit_ses_parametres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    avec_azure_openai(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    recus: dict[str, Any] = {}

    class FauxAzureChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            recus.update(kwargs)

    monkeypatch.setattr("langchain_openai.AzureChatOpenAI", FauxAzureChatOpenAI)
    assert isinstance(llm.get_llm(), FauxAzureChatOpenAI)
    assert recus["azure_deployment"] == "gpt-test" and recus["api_version"] == "2024-10-21"
    assert recus["azure_endpoint"].startswith("https://exemple") and "temperature" not in recus
    assert 5 <= recus["timeout"] <= 120  # jamais d'attente illimitée


def test_la_version_d_api_est_facultative(monkeypatch: pytest.MonkeyPatch) -> None:
    avec_azure_openai(monkeypatch)
    recus: dict[str, Any] = {}
    monkeypatch.setattr(
        "langchain_openai.AzureChatOpenAI", lambda **kw: recus.update(kw) or object()
    )
    llm.get_llm()
    assert recus["api_version"] is None


def test_le_delai_est_borne_et_tolere_une_valeur_invalide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KALDERA_LLM_DELAI_S", raising=False)
    assert llm.delai_s() == 60.0
    monkeypatch.setenv("KALDERA_LLM_DELAI_S", "2")
    assert llm.delai_s() == 5.0
    monkeypatch.setenv("KALDERA_LLM_DELAI_S", "beaucoup")
    assert llm.delai_s() == 60.0


def test_endpoint_v1_d_azure_ai_foundry_utilise_chat_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    avec_azure_openai(monkeypatch)
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT", "https://ressource.services.ai.azure.com/openai/v1/"
    )
    recus: dict[str, Any] = {}
    monkeypatch.setattr("langchain_openai.ChatOpenAI", lambda **kw: recus.update(kw) or object())
    llm.get_llm()
    assert recus["base_url"].endswith("/openai/v1") and recus["model"] == "gpt-test"
    assert "temperature" not in recus
