"""Catalog ↔ builder consistency: invariants + an exhaustive build sweep.

The sweep builds a well-formed graph for EVERY local model in EVERY mode it claims to support,
so a drifted template, a missing `files` key, or a removed/renamed model is caught immediately.
"""
import pytest

from app.comfy import builder as B
from app.models_catalog.registry import (
    CONTROLNET_FILES,
    DEFAULT_BY_MODE,
    LIGHTER_EQUIVALENT,
    MODELS,
    is_cloud,
    resolve,
)
from app.schemas.genspec import ControlType, GenSpec, Mode

LOCAL = {mid: m for mid, m in MODELS.items() if not is_cloud(m)}
REMOVED_IDS = {
    "qwen-image", "z-image", "pony-v6", "qwen-edit",          # anime-first / superseded
    "seedream-4.5", "flux2-max", "flux2-pro", "flux2-flex",   # dropped cloud image models
    "instantid", "ip-adapter", "pulid-flux",                 # identity merged into qwen-edit/redux
    "sdxl-inpaint", "kontext",                                # consolidated (flux-fill / qwen-edit)
    "wan22-t2v", "wan22-i2v",                                 # video consolidated to wan22-ti2v (5B)
}


def _spec_ctx(build_ctx, model_id: str, mode: Mode):
    """A minimal valid (GenSpec, BuildContext) for a model in a mode (satisfies GenSpec validators)."""
    fields: dict = {"mode": mode, "model": model_id, "prompt": "x"}
    kw: dict = {}
    if mode in (Mode.img2img, Mode.edit):
        fields["source_asset"] = "s"
        kw["src"] = "imggen/s.png"
    if mode == Mode.inpaint:
        fields.update(source_asset="s", mask_asset="m")
        kw.update(src="imggen/s.png", mask="imggen/m.png")
    if mode in (Mode.controlnet, Mode.reference):
        kw["refs"] = ["imggen/r.png"]
    if mode == Mode.video and "i2v" in model_id:  # image→video needs a start frame
        fields["source_asset"] = "s"
        kw["src"] = "imggen/s.png"
    return GenSpec(**fields), build_ctx(model_id, **kw)


# ── exhaustive build sweep ───────────────────────────────────────────────────
_CASES = [(mid, mode) for mid, m in LOCAL.items() for mode in m.supports]


@pytest.mark.parametrize("model_id,mode", _CASES, ids=[f"{mid}-{mode.value}" for mid, mode in _CASES])
def test_every_local_model_builds(model_id, mode, build_ctx, assert_graph, assert_video_graph):
    spec, ctx = _spec_ctx(build_ctx, model_id, mode)
    res = B.build(spec, ctx)
    (assert_video_graph if mode == Mode.video else assert_graph)(res)


# ── catalog invariants ───────────────────────────────────────────────────────
def test_removed_models_are_gone():
    assert REMOVED_IDS.isdisjoint(MODELS), f"stale model ids still present: {REMOVED_IDS & set(MODELS)}"


def test_every_template_is_dispatched():
    """A model.template that isn't in the dispatch would silently fall back to SDXL — catch it.
    (controlnet/img2img are dispatched by mode, not template, so they need no template entry.)"""
    for mid, m in LOCAL.items():
        if m.template:
            assert m.template in B._TEMPLATE_DISPATCH, f"{mid}: template {m.template!r} not dispatched"


def test_default_by_mode_covers_every_mode():
    for mode in Mode:
        assert mode in DEFAULT_BY_MODE, f"no default model for mode {mode}"
        default_id = DEFAULT_BY_MODE[mode]
        assert default_id in MODELS, f"default for {mode} is unknown id {default_id!r}"
        assert mode in MODELS[default_id].supports, f"{default_id} does not support its default mode {mode}"


def test_resolve_picks_a_supporting_local_model_per_mode():
    for mode in Mode:
        if mode == Mode.figure:
            continue  # figure is a cloud-only mode (no local backend) — see DEFAULT_BY_MODE
        m = resolve(None, mode)
        assert not is_cloud(m), f"default for {mode} should be local, got {m.id}"
        assert mode in m.supports


def test_controlnet_files_cover_every_control_type():
    for ctype in ControlType.__args__:  # type: ignore[attr-defined]
        assert ctype in CONTROLNET_FILES, f"no ControlNet file mapped for control type {ctype!r}"


def test_lighter_equivalent_ids_are_valid():
    for src, alt in LIGHTER_EQUIVALENT.items():
        assert src in MODELS and alt in MODELS, f"LIGHTER_EQUIVALENT[{src}]={alt} references unknown id"


def test_video_models_are_kind_video():
    for mid, m in LOCAL.items():
        if Mode.video in m.supports:
            assert m.kind == "video", f"{mid} supports video but kind={m.kind!r}"
        else:
            assert m.kind == "image", f"{mid} is not a video model but kind={m.kind!r}"


def test_core_photoreal_bases_are_natively_nsfw():
    """The natively-uncensored local picks must be flagged nsfw."""
    for mid in ("chroma-hd", "lustify", "flux-fill", "qwen-edit-aio", "redux", "wan22-ti2v"):
        assert MODELS[mid].nsfw, f"{mid} should be flagged nsfw (natively uncensored)"
