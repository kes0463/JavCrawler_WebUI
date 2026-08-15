from __future__ import annotations



from fastapi import APIRouter, HTTPException

from fastapi.responses import FileResponse



from javstory.services.playback_service import PlaybackService, guess_video_mime

from webapi.schemas import (

    PlaybackInfo,

    ProxyCacheClearResult,

    ProxyCacheStats,

    StreamPrepareResponse,

    SubtitleCueList,

)



router = APIRouter()

_playback = PlaybackService()





@router.get("/cache/stats", response_model=ProxyCacheStats)

def get_proxy_cache_stats():

    from javstory.services.proxy_cache_service import cache_stats



    return ProxyCacheStats(**cache_stats())





@router.post("/cache/clear", response_model=ProxyCacheClearResult)

def clear_proxy_cache():

    from javstory.services.proxy_cache_service import clear_cache



    result = clear_cache()

    return ProxyCacheClearResult(ok=True, **result)





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
            raise HTTPException(503, "브라우저 재생용 HLS 변환 중입니다. 잠시 후 다시 시도하세요.")
        if prep and prep.get("needs_proxy"):
            raise HTTPException(503, "브라우저 재생용 HLS를 사용하세요.")
        if prep and prep.get("status") == "failed":
            raise HTTPException(500, prep.get("error") or "프록시 변환에 실패했습니다")
        raise HTTPException(404, "영상 파일을 찾을 수 없습니다")
    return FileResponse(
        str(path),
        media_type=guess_video_mime(path),
        filename=f"{code}_part{part}{path.suffix.lower()}",
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/{code}/hls/{part}/index.m3u8")
def stream_hls_playlist(code: str, part: int):
    playlist = _playback.resolve_hls_playlist(code, part)
    if not playlist:
        prep = _playback.prepare_stream(code, part)
        if prep and prep.get("status") == "building":
            raise HTTPException(503, "브라우저 재생용 HLS 변환 중입니다. 잠시 후 다시 시도하세요.")
        if prep and prep.get("status") == "failed":
            raise HTTPException(500, prep.get("error") or "프록시 변환에 실패했습니다")
        raise HTTPException(404, "HLS 재생 목록을 찾을 수 없습니다")
    return FileResponse(
        str(playlist),
        media_type="application/vnd.apple.mpegurl",
        filename="index.m3u8",
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/{code}/hls/{part}/{segment_name}")
def stream_hls_segment(code: str, part: int, segment_name: str):
    segment = _playback.resolve_hls_segment(code, part, segment_name)
    if not segment:
        prep = _playback.prepare_stream(code, part)
        if prep and prep.get("status") == "building":
            raise HTTPException(503, "브라우저 재생용 HLS 변환 중입니다. 잠시 후 다시 시도하세요.")
        raise HTTPException(404, "HLS 세그먼트를 찾을 수 없습니다")
    return FileResponse(
        str(segment),
        media_type="video/mp2t",
        filename=segment.name,
        content_disposition_type="inline",
        headers={"Accept-Ranges": "bytes"},
    )





@router.get("/{code}/subtitles/{part}/{track}", response_model=SubtitleCueList)

def get_subtitle_cues(code: str, part: int, track: int):

    path = _playback.resolve_subtitle_path(code, part, track)

    if path is None:

        raise HTTPException(404, "자막을 찾을 수 없습니다")

    return SubtitleCueList(cues=_playback.read_subtitle_cues(path))


