"""백그라운드 번역 워커."""

import asyncio
from PySide6.QtCore import QThread, Signal
from javstory.harvest.coordinator import run_crawler_for_video_path

class TranslationWorker(QThread):
    finished = Signal(bool, str) # success, message

    def __init__(self, sku: str, video_path: str, parent=None):
        super().__init__(parent)
        self.sku = sku
        self.video_path = video_path

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
                    force_rebuild_story_context=False
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
        
        # 루프 종료 후 시그널 전송
        self.finished.emit(success, message)
