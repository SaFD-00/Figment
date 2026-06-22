"""`.env` 기반 설정 — API 키, 역할별 모델 ID, 서버, 경로를 단일 통합한다.

모든 모델 ID는 환경변수로 오버라이드 가능하다(모델명 preview 불안정 대비).
provider는 **OpenRouter 단일**이며, 키가 없으면 ``mock``으로 안전 폴백해 오프라인 구동된다.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_font_dirs() -> list[Path]:
    """플랫폼별 시스템 폰트 디렉토리. FontProvider 폴백의 기본 검색 경로."""
    if sys.platform == "darwin":
        return [
            Path("/System/Library/Fonts/Supplemental"),
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    if sys.platform.startswith("linux"):
        return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    if sys.platform.startswith("win"):
        return [Path("C:/Windows/Fonts")]
    return []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ── API 키 (OpenRouter 단일 + mock 오프라인 폴백) ─────────────────────────
    openrouter_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key")
    )

    # ── provider/모델 기본값 (모두 FIGGEN_* 로 오버라이드) ────────────────────
    # provider: mock | openrouter | auto. 모델 ID는 OpenRouter 슬러그.
    provider_default: str = Field(
        default="openrouter", validation_alias=AliasChoices("FIGGEN_PROVIDER", "provider_default")
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("FIGGEN_OPENROUTER_BASE_URL", "openrouter_base_url"),
    )
    # LLM 라인업은 vision-capable 전용 — 모든 추론 역할 기본값을 멀티모달(VL) 슬러그로 둔다.
    planner_model: str = Field(
        default="google/gemini-2.5-flash",
        validation_alias=AliasChoices("FIGGEN_PLANNER_MODEL", "planner_model"),
    )
    classifier_model: str = Field(
        default="google/gemini-2.5-flash",
        validation_alias=AliasChoices("FIGGEN_CLASSIFIER_MODEL", "classifier_model"),
    )
    # critic(VLM)·sketch·참조 분석 비전 호출용 — 멀티모달(VL) 가능 모델 필요.
    vision_model: str = Field(
        default="google/gemini-2.5-flash",
        validation_alias=AliasChoices("FIGGEN_VISION_MODEL", "FIGGEN_CRITIC_MODEL", "vision_model"),
    )
    chart_coder_model: str = Field(
        default="google/gemini-2.5-flash",
        validation_alias=AliasChoices("FIGGEN_CHART_CODER_MODEL", "chart_coder_model"),
    )
    # 이미지 생성 모델. API default는 .env의 FIGGEN_DEFAULT_IMAGER(google/gemini-3.1-flash-image);
    # env 미설정 시 이 소스 기본값(openai/gpt-5.4-image-2)으로 폴백한다.
    image_model: str = Field(
        default="openai/gpt-5.4-image-2",   # fallback slug (VERIFY)
        validation_alias=AliasChoices("FIGGEN_DEFAULT_IMAGER", "image_model"),
    )

    # ── research (웹검색 그라운딩) ────────────────────────────────────────────
    # 생성 전 OpenRouter ``:online`` 변종으로 과학적 맥락을 수집해 planner 프롬프트를 보강.
    research_enabled_default: bool = Field(
        default=False,
        validation_alias=AliasChoices("FIGGEN_RESEARCH_ENABLED", "research_enabled_default"),
    )
    research_model: str = Field(
        default="google/gemini-2.5-flash",
        validation_alias=AliasChoices("FIGGEN_RESEARCH_MODEL", "research_model"),
    )
    research_max_chars: int = Field(
        default=4000,
        validation_alias=AliasChoices("FIGGEN_RESEARCH_MAX_CHARS", "research_max_chars"),
    )

    # ── critic ──────────────────────────────────────────────────────────────
    critic_enabled: bool = Field(
        default=True, validation_alias=AliasChoices("FIGGEN_CRITIC_ENABLED", "critic_enabled")
    )
    max_critic_iters: int = Field(
        default=2, validation_alias=AliasChoices("FIGGEN_MAX_CRITIC_ITERS", "max_critic_iters")
    )

    # ── 장면 일러스트 ──────────────────────────────────────────────────────────
    # scientific_illustration 장면 아트를 벡터화(vtracer)해 SVG에서 편집 가능하게 한다.
    scene_vectorize: bool = Field(
        default=True, validation_alias=AliasChoices("FIGGEN_SCENE_VECTORIZE", "scene_vectorize")
    )
    # method_diagram의 각 박스에 작은 과학 일러스트(icon_asset)를 생성·삽입(박스당 이미지 1콜).
    # 비용이 크므로 기본 OFF — CLI --box-icons 또는 FIGGEN_DIAGRAM_BOX_ICONS=true로 켠다.
    diagram_box_icons: bool = Field(
        default=False,
        validation_alias=AliasChoices("FIGGEN_DIAGRAM_BOX_ICONS", "diagram_box_icons"),
    )

    # ── 서버 ────────────────────────────────────────────────────────────────
    host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("FIGGEN_HOST", "host"))
    port: int = Field(default=8736, validation_alias=AliasChoices("FIGGEN_PORT", "port"))
    max_concurrent_jobs: int = Field(
        default=2,
        validation_alias=AliasChoices("FIGGEN_MAX_CONCURRENT_JOBS", "max_concurrent_jobs"),
    )

    # ── 경로 ────────────────────────────────────────────────────────────────
    outputs_dir: Path = Field(
        default=Path("outputs"), validation_alias=AliasChoices("FIGGEN_OUTPUTS", "outputs_dir")
    )
    asset_cache_dir: Path = Field(
        default=Path.home() / ".figgen" / "assets_cache",
        validation_alias=AliasChoices("FIGGEN_ASSET_CACHE", "asset_cache_dir"),
    )
    font_dirs: list[Path] = Field(default_factory=_default_font_dirs)

    # ── 헬퍼 ────────────────────────────────────────────────────────────────
    def resolved_outputs_dir(self) -> Path:
        """비어 있으면 ./outputs, ~ 확장 후 절대경로."""
        p = self.outputs_dir if str(self.outputs_dir) else Path("outputs")
        return p.expanduser().resolve()

    def resolved_asset_cache_dir(self) -> Path:
        # 비어 있으면(.env에 FIGGEN_ASSET_CACHE= → Path('.')) 홈 기본값.
        # 빈 값을 그대로 resolve하면 cwd(=Drive 동기화 프로젝트 루트)에 캐시가 쏟아진다.
        p = self.asset_cache_dir
        if not str(p) or str(p) == ".":
            p = Path.home() / ".figgen" / "assets_cache"
        return p.expanduser().resolve()

    def available_providers(self) -> set[str]:
        """키 보유 여부로 사용 가능한 provider 집합. mock은 항상 가용.

        빈 문자열 키(`.env`에 ``OPENROUTER_API_KEY=``)는 미보유로 취급한다.
        """
        providers = {"mock"}
        if self.openrouter_api_key and self.openrouter_api_key.get_secret_value().strip():
            providers.add("openrouter")
        return providers

    def has_key(self, provider: str) -> bool:
        return provider in self.available_providers()


@lru_cache
def get_settings() -> Settings:
    """프로세스 단일 Settings 싱글턴."""
    return Settings()
