"""하베스트 워커: Stage 1(수집) 및 Stage 2(정제) 작업을 비동기로 처리."""
import sys
from pathlib import Path
from PySide6.QtCore import QThread, Signal

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.harvest.coordinator import run_crawler_for_video_path
from javstory.utils.product_code import extract_product_code_from_path
from javstory.harvest.database import get_db_session_ctx
import asyncio
from javstory.config.app_config import MEDIA_ROOT

class HarvestWorker(QThread):
    """
    크롤링 엔트리 리스트를 순차 처리한다.
    각 엔트리: `(target, is_path, product_code)` — `is_path`가 True면 `target`은 영상 파일 경로,
    False면 품번 문자열(크롤만). `product_code`가 있으면 폴더명 기준 품번으로 크롤에 사용한다.
    """

    progress = Signal(str, str, int)  # sku, message, percentage
    task_finished = Signal(str, bool, str)  # sku, success, final_message

    def __init__(
        self,
        entries: list[tuple],
        grok_enabled: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.entries = entries
        self.grok_enabled = grok_enabled
        self._is_running = True

    @classmethod
    def from_legacy(
        cls,
        items: list[str],
        is_path: bool = True,
        product_codes: list[str | None] | None = None,
        parent=None,
    ):
        pcs = product_codes if product_codes is not None else [None] * len(items)
        ent: list[tuple[str, bool, str | None]] = [
            (items[i], is_path, pcs[i] if i < len(pcs) else None) for i in range(len(items))
        ]
        return cls(ent, parent=parent)

    def stop(self):
        self._is_running = False

    def run(self):
        """워커 메인 루프: 단일 비동기 루프를 사용하여 안정성 확보"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from javstory.harvest.translator import MetadataTranslator
            # [최적화] 워커 실행 동안 단일 번역기 인스턴스 유지 (httpx 클라이언트 재사용)
            translator = MetadataTranslator()

            for e in self.entries:
                if not self._is_running:
                    break

                # entry: (target, is_path, product_code_override, force_rebuild?)
                try:
                    target = e[0]
                    is_path_flag = bool(e[1])
                    pc_override = e[2] if len(e) >= 3 else None
                    force_rebuild = bool(e[3]) if len(e) >= 4 else False
                except Exception:
                    target = e
                    is_path_flag = False
                    pc_override = None
                    force_rebuild = False

                pc_kw = (pc_override or "").strip() or None
                if is_path_flag:
                    sku = pc_kw or extract_product_code_from_path(target) or Path(target).stem
                else:
                    sku = pc_kw or str(target).strip().upper()

                def log(msg):
                    from datetime import datetime
                    now = datetime.now().strftime("%H:%M:%S")
                    print(f"[{now}] {msg}", flush=True)

                log(f"[HarvestWorker] [{sku}] 수집 공정 진입 (Target: {target})")

                loop.run_until_complete(
                    self._process_item(
                        sku,
                        str(target),
                        log,
                        product_code=pc_kw,
                        force_rebuild=force_rebuild,
                        translator_instance=translator
                    )
                )
                self.msleep(300) # UI 응답성 보호
        finally:
            # 번역기 리소스 해제
            try:
                if 'translator' in locals():
                    loop.run_until_complete(translator.close())
            except Exception:
                pass

            # [개선] 루프 종료 전 대기 중인 모든 태스크를 정리하여 'Event loop is closed' 방지
            try:
                # 1. 현재 루프에서 실행 중인 모든 태스크 확인
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    # 취소된 태스크들이 정리될 수 있도록 루프를 잠시 실행
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # 2. 비동기 제너레이터 등 클린업
                loop.run_until_complete(loop.shutdown_asyncgens())
                # 3. asyncio.to_thread / 기본 ThreadPoolExecutor 종료 대기 (연결·httpx 정리와 loop.close 경쟁 방지)
                try:
                    loop.run_until_complete(loop.shutdown_default_executor())
                except Exception:
                    pass
            except Exception as e:
                print(f"[HarvestWorker] 클린업 중 예외 발생: {e}")
            finally:
                loop.close()
                now_end = __import__('datetime').datetime.now().strftime("%H:%M:%S")
                first_t = self.entries[0][0] if self.entries else "Unknown"
                print(f"[{now_end}] [HarvestWorker] '{first_t}' 스레드 루프 종료 및 리소스 해제 완료.", flush=True)

    async def _process_item(
        self,
        sku: str,
        item: str,
        log,
        *,
        product_code: str | None = None,
        force_rebuild: bool = False,
        translator_instance: any = None,
    ):
        """개별 아이템에 대한 전체 수집/번역/저장 프로세스 (Async)"""
        log(f"[HarvestWorker] '{sku}' 통합 공정 시작...")
        self.progress.emit(sku, "준비 중...", 5)
        
        # 1. 통합 코디네이터 호출 (Crawling + Mapping + AI Translation + DB Save)
        if self.grok_enabled:
            self.progress.emit(sku, "크롤링·한국어 번역·DB 저장·스토리 맥락(Grok JSON, 캐시)…", 20)
        else:
            self.progress.emit(sku, "크롤링·한국어 번역·DB 저장…", 20)
        
        try:
            crawler_res = await run_crawler_for_video_path(
                item, 
                product_code=product_code,
                enable_story_context=False, # 메타데이터 단계에서는 비활성
                force_rebuild_story_context=bool(force_rebuild),
                skip_translation=True,      # 번역은 백그라운드 큐에서 처리
                skip_media=True,            # 미디어는 백그라운드 큐에서 처리
                translator_instance=translator_instance,
            )
            
            if crawler_res.get("error"):
                if crawler_res.get("skeleton_saved"):
                    log(f"⚠️ [HarvestWorker] {sku} 크롤링은 실패했으나 뼈대 정보와 로컬 이미지가 저장되었습니다. 후처리를 계속합니다.")
                else:
                    log(f"⚠️ [HarvestWorker] {sku} 수집 실패: {crawler_res['error']}")
                    self.task_finished.emit(sku, False, f"수집 실패: {crawler_res['error']}")
                    return
            
            # 2. 자산 처리 (Assets - 이미지 다운로드 및 가공)
            self.progress.emit(sku, "표지 이미지 및 썸네일 생성 중...", 80)
            
            # DB에서 행 정보 다시 읽기 (이미지 경로 업데이트용)
            try:
                from javstory.harvest.database import JAVMetadata
                with get_db_session_ctx() as session:
                    row = session.query(JAVMetadata).filter_by(product_code=sku).first()
                    if not row:
                        pass
                    else:
                        # cover가 이미 있으면 여기서 굳이 재처리하지 않는다(중복 I/O 방지)
                        has_local = False
                        try:
                            has_local = bool(getattr(row, "cover_image_local_path", None))
                        except Exception:
                            has_local = False

                        url = (getattr(row, "cover_image_url", None) or "").strip()
                        is_http = url.startswith("http://") or url.startswith("https://")

                        if (not has_local) and is_http:
                            log(f"[HarvestWorker] [{sku}] 이미지 자산 처리 시작 (URL: {url})")
                            from javstory.utils.image_handler import ImageHandler

                            handler = ImageHandler()
                            img_res = handler.process_jav_assets(sku, url)

                            if img_res:
                                row.cover_image_local_path = img_res.get("poster_local")
                                row.thumb_image_local_path = img_res.get("thumb_local")
                                session.commit()
                                log(f"[HarvestWorker] [{sku}] 이미지 자산 처리 완료.")
                            else:
                                log(f"⚠️ [HarvestWorker] [{sku}] 이미지 수집 실패 (데이터는 보존됨).")
            except Exception as img_e:
                log(f"⚠️ [HarvestWorker] [{sku}] 이미지 처리 오류: {str(img_e)}")

            # 3. 스냅샷(영상 전체) 추출 및 기타 공정은 coordinator 내부에서 수행됨
            self.progress.emit(sku, "추출 및 최종 정리 중...", 95)

            self.progress.emit(sku, "수집 완료 (후처리 큐 등록됨)", 100)
            
            # [핵심] 수집 완료 후 각 대기 큐로 작업 분배 (대시보드 노출)
            try:
                from gui.models.translation_queue_model import TranslationQueueController
                from gui.models.preview_queue_model import PreviewQueueController
                from javstory.library.stills.snapshot_queue import snapshot_queue_manager
                from javstory.library.stills.digest_queue import digest_queue_manager

                # 1. 번역 큐
                # [수정] 크롤링에 실패한 '뼈대' 작품은 번역할 내용이 없으므로 큐에서 제외 (프리뷰 지연 방지)
                is_skeleton = bool(crawler_res.get("skeleton_saved"))
                if not is_skeleton:
                    tq = TranslationQueueController.instance()
                    if tq: tq.enqueue(sku, item)
                    self.msleep(50)
                else:
                    log(f"[HarvestWorker] {sku}는 뼈대 정보이므로 번역 큐 등록을 스킵합니다.")

                # 2) 미디어 관련 큐에는 "원본 영상 파일 경로"가 필요함.
                # recrawlProducts는 item에 품번 문자열만 들어오므로, 바인딩된 folder_path에서 원본 영상을 추정해 넣는다.
                media_video_path: Path | None = None
                try:
                    direct = Path(item)
                    if direct.is_file():
                        media_video_path = direct
                    else:
                        from gui.library_data import guess_video_path_for_product
                        from javstory.harvest.database import JAVMetadata
                        folder_path = None
                        with get_db_session_ctx() as session:
                            row = session.query(JAVMetadata).filter_by(product_code=sku).first()
                            if row:
                                folder_path = getattr(row, "folder_path", None)
                        guessed = guess_video_path_for_product(sku, folder_path or None)
                        if guessed and Path(guessed).is_file():
                            media_video_path = Path(guessed)
                except Exception:
                    media_video_path = None
                
                # 2. 프리뷰 큐
                pq = PreviewQueueController.instance()
                if pq and media_video_path:
                    pq.enqueue(sku, str(media_video_path))
                self.msleep(50)
                
                # 3. 다이제스트 큐 (매니저 직접 호출)
                from javstory.config.app_config import E_MEDIA_ROOT, MEDIA_ROOT
                base_root = Path(E_MEDIA_ROOT)
                if not base_root.exists(): base_root = Path(MEDIA_ROOT)
                
                digest_dir = base_root / sku / "Digest"
                digest_dir.mkdir(parents=True, exist_ok=True)
                digest_path = digest_dir / "digest.mp4"
                if media_video_path:
                    digest_queue_manager.push_job(media_video_path, digest_path, product_code=sku)
                self.msleep(50)
                
                # 4. 스냅샷 큐 (자동 추출 폴더 계산)
                out_dir = base_root / sku / "Snapshots"
                out_dir.mkdir(parents=True, exist_ok=True)
                if media_video_path:
                    snapshot_queue_manager.push_job(media_video_path, out_dir, product_code=sku)
                self.msleep(50)
                
            except Exception as ph_e:
                log(f"⚠️ [HarvestWorker] 대시보드 큐 등록 실패: {ph_e}")

            self.task_finished.emit(sku, True, "기본 수집 성공 (대시보드 큐 등록됨)")

        except Exception as e:
            log(f"❌ [HarvestWorker] 치명적 에러: {e}")
            self.task_finished.emit(sku, False, str(e))

