"""다이제스트(타임랩스) 추출 모듈."""

from __future__ import annotations

import logging
import subprocess
import os
import re
from pathlib import Path
from typing import Callable, Optional
from javstory.library.stills.extract import probe_video_duration_seconds

logger = logging.getLogger(__name__)

def create_digest_video(
    video_path: Path | str,
    output_path: Path | str,
    *,
    speed: int = 60,
    width: int = 860,
    progress_callback: Optional[Callable[[int], None]] = None
) -> Path | None:
    """
    영상 전체의 타임랩스(고속 재생 다이제스트) MP4를 생성합니다.
    speed: 배속 (기본 60). 2시간 영상 -> 2분 다이제스트.
    width: 움짤 용도이므로 가로 해상도를 480px로 최소화.
    """
    vp = Path(video_path)
    op = Path(output_path)
    
    if not vp.is_file():
        logger.warning(f"원본 영상 파일이 없습니다: {vp}")
        return None
        
    op.parent.mkdir(parents=True, exist_ok=True)
    
    dur = probe_video_duration_seconds(vp)
    if dur > 0 and dur < 60:
        logger.info(f"영상이 너무 짧아 다이제스트를 생략합니다: {dur}초")
        return None

    logger.info(f"🎥 다이제스트 타임랩스 렌더링 시작({speed}배속): {vp.name}")
    
    # 추출 필터: 속도에 맞춰 fps 조정하고 30프레임으로 압축
    extract_fps = 30.0 / float(speed)
    total_expected_frames = int(dur * extract_fps)
    
    # 1. RTX 3080Ti 타겟: 최강 속도의 CUDA 하드웨어 렌더링 세팅
    cmd_cuda = [
        "ffmpeg", "-y",
        "-hwaccel", "auto", # 디코딩 가속 활성화
        "-skip_frame", "nokey", # [초고속 핵심] 키프레임 외의 모든 불필요한 프레임 디코딩 완전 생략
        "-i", str(vp),
        "-vf", f"fps={extract_fps},setpts=N/30/TB,scale={width}:-2",
        "-r", "30",
        "-c:v", "h264_nvenc", # NVIDIA 하드웨어 인코더 칩 사용
        "-preset", "fast",
        "-cq", "30",  # 하드웨어 변압(VBR) 기준: 용량 최적화 (20~30)
        "-an",
        str(op)
    ]
    
    # 2. 예비용: CUDA 칩이 꽉 찼거나(NVENC Limit 초과) 에러 발생 시 원래 쓰던 CPU 렌더링으로 백업
    cmd_cpu = [
        "ffmpeg", "-y",
        "-skip_frame", "nokey", # [초고속 핵심] CPU 방식에서도 키프레임만 스킵하여 엄청난 속도 향상
        "-i", str(vp),
        "-vf", f"fps={extract_fps},setpts=N/30/TB,scale={width}:-2",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "30",
        "-an",
        str(op)
    ]
    
    def run_cmd(cmd_list):
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # -progress 파싱용
        process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            encoding='utf-8',
            errors='ignore'
        )
        
        frame_pattern = re.compile(r'frame=\s*(\d+)')
        last_percent = -1
        
        for line in process.stderr:
            if progress_callback and total_expected_frames > 0:
                match = frame_pattern.search(line)
                if match:
                    current_frame = int(match.group(1))
                    percent = int(min((current_frame / total_expected_frames) * 100, 99))
                    if percent != last_percent:
                        progress_callback(percent)
                        last_percent = percent
                        
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd_list, stderr="FFmpeg execution failed")

    try:
        # CUDA를 1순위로 공격적으로 실행
        run_cmd(cmd_cuda)
        if op.is_file() and op.stat().st_size > 100:
            if progress_callback: progress_callback(100)
            logger.info(f"✅ 다이제스트 완료 (최고속 ⚡CUDA 가속): {op.name} ({op.stat().st_size / 1024 / 1024:.2f} MB)")
            return op
    except subprocess.CalledProcessError as e:
        logger.warning(f"⚠️ CUDA 인코딩 일시 불가 (NVENC 가득 참 등), CPU 스페어 인코더로 전환하여 작업합니다: {vp.name}")
        try:
            # 실패하면 즉시 CPU 코어로 전환하여 구워버림 (안정성 보장)
            run_cmd(cmd_cpu)
            if op.is_file() and op.stat().st_size > 100:
                if progress_callback: progress_callback(100)
                logger.info(f"✅ 다이제스트 완료 (안정형 🖥️CPU 폴백): {op.name}")
                return op
        except subprocess.CalledProcessError as e2:
            logger.error(f"❌ FFmpeg 다이제스트 생성 에러 (양쪽 모두 실패):\n{str(e2)}")
    except FileNotFoundError:
        logger.error("시스템에 ffmpeg이 설치되어 있지 않거나 환경변수 PATH가 없습니다.")
        
    return None
