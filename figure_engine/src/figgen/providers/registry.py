"""역할(planner/critic/classifier/chart_coder/editor/research)→클라이언트 라우팅.

실 provider는 **OpenRouter 단일**(LLM=qwen/qwen3.7-plus 등, 이미지=bytedance-seed/seedream-4.5).
provider='auto'/키 없음/명시 mock이면 mock으로 안전 폴백(오프라인 구동).
"""

from __future__ import annotations

from typing import Literal

from ..config import Settings
from .base import ImageClient, LLMClient
from .mock_client import MockImageClient, MockLLMClient

Role = Literal["planner", "critic", "classifier", "chart_coder", "editor", "research"]

# 역할별 모델 속성명(provider 무관 — OpenRouter/OpenAI 공통 슬러그 필드).
_ROLE_ATTR: dict[str, str] = {
    "planner": "planner_model",
    "editor": "planner_model",
    "chart_coder": "chart_coder_model",
    "critic": "vision_model",
    "classifier": "classifier_model",
    "research": "research_model",
}


def _model_for(role: str, settings: Settings) -> str:
    return getattr(settings, _ROLE_ATTR[role])


def _resolve_provider(role: str, settings: Settings, override: str | None) -> str:
    provider = override or settings.provider_default
    if provider == "auto":
        return "openrouter" if settings.has_key("openrouter") else "mock"
    if provider != "mock" and not settings.has_key(provider):
        return "mock"  # 키 없음(또는 미지원 provider) → 안전 폴백
    return provider


def get_llm(role: Role, settings: Settings, *, provider_override: str | None = None) -> LLMClient:
    provider = _resolve_provider(role, settings, provider_override)
    model = _model_for(role, settings)
    if provider == "openrouter":
        from .openrouter_client import OpenRouterClient

        return OpenRouterClient(
            settings.openrouter_api_key.get_secret_value(),
            model,
            base_url=settings.openrouter_base_url,
        )
    return MockLLMClient()


def get_image_client(
    settings: Settings,
    *,
    hint: str | None = None,
    transparent: bool = False,
    provider_override: str | None = None,
) -> ImageClient:
    """이미지 생성 클라이언트. OpenRouter(SeeDream 4.5 등)·mock 안전 폴백.

    ``hint``는 호환용 no-op(과거 분기 잔재).
    """
    provider = _resolve_provider("planner", settings, provider_override)
    if provider == "openrouter":
        from .openrouter_client import OpenRouterImageClient

        return OpenRouterImageClient(
            settings.openrouter_api_key.get_secret_value(),
            settings.image_model,
            base_url=settings.openrouter_base_url,
        )
    return MockImageClient()
