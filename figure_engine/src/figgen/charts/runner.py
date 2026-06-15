"""차트 서브프로세스 내부 실행 엔트리 (메인 프로세스와 격리).

계약: 생성 코드는 주입된 ``ax``에 그리기만 한다(savefig/show 금지 — 하네스가 통제).
모든 수치는 주입된 ``df``에서만 — 데이터 환각 차단. svg.fonttype='none'으로 텍스트 벡터 유지.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _set_limits() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
        if not sys.platform == "darwin":  # macOS는 RLIMIT_AS가 라이브러리 로드를 깨뜨릴 수 있음
            resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    except Exception:  # noqa: BLE001
        pass


def main(workdir: str) -> int:
    _set_limits()
    wd = Path(workdir)
    meta = json.loads((wd / "meta.json").read_text("utf-8"))
    size_pt = meta.get("size_pt", [120, 90])
    rc = meta.get("rc", {})

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if isinstance(rc.get("axes.prop_cycle"), str):
        from cycler import cycler

        rc["axes.prop_cycle"] = cycler(color=rc["axes.prop_cycle"].split("+"))
    for k, v in rc.items():
        try:
            plt.rcParams[k] = v
        except Exception:  # noqa: BLE001
            pass
    plt.rcParams["svg.fonttype"] = "none"

    pd = None
    df = None
    try:
        import pandas as pd  # noqa: PLC0415

        if (wd / "data.csv").exists():
            df = pd.read_csv(wd / "data.csv")
    except Exception:  # noqa: BLE001
        pd = None

    figsize = (max(0.5, size_pt[0] / 72.0), max(0.5, size_pt[1] / 72.0))
    fig, ax = plt.subplots(figsize=figsize)
    code = (wd / "code.py").read_text("utf-8")
    ns = {"plt": plt, "np": np, "pd": pd, "df": df, "fig": fig, "ax": ax}
    exec(compile(code, "<chart>", "exec"), ns)  # noqa: S102
    try:
        fig.tight_layout()
    except Exception:  # noqa: BLE001
        pass
    fig.savefig(wd / "out.svg")
    fig.savefig(wd / "out.png", dpi=300)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
