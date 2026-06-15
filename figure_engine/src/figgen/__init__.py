"""FigGen — 논문용 figure 생성 프레임워크.

LLM은 의미·구조만 담은 FigureSpec(JSON)을 생성하고, 결정론적 Python 렌더러가
PowerPoint/Illustrator에서 후편집 가능한 PPTX+SVG를 동시 산출한다.
"""

__version__ = "0.1.0"

# cairosvg(cairocffi)가 Homebrew libcairo를 찾도록 dlopen 검색 경로를 보강한다.
from ._native import ensure_native_libs  # noqa: E402

ensure_native_libs()
