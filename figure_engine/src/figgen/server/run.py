"""`figgen serve` — uvicorn 기동 + 브라우저 자동 오픈 (127.0.0.1, 포트 충돌 시 자동 증가)."""

from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from ..config import get_settings


def _free_port(host: str, start: int, tries: int = 20) -> int:
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start


def _open_when_ready(url: str, health: str) -> None:
    def _poll():
        for _ in range(60):
            try:
                with urllib.request.urlopen(health, timeout=0.5) as r:
                    if r.status == 200:
                        webbrowser.open(url)
                        return
            except Exception:  # noqa: BLE001
                time.sleep(0.4)

    threading.Thread(target=_poll, daemon=True).start()


def serve(
    *,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool = True,
    outputs: Path | None = None,
    reload: bool = False,
) -> int:
    import uvicorn

    if outputs is not None:
        os.environ["FIGGEN_OUTPUTS"] = str(outputs)
        get_settings.cache_clear()
    settings = get_settings()
    host = host or settings.host
    port = _free_port(host, port or settings.port)
    url = f"http://{host}:{port}"

    print(f"· FigGen 서버: {url}")
    print(f"· outputs: {settings.resolved_outputs_dir()}")
    print(f"· providers: {sorted(settings.available_providers())}")
    if open_browser and not reload:
        _open_when_ready(url, f"{url}/api/health")

    uvicorn.run("figgen.server.app:create_app", factory=True, host=host, port=port,
                reload=reload, log_level="info")
    return 0
