"""백그라운드 번역 워커."""

import asyncio
from PySide6.QtCore import QThread, Signal
from javstory.harvest.coordinator import run_crawler_for_video_path

class TranslationWorker(QThread):
    """QThread.finished(무인자)와 이름이 겹치면 스레드 종료·deleteLater 연결이 꼬일 수 있어 별도 시그널 사용."""
    translationFinished = Signal(bool, str)  # success, message

    def __init__(self, sku: str, video_path: str, force_rebuild: bool = False, parent=None):
        super().__init__(parent)
        self.sku = sku
        self.video_path = video_path
        self.force_rebuild = bool(force_rebuild)
        # QThread.finished 가 translationFinished 슬롯보다 먼저 오는 경우 좀비 복구 오동작 방지용
        self._translation_notified: bool = False

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = False
        message = ""
        try:
            res = loop.run_until_complete(
                run_crawler_for_video_path(
                    self.video_path,
                    product_code=self.sku,
                    skip_translation=False,
                    skip_media=True,
                    force_rebuild_story_context=bool(self.force_rebuild)
                )
            )
            if isinstance(res, dict) and res.get("error"):
                success = False
                message = str(res.get("error"))
            else:
                success = True
                if isinstance(res, dict) and res.get("translation_skipped") is True and res.get("did_translate") is False:
                    reason = str(res.get("translation_skip_reason") or "")
                    if reason == "already_ok_in_db":
                        message = "번역 스킵(DB에 한국어 저장됨)"
                    elif reason == "skip_translation_param":
                        message = "번역 스킵(설정/단계)"
                    else:
                        message = "번역 스킵"
                else:
                    message = "번역 완료"
        except Exception as e:
            success = False
            message = str(e)
        finally:
            loop.close()

        # emit 직전에 설정 → finished 슬롯이 먼저 실행돼도 메인 스레드에서 True로 관측됨
        self._translation_notified = True
        self.translationFinished.emit(success, message)
