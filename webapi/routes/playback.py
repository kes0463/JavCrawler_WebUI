from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from javstory.services.playback_service import PlaybackService, guess_video_mime
from webapi.schemas import PlaybackInfo, StreamPrepareResponse, SubtitleCueList

router = APIRouter()
_playback = PlaybackService()


@router.get("/{code}", response_model=PlaybackInfo)
def get_playback_info(code: str):
    info = _playback.playback_info(code)
    if not info:
        raise HTTPException(404, "재생 가능한 영상을 찾을 수 없습니다")
    return PlaybackInfo(**info)


@router.get("/{code}/stream/{part}/prepare", response_model=StreamPrepareResponse)
def prepare_stream(code: str, part: int):
    result = _playback.prepare_stream(code, part)
    if not result:
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")
    return StreamPrepareResponse(**result)


@router.get("/{code}/stream/{part}")
def stream_video(code: str, part: int):
    path = _playback.resolve_stream_path(code, part)
    if not path:
        prep = _playback.prepare_stream(code, part)
        if prep and prep.get("status") == "building":
            raise HTTPException(503, "브라우저 재생용 MP4 변환 중입니다. 잠시 후 다시 시도하세요.")
        if prep and prep.get("status") == "failed":
            raise HTTPException(500, prep.get("error") or "프록시 변환에 실패했습니다")
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")
    return FileResponse(
        str(path),
        media_type=guess_video_mime(path),
        filename=path.name,
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/{code}/subtitles/{part}/{track}", response_model=SubtitleCueList)
def get_subtitle_cues(code: str, part: int, track: int):
    cues = _playback.subtitle_cues(code, part, track)
    if not cues and _playback.resolve_subtitle_path(code, part, track) is None:
        raise HTTPException(404, "자막을 찾을 수 없습니다")
    return SubtitleCueList(cues=cues)
