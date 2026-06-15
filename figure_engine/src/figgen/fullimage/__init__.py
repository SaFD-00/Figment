"""풀 이미지 모드 — 베이스 AI 이미지 + 편집 가능 라벨 오버레이."""

from .composer import LabelProposal, build_overlay_spec, generate_base_image

__all__ = ["LabelProposal", "build_overlay_spec", "generate_base_image"]
