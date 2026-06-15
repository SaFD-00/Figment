"""LLM 생성 matplotlib 코드의 AST 검증 + 서브프로세스 격리 실행.

이중 방어: ①AST 사전검증(import 화이트리스트 + 금지 이름) ②별도 subprocess(rlimit, Agg,
임시 cwd, 타임아웃). LLM 코드는 신뢰 불가하므로 실데이터를 코드에 직접 전달해 수치 환각도 차단.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel

ALLOWED_IMPORTS = {
    "matplotlib", "matplotlib.pyplot", "matplotlib.ticker", "matplotlib.colors",
    "numpy", "pandas", "math",
}
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "__import__", "compile", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
}
_FORBIDDEN_SUBSTR = ("os.", "sys.", "subprocess", "shutil", "socket", "requests",
                     "urllib", "pathlib", "__builtins__", "importlib")


class ChartResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    svg: str = ""
    png: bytes = b""
    code: str = ""
    stderr: str | None = None
    ok: bool = False


def validate_chart_code(code: str) -> list[str]:
    """위반 목록 반환(비면 통과). 위반 시 LLM 재생성 피드백으로 사용."""
    violations: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"문법 오류: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in {i.split(".")[0] for i in ALLOWED_IMPORTS}:
                    violations.append(f"허용되지 않은 import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in {i.split(".")[0] for i in ALLOWED_IMPORTS}:
                violations.append(f"허용되지 않은 import-from: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_NAMES:
                violations.append(f"금지된 호출: {node.func.id}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            violations.append(f"금지된 이름 참조: {node.id}")
        elif isinstance(node, (ast.Attribute,)) and node.attr in ("savefig", "show"):
            violations.append("savefig/show 금지 — 하네스가 저장을 통제")

    for s in _FORBIDDEN_SUBSTR:
        if s in code:
            violations.append(f"금지 패턴: {s}")
    return sorted(set(violations))


def run_chart_code(
    code: str,
    data_path: Path | None,
    size_pt: tuple[float, float],
    chart_rcparams: dict,
    timeout_s: int = 30,
) -> ChartResult:
    """AST 검증 통과 코드를 subprocess 격리 실행 → SVG(fonttype=none) + 300dpi PNG."""
    violations = validate_chart_code(code)
    if violations:
        return ChartResult(code=code, stderr="; ".join(violations), ok=False)

    with tempfile.TemporaryDirectory(prefix="figgen_chart_") as td:
        tmp = Path(td)
        (tmp / "code.py").write_text(code, encoding="utf-8")
        (tmp / "meta.json").write_text(json.dumps({
            "size_pt": list(size_pt), "rc": chart_rcparams}), encoding="utf-8")
        if data_path and Path(data_path).exists():
            (tmp / "data.csv").write_bytes(Path(data_path).read_bytes())
        mpl_dir = tmp / ".mpl"
        mpl_dir.mkdir(exist_ok=True)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "figgen.charts.runner", str(tmp)],
                capture_output=True, timeout=timeout_s, cwd=str(tmp),
                env={
                    "MPLBACKEND": "Agg",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "MPLCONFIGDIR": str(mpl_dir),
                    "PATH": "/usr/bin:/bin",
                },
            )
        except subprocess.TimeoutExpired:
            return ChartResult(code=code, stderr=f"타임아웃 {timeout_s}s", ok=False)
        if proc.returncode != 0:
            return ChartResult(code=code, stderr=proc.stderr.decode("utf-8", "replace")[:600], ok=False)
        svg = (tmp / "out.svg").read_text("utf-8") if (tmp / "out.svg").exists() else ""
        png = (tmp / "out.png").read_bytes() if (tmp / "out.png").exists() else b""
        return ChartResult(svg=svg, png=png, code=code, ok=bool(svg and png))
