"""Phase 4 — 차트 샌드박스 AST 검증 + 격리 실행."""

from __future__ import annotations

import tempfile
from pathlib import Path

from figgen.charts.sandbox import run_chart_code, validate_chart_code
from figgen.schema.style import StyleSheet

RC = StyleSheet(name="t").chart_rcparams()


def test_ast_rejects_os_import():
    assert validate_chart_code("import os\nax.plot([1,2])")


def test_ast_rejects_dunder_and_eval():
    assert validate_chart_code("ax.plot(eval('1+1'))")
    assert validate_chart_code("x = __import__('os')")


def test_ast_rejects_savefig():
    assert validate_chart_code("ax.plot([1,2]); fig.savefig('x.png')")


def test_ast_rejects_forbidden_substring():
    assert validate_chart_code("ax.plot([1]); import subprocess")  # double hit


def test_ast_accepts_valid():
    assert validate_chart_code("import numpy as np\nax.bar(['A','B'],[1,2])") == []


def test_run_produces_svg_and_png():
    res = run_chart_code("ax.bar(['A','B','C'],[3,5,2])", None, (120, 80), RC, timeout_s=40)
    assert res.ok
    assert res.png[:4] == b"\x89PNG"
    # svg.fonttype='none' → 텍스트가 벡터 path가 아닌 <text>로 유지 (Illustrator 편집 가능)
    assert "<text" in res.svg


def test_run_rejects_malicious_before_exec():
    res = run_chart_code("import os\nos.system('echo hi')", None, (120, 80), RC)
    assert not res.ok
    assert "import" in (res.stderr or "")


def test_run_uses_data_file_no_hardcode():
    d = Path(tempfile.mkdtemp()) / "data.csv"
    d.write_text("model,acc\nA,0.8\nB,0.9\n")
    res = run_chart_code("ax.bar(df['model'], df['acc'])", d, (120, 80), RC, timeout_s=40)
    assert res.ok and res.png[:4] == b"\x89PNG"
