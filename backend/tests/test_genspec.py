"""GenSpec schema: the H100 retarget additions (video mode, pose, larger canvas, video fields)
plus the pre-existing mode/consistency validators."""
import pytest
from pydantic import ValidationError

from app.schemas.genspec import GenSpec, Mode


def test_video_mode_and_fields():
    spec = GenSpec(mode=Mode.video, prompt="clip", video_frames=121, video_fps=24)
    assert spec.mode == Mode.video
    assert spec.video_frames == 121 and spec.video_fps == 24


def test_video_field_defaults():
    spec = GenSpec(mode=Mode.video, prompt="clip")
    assert spec.video_frames == 81 and spec.video_fps == 16


@pytest.mark.parametrize("frames", [8, 242])
def test_video_frames_out_of_range_rejected(frames):
    with pytest.raises(ValidationError):
        GenSpec(mode=Mode.video, prompt="x", video_frames=frames)


def test_pose_controlnet_type():
    spec = GenSpec(mode=Mode.controlnet, prompt="x", controlnet_type="pose")
    assert spec.controlnet_type == "pose"


def test_controlnet_defaults_to_canny():
    spec = GenSpec(mode=Mode.controlnet, prompt="x")
    assert spec.controlnet_type == "canny"


def test_canvas_size_cap_raised_to_2048():
    GenSpec(mode=Mode.txt2img, prompt="x", width=2048, height=2048)  # ok now (was capped at 1536)
    with pytest.raises(ValidationError):
        GenSpec(mode=Mode.txt2img, prompt="x", width=2049)


def test_img2img_requires_source():
    with pytest.raises(ValidationError):
        GenSpec(mode=Mode.img2img, prompt="x")


def test_inpaint_requires_source_and_mask():
    with pytest.raises(ValidationError):
        GenSpec(mode=Mode.inpaint, prompt="x", source_asset="s")  # missing mask


def test_too_many_reference_images_rejected():
    refs = [{"asset": f"a{i}"} for i in range(7)]
    with pytest.raises(ValidationError):
        GenSpec(mode=Mode.reference, prompt="x", reference_images=refs)
