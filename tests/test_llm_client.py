from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import llm_client


class StructuredResult(BaseModel):
    value: int


def test_generate_content_uses_custom_model_chain_in_order_on_rate_limits(monkeypatch):
    calls = []

    class RateLimitError(Exception):
        pass

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise RateLimitError("429 rate limit")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_args, **_kwargs: None)

    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=1,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
        model_chain=[
            "gemini/gemini-3-flash-preview",
            "gemini/gemma-4-31b-it",
            "gemini/gemini-3.1-flash-lite",
        ],
    )

    result = client.generate_content(prompt="hello")

    assert result == "ok"
    assert [call["model"] for call in calls] == [
        "gemini/gemini-3-flash-preview",
        "gemini/gemma-4-31b-it",
        "gemini/gemini-3.1-flash-lite",
    ]


def test_generate_content_honors_provider_retry_hint(monkeypatch):
    sleeps = []
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("429 quota exceeded. Please retry in 27.5s.")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm_client.random, "uniform", lambda *_args: 1.0)
    monkeypatch.setattr(llm_client.time, "sleep", lambda seconds: sleeps.append(seconds))
    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=0,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
        model_chain=["gemini/first", "gemini/second"],
    )

    assert client.generate_content(prompt="hello") == "ok"
    assert sleeps == [27.5]


def test_generate_content_forwards_reasoning_effort(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="42"))]
        )

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)

    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=0,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
    )

    result = client.generate_content(prompt="hello", reasoning_effort="medium")

    assert result == "42"
    assert calls[0]["reasoning_effort"] == "medium"


def test_generate_content_omits_reasoning_effort_for_gemma_fallback(monkeypatch):
    calls = []

    class RateLimitError(Exception):
        pass

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RateLimitError("429 rate limit")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_args, **_kwargs: None)

    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=1,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
        model_chain=["gemini/gemini-3.1-flash-lite", "gemini/gemma-4-26b-a4b-it"],
    )

    assert client.generate_content(prompt="hello", reasoning_effort="low") == "ok"
    assert calls[0]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in calls[1]


def test_generate_content_omits_temperature_when_not_provided(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)

    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=0,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
    )

    result = client.generate_content(prompt="hello")

    assert result == "ok"
    assert "temperature" not in calls[0]


def test_generate_content_retries_invalid_structured_output_on_next_model(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        content = '{"value":' if len(calls) == 1 else '{"value":42}'
        return SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content),
            )]
        )

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)
    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=0,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
        model_chain=["gemini/first", "gemini/second"],
    )

    assert client.generate_content(
        prompt="hello", response_format=StructuredResult
    ) == '{"value":42}'
    assert [call["model"] for call in calls] == ["gemini/first", "gemini/second"]


def test_generate_content_retries_empty_content_on_next_model(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        content = None if len(calls) == 1 else "ok"
        return SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content),
            )]
        )

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)
    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=0,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
        model_chain=["gemini/first", "gemini/second"],
    )

    assert client.generate_content(prompt="hello") == "ok"
    assert [call["model"] for call in calls] == ["gemini/first", "gemini/second"]


def test_generate_content_rejects_truncated_finish_reason(monkeypatch):
    monkeypatch.setattr(
        llm_client.litellm,
        "completion",
        lambda **_kwargs: SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="length",
                message=SimpleNamespace(content='{"value":42}'),
            )]
        ),
    )
    client = llm_client.LLMClient(
        model="openai/test",
        api_key="test-key",
        max_rpm=100,
        max_retries=0,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
    )

    with pytest.raises(llm_client.LLMResponseError, match="truncated"):
        client.generate_content(prompt="hello", response_format=StructuredResult)


def test_generate_content_logs_final_provider_error_after_pool_exhaustion(monkeypatch, caplog):
    calls = []

    class RateLimitError(Exception):
        pass

    def fake_completion(**kwargs):
        calls.append(kwargs)
        raise RateLimitError(f"429 exhausted on {kwargs['model']}")

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)
    monkeypatch.setattr(llm_client.time, "sleep", lambda *_args, **_kwargs: None)

    client = llm_client.LLMClient(
        model="gemini",
        api_key="test-key",
        max_rpm=100,
        max_retries=0,
        retry_base_delay=0,
        daily_budget=0,
        request_delay=0,
        model_chain=["gemini/first", "gemini/second"],
    )

    with pytest.raises(RateLimitError, match="429 exhausted on gemini/second"):
        client.generate_content(prompt="hello")

    assert [call["model"] for call in calls] == ["gemini/first", "gemini/second"]
    assert "All 2 attempts failed; final model=gemini/second" in caplog.text
    assert "RateLimitError: 429 exhausted on gemini/second" in caplog.text


def test_job_scoring_model_chain_prefers_stable_flash_fallbacks():
    import config

    assert config.JOB_SCORING_MODEL_CHAIN == [
        "gemini/gemini-3.1-flash-lite",
        "gemini/gemini-2.5-flash-lite",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-3-flash-preview",
        "gemini/gemma-4-31b-it",
        "gemini/gemma-4-26b-a4b-it",
    ]
