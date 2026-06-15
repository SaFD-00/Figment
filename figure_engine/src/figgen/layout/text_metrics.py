"""폰트 메트릭 기반 텍스트 실측 + 줄바꿈.

PPTX/SVG 두 렌더러의 줄바꿈을 강제로 일치시키기 위해, 레이아웃 단계에서 PIL 폰트
메트릭으로 1회 줄바꿈(``lines[]``)을 확정한다. PowerPoint/브라우저 실제 렌더와의 미세
차이는 안전 계수 ``SAFETY``로 보정한다.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import ImageFont
from pydantic import BaseModel

from ..schema.style import Font
from ..units import pt_to_mm

# pt→px 로딩 배율(서브-pt 정밀도). 측정 후 동일 배율로 되돌린다.
_METRIC_SCALE = 4.0
# PowerPoint/브라우저 렌더 폭 보정 안전 계수
SAFETY = 1.08
_LINE_LEADING = 1.25

_FALLBACK_CHAIN = ("Arial", "Helvetica", "Liberation Sans", "DejaVu Sans")


class Size(BaseModel):
    w: float = 0.0  # mm
    h: float = 0.0  # mm


class TextMetrics(BaseModel):
    width_mm: float
    height_mm: float
    lines: list[str]
    line_height_mm: float


@lru_cache(maxsize=256)
def _resolve_ttf(family: str, weight: str, italic: bool) -> str:
    """family(+폴백 체인) → ttf 경로. 최종 폴백은 matplotlib 번들 DejaVu Sans."""
    from matplotlib import font_manager as fm

    mpl_weight = {"regular": "normal", "medium": "medium", "bold": "bold"}.get(weight, "normal")
    style = "italic" if italic else "normal"
    fams = [family, *(_FALLBACK_CHAIN)]
    prop = fm.FontProperties(family=fams, weight=mpl_weight, style=style)
    return fm.findfont(prop, fallback_to_default=True)


@lru_cache(maxsize=512)
def _pil_font(path: str, size_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size_px)


class FontProvider:
    """Font → PIL FreeTypeFont 해석기 (lru 캐시)."""

    def __init__(self, fallback_chain: tuple[str, ...] = _FALLBACK_CHAIN):
        self.fallback_chain = fallback_chain

    def ttf_path(self, font: Font) -> str:
        return _resolve_ttf(font.family, font.weight, font.italic)

    def get(self, font: Font) -> ImageFont.FreeTypeFont:
        size_px = max(1, round(font.size_pt * _METRIC_SCALE))
        return _pil_font(self.ttf_path(font), size_px)

    # ── 측정 ──────────────────────────────────────────────────────────────────
    def _line_width_mm(self, text: str, font: Font) -> float:
        if not text:
            return 0.0
        pil = self.get(font)
        px = pil.getlength(text)
        return pt_to_mm(px / _METRIC_SCALE) * SAFETY

    def longest_word_width_mm(self, text: str, font: Font) -> float:
        """공백 분할 후 가장 긴 단어의 폭(mm). 이 폭 미만으로 박스를 줄이면 문자 단위
        줄바꿈이 강제되므로, 레이아웃 축소의 하한(min width)으로 쓴다."""
        best = 0.0
        for w in text.replace("\n", " ").split(" "):
            if w:
                best = max(best, self._line_width_mm(w, font))
        return best

    def measure_text(
        self, text: str, font: Font, max_width_mm: float | None = None
    ) -> TextMetrics:
        line_height_mm = pt_to_mm(font.size_pt * _LINE_LEADING)
        lines: list[str] = []
        for segment in text.split("\n"):
            if max_width_mm is None:
                lines.append(segment)
            else:
                lines.extend(self._wrap(segment, font, max_width_mm))
        if not lines:
            lines = [""]
        width_mm = max((self._line_width_mm(ln, font) for ln in lines), default=0.0)
        height_mm = line_height_mm * len(lines)
        return TextMetrics(
            width_mm=width_mm,
            height_mm=height_mm,
            lines=lines,
            line_height_mm=line_height_mm,
        )

    def _wrap(self, text: str, font: Font, max_width_mm: float) -> list[str]:
        words = text.split(" ")
        lines: list[str] = []
        cur = ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if self._line_width_mm(trial, font) <= max_width_mm or not cur:
                # 단어 단독으로도 폭 초과 → 문자 단위 분할
                if not cur and self._line_width_mm(word, font) > max_width_mm:
                    lines.extend(self._break_word(word, font, max_width_mm))
                    cur = lines.pop() if lines else ""
                else:
                    cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines or [""]

    def _break_word(self, word: str, font: Font, max_width_mm: float) -> list[str]:
        out: list[str] = []
        cur = ""
        for ch in word:
            if self._line_width_mm(cur + ch, font) <= max_width_mm or not cur:
                cur += ch
            else:
                out.append(cur)
                cur = ch
        if cur:
            out.append(cur)
        return out

    def fit_font_size(
        self, text: str, box: Size, font: Font, min_pt: float = 5.0
    ) -> float:
        """박스에 들어가는 최대 폰트 크기를 이진 탐색(critic text_clipping 대안)."""
        lo, hi = min_pt, font.size_pt
        if self._fits(text, box, font.model_copy(update={"size_pt": hi})):
            return hi
        for _ in range(20):
            mid = (lo + hi) / 2
            if self._fits(text, box, font.model_copy(update={"size_pt": mid})):
                lo = mid
            else:
                hi = mid
        return round(lo, 2)

    def _fits(self, text: str, box: Size, font: Font) -> bool:
        tm = self.measure_text(text, font, max_width_mm=box.w if box.w > 0 else None)
        return tm.width_mm <= box.w and tm.height_mm <= box.h
