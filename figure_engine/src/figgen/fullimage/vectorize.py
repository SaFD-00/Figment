"""장면 래스터 PNG → 편집 가능 벡터 SVG (vtracer).

FigureLabs식 deep-edit에 근접: 생성된 장면 이미지를 컬러 영역 ``<path>`` 레이어로 변환해
figure.svg가 Illustrator/Inkscape에서 path·색 단위로 편집 가능해진다.

정직한 한계: vtracer는 '의미 객체'가 아니라 '컬러 영역 path'를 만든다 — "대식세포"는 여러 색
blob이 된다. 즉 편집은 path/색 편집이지 "대식세포 선택"이 아니다. 의미 단위 편집은 향후 마스크
영역 재생성(OpenAI image edit + mask)으로 확장한다. PPTX는 벡터 path 임포트가 불가하여 장면이
래스터 그림으로 남는다(차트와 동일 한계). SVG/PNG 미리보기에서만 벡터 편집이 가능하다.

결정론: 고정 파라미터 + 동일 입력 바이트 → 동일 SVG. VECTORIZER_VERSION을 캐시/스토어 키 무효화에
사용한다.
"""

from __future__ import annotations

VECTORIZER_VERSION = "v1"

# 평면 음영 다색 과학 일러스트에 맞춘 보수적 파라미터(과한 speckle 억제, 부드러운 곡선).
_VTRACER_PARAMS: dict = {
    "colormode": "color",
    "hierarchical": "stacked",
    "mode": "spline",
    "filter_speckle": 6,
    "color_precision": 7,
    "layer_difference": 16,
    "corner_threshold": 60,
    "length_threshold": 4.0,
    "splice_threshold": 45,
    "path_precision": 3,
}


def vectorize_png(png: bytes) -> str:
    """PNG 바이트 → 레이어드 멀티컬러 SVG 문자열(결정론적). 실패 시 예외 전파."""
    import vtracer

    return vtracer.convert_raw_image_to_svg(png, img_format="png", **_VTRACER_PARAMS)
