from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import datetime, date, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .models import ArticleCandidate, CuratorDecision
from .validator import clean_ai_text
from .writer import (
    PromptStore,
    build_curator_prompt,
    build_rewrite_prompt,
    build_writer_prompt,
)


NotifyFn = Callable[[str], Awaitable[None]]


class AIClientError(RuntimeError):
    pass


def gemini_quota_reset_msk() -> str:
    """Return next Gemini quota reset time in MSK as 'HH:MM' string.

    Gemini free-tier RPD resets at 00:00 Pacific Time.
    """
    pt = ZoneInfo("America/Los_Angeles")
    msk = ZoneInfo("Europe/Moscow")
    now_pt = datetime.now(pt)
    next_reset_pt = datetime.combine(
        (now_pt + timedelta(days=1)).date(),
        time.min,
        tzinfo=pt,
    )
    return next_reset_pt.astimezone(msk).strftime("%H:%M")


def gemini_quota_date() -> date:
    """Return current date in PT — used to reset exhausted-key state at PT midnight."""
    return datetime.now(ZoneInfo("America/Los_Angeles")).date()


def normalize_api_keys(value: str | list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = str(item).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


RETRY_STATUSES = {429, 500, 502, 503, 504}


class BaseAIClient(ABC):
    def __init__(self, prompt_store: PromptStore) -> None:
        self.prompt_store = prompt_store
        self._api_lock = asyncio.Lock()

    async def curate(
        self,
        article: ArticleCandidate,
        feedback_context: str = "",
        recent_published_context: str = "",
    ) -> CuratorDecision:
        system_prompt, user_prompt = build_curator_prompt(
            self.prompt_store, article, feedback_context, recent_published_context
        )
        raw = await self.complete(system_prompt, user_prompt, temperature=0.2)
        return parse_curator_response(raw)

    async def write(
        self,
        article: ArticleCandidate,
        decision: CuratorDecision,
        article_text: str = "",
    ) -> str:
        system_prompt, user_prompt = build_writer_prompt(self.prompt_store, article, decision, article_text)
        raw = await self.complete(system_prompt, user_prompt, temperature=0.65)
        return clean_ai_text(raw)

    async def rewrite(
        self,
        article: ArticleCandidate,
        previous_text: str,
        reason: str,
        article_text: str = "",
    ) -> str:
        system_prompt, user_prompt = build_rewrite_prompt(
            self.prompt_store,
            article,
            previous_text,
            reason,
            article_text,
        )
        raw = await self.complete(system_prompt, user_prompt, temperature=0.75)
        return clean_ai_text(raw)

    async def complete(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        async with self._api_lock:
            return await self._complete(system_prompt, user_prompt, temperature=temperature)

    @abstractmethod
    async def _complete(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class GeminiAIClient(BaseAIClient):
    def __init__(
        self,
        prompt_store: PromptStore,
        *,
        api_key: str | list[str],
        model: str,
        timeout_seconds: float,
        request_delay_seconds: float = 0.0,
        notify: NotifyFn | None = None,
        label: str = "",
    ) -> None:
        super().__init__(prompt_store)
        self.api_keys = normalize_api_keys(api_key)
        self.model = model
        self.request_delay_seconds = request_delay_seconds
        self.client = httpx.AsyncClient(timeout=timeout_seconds)
        self.notify = notify
        self.label = label or model
        self.exhausted_keys: set[int] = set()
        self.quota_day: date | None = None

    def _reset_quota_state_if_new_day(self) -> None:
        today = gemini_quota_date()
        if self.quota_day != today:
            self.quota_day = today
            self.exhausted_keys.clear()

    async def _notify_key_exhausted(self, key_index: int) -> None:
        if self.notify is None:
            return
        total = len(self.api_keys)
        if key_index < total:
            msg = (
                f"Gemini ({self.label}): ключ #{key_index} выгорел на сегодня, "
                f"переключаюсь на #{key_index + 1}."
            )
        else:
            msg = (
                f"Gemini ({self.label}): все {total} ключа выгорели. "
                f"Квота обновится в {gemini_quota_reset_msk()} MSK."
            )
        try:
            await self.notify(msg)
        except Exception:
            pass

    async def _complete(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        if not self.api_keys:
            raise AIClientError("Gemini API key is empty")

        self._reset_quota_state_if_new_day()

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "text/plain",
            },
        }

        last_status_code: int | None = None
        for key_index, api_key in enumerate(self.api_keys, start=1):
            if key_index in self.exhausted_keys:
                continue
            try:
                response = await post_json_with_retries(
                    self.client,
                    url,
                    json_payload=payload,
                    params={"key": api_key},
                    request_delay_seconds=self.request_delay_seconds,
                )
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                last_status_code = status_code
                if status_code == 429:
                    if key_index not in self.exhausted_keys:
                        self.exhausted_keys.add(key_index)
                        await self._notify_key_exhausted(key_index)
                    if key_index < len(self.api_keys):
                        continue
                raise AIClientError(f"Gemini request failed: HTTP {status_code}") from None
            except httpx.HTTPError as exc:
                raise AIClientError(f"Gemini request failed: {exc.__class__.__name__}") from None

            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                raise AIClientError(f"Unexpected Gemini response: {data}") from exc

        raise AIClientError(f"Gemini request failed: HTTP {last_status_code or 'unknown'}")

    async def aclose(self) -> None:
        await self.client.aclose()


class OpenAICompatibleClient(BaseAIClient):
    def __init__(
        self,
        prompt_store: PromptStore,
        *,
        api_key: str | list[str],
        base_url: str,
        model: str,
        timeout_seconds: float,
        request_delay_seconds: float = 0.0,
    ) -> None:
        super().__init__(prompt_store)
        keys = normalize_api_keys(api_key)
        self.api_key = keys[0] if keys else ""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.request_delay_seconds = request_delay_seconds
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    async def _complete(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        if not self.api_key:
            raise AIClientError("OpenAI-compatible API key is empty")
        if not self.base_url:
            raise AIClientError("OpenAI-compatible base URL is empty")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "Tuda i obratno News Bot",
        }
        try:
            response = await post_json_with_retries(
                self.client,
                f"{self.base_url}/chat/completions",
                json_payload=payload,
                headers=headers,
                request_delay_seconds=self.request_delay_seconds,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise AIClientError(f"OpenAI-compatible request failed: HTTP {status_code}") from None
        except httpx.HTTPError as exc:
            raise AIClientError(f"OpenAI-compatible request failed: {exc.__class__.__name__}") from None

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIClientError(f"Unexpected OpenAI-compatible response: {data}") from exc

    async def aclose(self) -> None:
        await self.client.aclose()


class StubAIClient(BaseAIClient):
    async def _complete(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        if "JSON" in system_prompt.upper():
            return json.dumps(
                {
                    "accept": True,
                    "score": 8,
                    "category": "test",
                    "reason": "Stub client accepted this item for local testing.",
                },
                ensure_ascii=False,
            )
        return (
            "Тестовый заголовок\n\n"
            "Коротко: это тестовый черновик для проверки Telegram-модерации.\n\n"
            "Он не предназначен для публикации, но помогает проверить кнопки и ветку."
        )


class FallbackAIClient(BaseAIClient):
    def __init__(
        self,
        primary: BaseAIClient,
        fallback: BaseAIClient | None,
        *,
        primary_timeout_seconds: float = 0.0,
    ) -> None:
        super().__init__(primary.prompt_store)
        self.primary = primary
        self.fallback = fallback
        self.primary_timeout_seconds = primary_timeout_seconds

    async def _complete(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        raise NotImplementedError

    async def complete(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        try:
            if self.primary_timeout_seconds > 0:
                return await asyncio.wait_for(
                    self.primary.complete(system_prompt, user_prompt, temperature=temperature),
                    timeout=self.primary_timeout_seconds,
                )
            return await self.primary.complete(system_prompt, user_prompt, temperature=temperature)
        except asyncio.TimeoutError:
            if self.fallback is None:
                raise AIClientError("Primary AI provider timed out") from None
            return await self.fallback.complete(system_prompt, user_prompt, temperature=temperature)
        except AIClientError:
            if self.fallback is None:
                raise
            return await self.fallback.complete(system_prompt, user_prompt, temperature=temperature)

    async def aclose(self) -> None:
        await self.primary.aclose()
        if self.fallback is not None:
            await self.fallback.aclose()


def create_ai_client(
    settings: Settings,
    *,
    model: str | None = None,
    notify: NotifyFn | None = None,
) -> BaseAIClient:
    prompt_store = PromptStore(settings.prompt_dir)
    primary_model = model or settings.ai_model
    primary = create_single_ai_client(
        settings.ai_provider,
        primary_model,
        settings.effective_ai_api_keys,
        settings.ai_base_url,
        prompt_store,
        settings.http_timeout_seconds,
        settings.ai_request_delay_seconds,
        notify=notify,
        label=gemini_label(primary_model),
    )
    fallback = None
    fallback_keys = settings.effective_fallback_api_keys
    if settings.ai_fallback_provider and fallback_keys:
        fallback = create_single_ai_client(
            settings.ai_fallback_provider,
            settings.ai_fallback_model,
            fallback_keys,
            settings.ai_fallback_base_url,
            prompt_store,
            settings.http_timeout_seconds,
            settings.ai_request_delay_seconds,
            notify=notify,
            label=gemini_label(settings.ai_fallback_model),
        )
    return FallbackAIClient(
        primary,
        fallback,
        primary_timeout_seconds=settings.ai_primary_timeout_seconds,
    )


def gemini_label(model: str) -> str:
    model_lower = model.lower()
    if "flash-lite" in model_lower:
        return "Flash Lite"
    if "flash" in model_lower:
        return "Flash"
    if "pro" in model_lower:
        return "Pro"
    return model


def create_single_ai_client(
    provider: str,
    model: str,
    api_key: str | list[str],
    base_url: str,
    prompt_store: PromptStore,
    timeout_seconds: float,
    request_delay_seconds: float = 0.0,
    *,
    notify: NotifyFn | None = None,
    label: str = "",
) -> BaseAIClient:
    provider_key = provider.lower()
    if provider_key == "stub":
        return StubAIClient(prompt_store)
    if provider_key == "gemini":
        return GeminiAIClient(
            prompt_store,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            request_delay_seconds=request_delay_seconds,
            notify=notify,
            label=label,
        )
    if provider_key in {"openrouter", "openai-compatible", "openai_compatible", "amvera"}:
        resolved_base_url = base_url or "https://openrouter.ai/api/v1"
        return OpenAICompatibleClient(
            prompt_store,
            api_key=api_key,
            base_url=resolved_base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            request_delay_seconds=request_delay_seconds,
        )
    raise AIClientError(f"Unsupported AI provider: {provider}")


async def post_json_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    json_payload: dict[str, Any],
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 3,
    request_delay_seconds: float = 0.0,
) -> httpx.Response:
    last_exc: httpx.HTTPError | None = None
    if request_delay_seconds > 0:
        await asyncio.sleep(request_delay_seconds)

    for attempt in range(attempts):
        try:
            response = await client.post(
                url,
                params=params,
                json=json_payload,
                headers=headers,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            status = exc.response.status_code
            if status not in RETRY_STATUSES or attempt == attempts - 1:
                raise
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
        retry_after = 0.0
        if isinstance(last_exc, httpx.HTTPStatusError):
            retry_after_header = last_exc.response.headers.get("Retry-After")
            if retry_after_header:
                try:
                    retry_after = float(retry_after_header)
                except ValueError:
                    retry_after = 0.0
        await asyncio.sleep(max(retry_after, 2 ** attempt))

    assert last_exc is not None
    raise last_exc


def parse_curator_response(text: str) -> CuratorDecision:
    data = extract_json_object(text)
    accept_raw = data.get("accept", data.get("should_publish", data.get("decision")))
    accept = parse_accept(accept_raw)
    try:
        score = int(data.get("score", data.get("ai_score", 0)))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(10, score))
    category = str(data.get("category") or "unknown").strip() or "unknown"
    reason = str(data.get("reason") or data.get("why") or "").strip()
    title_ru = str(data.get("title_ru") or "").strip()
    summary_ru = str(data.get("summary_ru") or "").strip()
    return CuratorDecision(accept=accept, score=score, category=category, reason=reason, title_ru=title_ru, summary_ru=summary_ru)


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = clean_ai_text(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise AIClientError(f"Curator did not return JSON: {text}")
        parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise AIClientError(f"Curator JSON is not an object: {text}")
    return parsed


def parse_accept(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    normalized = str(value or "").strip().casefold()
    return normalized in {"accept", "accepted", "approve", "publish", "yes", "true", "да"}

