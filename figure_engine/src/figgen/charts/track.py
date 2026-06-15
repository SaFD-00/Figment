"""데이터 차트 전용 트랙: matplotlib 코드 생성 → 샌드박스 실행 → 에셋화.

실데이터(헤더+샘플)를 프롬프트에 포함하되 전체는 파일로 전달, 수치 직접 기입 금지.
산출물은 svg.fonttype='none' SVG(Illustrator 편집) + 300dpi PNG(PPTX). 코드도 에셋 보존.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..assets.store import AssetStore
from ..providers.base import LLMClient, user
from ..schema.figure_spec import ChartElement
from ..schema.style import StyleSheet
from .sandbox import run_chart_code

_SYSTEM = (
    "You write matplotlib code that draws ONE chart on the pre-created `ax` using pandas `df` "
    "(may be None). RULES: draw only on `ax`; NEVER call savefig/show/plt.subplots/plt.figure; "
    "import only matplotlib/numpy/pandas/math; read numbers ONLY from `df` columns (never hardcode "
    "data values if df is provided). Return ChartCode {code, expects_data_file}."
)


class ChartCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    expects_data_file: bool = False


class ChartTrack:
    def __init__(self, llm: LLMClient, assets: AssetStore):
        self.llm = llm
        self.assets = assets

    async def build(
        self,
        chart: ChartElement,
        data_path: Path | None,
        stylesheet: StyleSheet,
        size_pt: tuple[float, float] = (160.0, 110.0),
    ) -> ChartElement:
        data_hint = _data_hint(data_path)
        rc = stylesheet.chart_rcparams()
        feedback = ""
        last_err = None
        for _ in range(3):
            prompt = (
                f"Chart kind: {chart.chart_kind}. Goal: {chart.brief}.\n"
                f"{data_hint}\n{feedback}"
            )
            cc = await self.llm.complete_structured([user(prompt)], ChartCode, system=_SYSTEM)
            result = run_chart_code(cc.code, data_path, size_pt, rc)
            if result.ok:
                svg_id, code_id = self.assets.put_chart(result.svg, result.png, result.code)
                return chart.model_copy(update={"svg_asset_id": svg_id, "code_asset_id": code_id})
            last_err = result.stderr
            feedback = f"이전 코드가 실패했습니다. 오류: {last_err}. 수정해 다시 작성하세요."
        # 실패 → placeholder 유지(svg_asset_id None)
        return chart.model_copy(update={"code_asset_id": None})


def _data_hint(data_path: Path | None) -> str:
    if not data_path or not Path(data_path).exists():
        return "No data file provided — you may use a small illustrative dataset described by the goal."
    try:
        lines = Path(data_path).read_text("utf-8").splitlines()[:6]
        return ("Data is in df (pandas, read from data.csv). Header + sample rows:\n"
                + "\n".join(lines))
    except Exception:  # noqa: BLE001
        return "Data is available in df."
