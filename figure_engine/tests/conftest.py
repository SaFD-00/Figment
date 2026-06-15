"""테스트 공용 픽스처.

전역 에셋 캐시(`~/.figgen/assets_cache`, 또는 .env에서 FIGGEN_ASSET_CACHE 미설정 시 cwd로
오해석되던 경로)를 매 테스트마다 임시 디렉토리로 격리한다. 테스트가 실제 캐시(또는 Drive 동기화
프로젝트 루트)에 PNG/JSON을 흘리지 않게 한다.
"""

from __future__ import annotations

import pytest

from figgen.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_asset_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGGEN_ASSET_CACHE", str(tmp_path / "asset_cache"))
    monkeypatch.setenv("FIGGEN_OUTPUTS", str(tmp_path / "outputs"))
    # hermetic — 주변 .env의 실제 API 키와 무관하게 모든 테스트를 오프라인 mock으로 강제.
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("FIGGEN_PROVIDER", "mock")
    get_settings.cache_clear()  # .env 캐시된 싱글턴 무효화 → 격리 env 재로딩
    yield
    get_settings.cache_clear()
