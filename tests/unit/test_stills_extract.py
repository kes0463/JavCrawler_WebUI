"""javstory.library.stills.extract — cv2 목."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from javstory.library.canonical.schema import SceneEntry
from javstory.library.stills import extract as ex_mod
from javstory.library.stills.extract import scene_time_bounds


def test_scene_time_bounds_from_range() -> None:
    sc = SceneEntry(scene_id="x", time_range="00:01:00 ~ 00:02:00")
    a, b = scene_time_bounds(sc)
    assert a == 60.0
    assert b == 120.0


def test_extract_frames_mocked(tmp_path: Path) -> None:
    fake_frame = object()
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.read.side_effect = [(True, fake_frame), (True, fake_frame)]

    imwrite_calls: list[str] = []

    def _imwrite(path: str, frame: object, *args: object) -> bool:
        imwrite_calls.append(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"jpeg")
        return True

    cv2_mod = MagicMock()
    cv2_mod.VideoCapture.return_value = cap
    cv2_mod.CAP_PROP_POS_MSEC = 0
    cv2_mod.imwrite = _imwrite
    cv2_mod.IMWRITE_JPEG_QUALITY = 1

    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "out"

    with patch.object(ex_mod, "cv2", cv2_mod):
        paths = ex_mod.extract_frames(video, [1.0, 2.0], out_dir, prefix="s")

    assert len(paths) == 2
    assert len(imwrite_calls) == 2
