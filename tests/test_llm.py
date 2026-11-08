from types import SimpleNamespace

import pytest

from app.llm import FakeLLM, get_client, get_vision_client
from app.llm.gemini import GeminiClient, RetryableError, _retry_after


def test_fake_returns_first_match_and_counts_calls():
    llm = FakeLLM({"concept": '{"concepts": []}', "question": "Q1"})
    assert llm.complete("extract concept from page 3").text == '{"concepts": []}'
    assert llm.complete("no match here").text == "{}"
    assert llm.calls == 2


def test_get_client_fake(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert isinstance(get_client(), FakeLLM)


def test_get_client_missing_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Thiếu LLM_API_KEY"):
        get_client()


def test_get_client_gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    client = get_client()
    assert isinstance(client, GeminiClient)
    assert client.models == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


def test_get_client_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    with pytest.raises(ValueError):
        get_client()


def _gemini(monkeypatch, *outcomes, models=("gemini-3.8-flash",)):
    """GeminiClient whose vendor call returns/raises the given outcomes in order, no network."""
    client = GeminiClient("test-key", list(models))
    client.called = []
    pending = list(outcomes)

    def fake_generate(model, *args):
        client.called.append(model)
        outcome = pending.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(client, "_generate", fake_generate)
    monkeypatch.setattr("app.llm.gemini.time.sleep", lambda s: None)
    return client


def test_gemini_bad_json_is_caught(monkeypatch):
    client = _gemini(monkeypatch, ("not json", 10, 5))
    with pytest.raises(ValueError, match="JSON"):
        client.complete("p", json_schema={"type": "object"})


def test_gemini_retries_then_succeeds(monkeypatch):
    client = _gemini(monkeypatch, RetryableError("429"), RetryableError("429"), ('{"ok": 1}', 1_000_000, 0))
    result = client.complete("p", json_schema={"type": "object"})
    assert result.text == '{"ok": 1}' and result.cost_usd == pytest.approx(0.75)


def test_gemini_gives_up_after_two_retries(monkeypatch):
    client = _gemini(monkeypatch, *[RetryableError("429")] * 3)
    with pytest.raises(RetryableError):
        client.complete("p")


def test_gemini_waits_as_long_as_the_server_asks(monkeypatch):
    client = _gemini(monkeypatch, RetryableError("429", retry_after=20), ("{}", 0, 0))
    slept = []
    monkeypatch.setattr("app.llm.gemini.time.sleep", slept.append)
    client.complete("p")
    assert slept == [20]


def test_gemini_does_not_retry_a_daily_quota(monkeypatch):
    client = _gemini(monkeypatch, RetryableError("429", retry_after=62322), ("{}", 0, 0))
    with pytest.raises(RetryableError):
        client.complete("p")


def test_retry_after_is_read_from_retry_info():
    info = {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "62322s"}
    assert _retry_after(SimpleNamespace(details={"error": {"details": [info]}})) == 62322
    assert _retry_after(SimpleNamespace(details={"error": {"details": []}})) is None
    assert _retry_after(SimpleNamespace(details=None)) is None


def test_get_client_reads_a_model_priority_list(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", " a , b ")
    assert get_client().models == ["a", "b"]


def test_gemini_falls_back_and_skips_a_model_out_of_daily_quota(monkeypatch):
    quota = RetryableError("429", retry_after=62322)
    client = _gemini(monkeypatch, quota, ("{}", 0, 0), ("{}", 0, 0), models=("first", "second"))
    client.complete("p")
    client.complete("p")
    assert client.called == ["first", "second", "second"]


def test_gemini_hands_over_at_once_but_retries_the_last_model(monkeypatch):
    overloaded = RetryableError("503")
    client = _gemini(monkeypatch, *[overloaded] * 4, models=("first", "second"))
    with pytest.raises(RetryableError):
        client.complete("p")
    assert client.called == ["first"] + ["second"] * 3


def test_vision_and_text_roles_use_their_own_models(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_VISION_MODEL", raising=False)
    vision, text = get_vision_client(), get_client()
    assert (vision.models, vision.thinking) == (["gemini-3.1-flash-lite"], "MINIMAL")
    assert (text.models, text.thinking) == (["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"], None)
