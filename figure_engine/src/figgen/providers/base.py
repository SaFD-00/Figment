"""LLM/VLM/이미지 생성 provider 공통 인터페이스.

핵심 진입점은 ``LLMClient.complete_structured(schema=...)`` — VLM critic도 ``images`` 인자로
동일 메서드를 쓴다. provider별 구조적 출력 차이는 schema_transform이 흡수하고, 변환 불가 시
JSON-mode + Pydantic 검증 + repair가 공통 최후 방어선이다.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ImageInput(BaseModel):
    mime: str
    data: bytes

    model_config = {"arbitrary_types_allowed": True}


class Message(BaseModel):
    role: str = "user"  # 'user' | 'assistant'
    content: str
    images: list[ImageInput] = []


class AssetResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    data: bytes
    mime: str = "image/png"
    has_alpha: bool = False
    provider: str = ""
    revised_prompt: str | None = None


class StructuredOutputError(Exception):
    """구조적 출력 파싱/검증 실패 — repair 루프와 UI 에러 표시용."""

    def __init__(self, message: str, raw_text: str = "", validation_errors: str = ""):
        super().__init__(message)
        self.raw_text = raw_text
        self.validation_errors = validation_errors


@runtime_checkable
class LLMClient(Protocol):
    name: str

    async def complete(self, messages: list[Message], *, system: str = "",
                       temperature: float = 0.3) -> str: ...

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[T],
        *,
        system: str = "",
        images: list[ImageInput] | None = None,
        max_repair: int = 2,
    ) -> T: ...

    async def web_research(self, query: str, *, max_chars: int = 4000) -> str:
        """웹검색 그라운딩 — 과학적 맥락 텍스트를 반환(베스트-에포트, 실패 시 빈 문자열)."""
        ...


@runtime_checkable
class ImageClient(Protocol):
    name: str

    async def generate(
        self,
        prompt: str,
        *,
        width_px: int = 1024,
        height_px: int = 1024,
        transparent: bool = True,
        style_hint: str | None = None,
    ) -> AssetResult: ...

    async def edit(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        size: str | None = None,
        background: str = "auto",
        input_fidelity: str = "high",
        transparent: bool = False,
    ) -> AssetResult:
        """기존 이미지를 편집(인페인트/배경/업스케일) — figurelabs 인-캔버스·refiner 백본."""
        ...


def user(content: str, images: list[ImageInput] | None = None) -> Message:
    return Message(role="user", content=content, images=images or [])
