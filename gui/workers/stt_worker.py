"""STT 워커: stable-ts(Whisper) 자막 생성을 비동기로 처리."""
import os
import sys
import traceback
from pathlib import Path
from PySide6.QtCore import QThread, Signal

# 프로젝트 루트 경로 추가
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.transcription.engine import process_video_to_segments, clear_vram, STT_PRESET_DEFAULT, STTCancelled

class STTWorker(QThread):
    """
    영상에서 오디오를 추출하고 stable-ts로 전사·후처리 후 자막을 저장하는 워커.
    """
    progress = Signal(str, int)       # message, percent
    finished = Signal(str, bool, str)  # srt_path, success, message

    def __init__(self, video_path: str, output_dir: str = None, stt_preset: str = None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self._is_running = True
        # 하위 호환: 프리셋 인자는 엔진에서 무시됨(stable-ts 고정)
        self.stt_preset = stt_preset if stt_preset else STT_PRESET_DEFAULT

        # 기본 출력 디렉토리 설정 (임시 작업용)
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = os.path.join(os.path.dirname(video_path), "stt_work")

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            last_percent = 0
            self.progress.emit("자막 생성 공정 시동 중...", 5)
            last_percent = 5

            # 파일/폴더명에 "자체자막" 표기가 있으면 STT를 스킵하고 완료 처리한다.
            p = Path(self.video_path)
            if any("자체자막" in part for part in p.parts):
                base_name = os.path.splitext(self.video_path)[0]
                ko_srt = base_name + ".ko.srt"
                ja_srt = base_name + ".ja.srt"
                plain_srt = base_name + ".srt"
                
                final_srt = ""
                if os.path.exists(ko_srt): final_srt = ko_srt
                elif os.path.exists(ja_srt): final_srt = ja_srt
                elif os.path.exists(plain_srt): final_srt = plain_srt

                self.progress.emit("[완료] 자체자막 표기 감지 → STT 스킵", 100)
                self.finished.emit(final_srt, True, "자체자막 표기: STT 스킵 완료")
                return
            
            # 기존 결과물이 이미 있는 경우 스킵 (STT 중복 방지)
            base_name = os.path.splitext(self.video_path)[0]
            ko_srt = base_name + ".ko.srt"
            plain_srt = base_name + ".srt"
            
            if os.path.exists(ko_srt):
                self.progress.emit("[완료] 기존 .ko.srt 감지 → STT 스킵", 100)
                self.finished.emit(ko_srt, True, "기존 .ko.srt 존재: STT 스킵")
                return
            if os.path.exists(plain_srt):
                self.progress.emit("[완료] 기존 .srt(외부) 감지 → STT 스킵", 100)
                self.finished.emit(plain_srt, True, "기존 .srt 존재: STT 스킵")
                return
            
            # Transcription.engine — stable-ts 단일 경로
            # - logger_func을 통해 내부의 모든 print 로그를 GUI로 전달
            # - progress_callback(STTProgressEvent)로 구조화된 진행률 이벤트를 직접 수신
            def log_bridge(msg: str):
                nonlocal last_percent
                # 하위 호환: 혹시라도 [P:xx] 로그가 섞여오면 percent만 추출하되,
                # 태그가 없는 로그 때문에 진행률이 0으로 떨어지지 않도록 마지막 값을 유지한다.
                try:
                    import re
                    m = re.search(r'\[P:(\d+)\]', msg)
                    if m:
                        p = int(m.group(1))
                        last_percent = max(last_percent, max(0, min(100, p)))
                        msg = re.sub(r'\[P:\d+\]\s*', '', msg)
                except Exception:
                    pass
                self.progress.emit(msg, last_percent)

            def progress_event_bridge(ev):
                nonlocal last_percent
                try:
                    p = int(getattr(ev, "percent", last_percent))
                except Exception:
                    p = last_percent
                p = max(0, min(100, p))
                last_percent = max(last_percent, p)
                stage = (getattr(ev, "stage", "") or "").strip()
                msg = getattr(ev, "message", "") or ""

                # UI 가독성: stage를 한국어 라벨로 표시 (시그널 형태는 유지)
                stage_label_map = {
                    "init": "초기화",
                    "extract": "오디오 추출",
                    "uvr": "보컬 분리",
                    "snr": "SNR",
                    "preprocess": "전처리",
                    "whisper": "전사(stable-ts)",
                    "post": "후처리",
                    "llm": "LLM 교정",
                    "write": "저장",
                    "done": "완료",
                }
                if stage:
                    label = stage_label_map.get(stage, stage)
                    if msg:
                        msg = f"[{label}] {msg}"
                    else:
                        msg = f"[{label}]"
                self.progress.emit(msg, last_percent)

            segments = process_video_to_segments(
                video_path=self.video_path,
                output_dir=self.output_dir,
                skip_vocal_sep=False,
                with_llm=False,
                logger_func=log_bridge,
                progress_callback=progress_event_bridge,
                stt_preset=self.stt_preset,
                should_cancel=lambda: not self._is_running,
            )

            # 생성/기존 자막 경로 확인
            base_name = os.path.splitext(self.video_path)[0]
            ja_srt = base_name + ".ja.srt"
            plain_srt = base_name + ".srt"

            if os.path.exists(ja_srt):
                self.finished.emit(ja_srt, True, "자막 생성 완료 (stable-ts)")
            elif os.path.exists(plain_srt):
                self.finished.emit(plain_srt, True, "기존 .srt 사용 (STT 스킵)")
            else:
                self.finished.emit("", False, "자막 파일이 생성되지 않았습니다.")

        except STTCancelled:
            self.finished.emit("", False, "사용자에 의해 자막 생성이 중단되었습니다.")
        except Exception as e:
            err_msg = f"STT 공정 에러: {str(e)}"
            print(f"[STTWorker] {err_msg}")
            traceback.print_exc()
            self.finished.emit("", False, err_msg)
        finally:
            clear_vram()
            # 임시 작업 디렉토리 정리:
            # 기본값(영상 옆 stt_work)만 자동 삭제한다. (사용자 지정 output_dir은 보존)
            try:
                out_dir = Path(self.output_dir).resolve()
                vid_dir = Path(self.video_path).resolve().parent
                if out_dir.name == "stt_work" and out_dir.parent == vid_dir and out_dir.exists():
                    import shutil
                    shutil.rmtree(out_dir, ignore_errors=True)
            except Exception:
                pass
