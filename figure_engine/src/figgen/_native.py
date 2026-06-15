"""네이티브 라이브러리 로딩 보정.

cairosvg는 cairocffi를 통해 libcairo를 dlopen하는데, uv/pyenv로 설치한 Python은
Homebrew(`/opt/homebrew/lib`)·MacPorts 경로를 dlopen 검색 경로에 포함하지 않는다.
`ctypes.util.find_library`를 보강해 시스템 탐색 실패 시 일반 패키지 매니저 경로에서
`lib<name>.dylib`를 찾아주도록 한다(re-exec·환경변수 불필요, 프로세스 내 해결).
"""

from __future__ import annotations

import ctypes.util
import os
import sys

_EXTRA_LIB_DIRS = ("/opt/homebrew/lib", "/usr/local/lib", "/opt/local/lib")
_applied = False


def ensure_native_libs() -> None:
    """`find_library` 폴백 보강을 1회 적용한다(idempotent)."""
    global _applied
    if _applied or sys.platform != "darwin":
        _applied = True
        return

    _orig = ctypes.util.find_library

    def _patched(name: str):  # pragma: no cover - 환경 의존
        found = _orig(name)
        if found:
            return found
        for d in _EXTRA_LIB_DIRS:
            for cand in (f"lib{name}.dylib", f"lib{name}.2.dylib", f"lib{name}-2.dylib"):
                p = os.path.join(d, cand)
                if os.path.exists(p):
                    return p
        return found

    ctypes.util.find_library = _patched
    _applied = True
