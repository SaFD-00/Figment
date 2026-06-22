"""Shared fixtures for the ComfyUI graph-builder tests.

`asyncio_mode = "auto"` (pyproject) lets async tests run without decorators.
"""
import pytest

from app.comfy import builder as B
from app.models_catalog.registry import MODELS


def _check_links(graph: dict) -> None:
    """Every node is well-formed and every [node_id, idx] link points to an existing node."""
    assert isinstance(graph, dict) and graph
    for nid, node in graph.items():
        assert "class_type" in node and "inputs" in node, f"node {nid} malformed"
        for v in node["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in graph, f"node {nid} links to missing node {v[0]}"


@pytest.fixture
def build_ctx():
    """Factory: build a BuildContext for a model id with optional src/mask/refs."""
    def _make(model_id: str, **kw) -> B.BuildContext:
        return B.BuildContext(
            model=MODELS[model_id],
            width=kw.get("width", 1024), height=kw.get("height", 1024),
            comfy_source=kw.get("src"), comfy_mask=kw.get("mask"),
            comfy_refs=kw.get("refs", []),
        )
    return _make


@pytest.fixture
def assert_graph():
    """Assert an image build result is well-formed and ends in a SaveImage node."""
    def _f(result: B.BuildResult) -> None:
        _check_links(result.graph)
        assert result.save_node in result.graph
        assert result.graph[result.save_node]["class_type"] == "SaveImage"
        assert not result.is_video
    return _f


@pytest.fixture
def assert_video_graph():
    """Assert a video build result is well-formed and flagged is_video (webp save node)."""
    def _f(result: B.BuildResult) -> None:
        _check_links(result.graph)
        assert result.save_node in result.graph
        assert result.is_video
    return _f
