"""라이브러리 폴더 바인딩(DB folder_path + canonical media.parts)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class _Toast(Protocol):
    def __call__(self, message: str, level: str) -> None: ...


@dataclass
class FolderBindHooks:
    toast: _Toast
    refresh_product: Callable[[str], None]
    summaries_reloaded: Callable[[], None]
    schedule_auto_snapshots: Callable[[str, str], None]


class LibraryFolderBind:
    @staticmethod
    def bind_folder(
        product_code: str,
        folder_path: str,
        *,
        force: bool,
        hooks: FolderBindHooks,
    ) -> bool:
        try:
            from javstory.harvest.database import JAVMetadata, get_db_session
            from javstory.utils.product_code import extract_product_code_from_path

            from gui.library_data import (
                _first_video_in_dir,
                path_contains_mopa_marker,
                path_contains_self_subtitle_marker,
            )

            pc = (product_code or "").strip().upper()
            target_path = Path(folder_path)
            if not target_path.is_dir():
                hooks.toast(f"폴더가 없거나 디렉터리가 아닙니다: {folder_path}", "error")
                return False

            detected_pc = extract_product_code_from_path(target_path)
            if not detected_pc:
                v = _first_video_in_dir(target_path)
                if v:
                    detected_pc = extract_product_code_from_path(v)

            mismatch = not detected_pc or detected_pc.upper() != pc
            if mismatch and not force:
                hooks.toast(
                    f"선택한 폴더({target_path.name})가 품번 {pc}와 일치하지 않습니다. "
                    "강제 연결을 사용하세요.",
                    "error",
                )
                return False

            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if not row:
                    hooks.toast(f"DB에 품번 {pc} 메타데이터가 없습니다.", "error")
                    return False

                abs_path = str(target_path.resolve())
                from javstory.harvest.product_repository import set_folder_path

                set_folder_path(session, pc, abs_path)
                try:
                    v = _first_video_in_dir(target_path)
                    row.is_hardcoded = bool(
                        path_contains_self_subtitle_marker(v, abs_path, pc)
                    )
                    row.is_mopa = bool(path_contains_mopa_marker(v, abs_path))
                except Exception:
                    pass
                from javstory.harvest.product_repository import sync_product_from_metadata_row

                sync_product_from_metadata_row(session, row)
                session.commit()

                try:
                    from javstory.harvest.product_repository import (
                        resolve_video_paths_for_playback,
                        sync_media_bundle,
                    )

                    vps = resolve_video_paths_for_playback(pc, abs_path)
                    if vps:
                        sync_media_bundle(pc, abs_path, vps)
                except Exception:
                    pass

                if mismatch and force:
                    hooks.toast(f"강제 연결 저장: {abs_path}", "warning")
                else:
                    hooks.toast(f"폴더 경로가 저장되었습니다: {abs_path}", "success")
                hooks.refresh_product(pc)
                hooks.summaries_reloaded()
                hooks.schedule_auto_snapshots(pc, abs_path)
                return True
            finally:
                session.close()
        except Exception as e:
            hooks.toast(f"폴더 연결 실패: {e}", "error")
            return False

    @staticmethod
    def clear_folder(product_code: str, hooks: FolderBindHooks) -> bool:
        try:
            from javstory.harvest.database import JAVMetadata, get_db_session

            pc = (product_code or "").strip().upper()
            if not pc:
                return False
            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if not row:
                    hooks.toast(f"DB에 품번 {pc}가 없습니다.", "warning")
                    return False
                from javstory.harvest.product_repository import (
                    clear_video_files_for_product,
                    set_folder_path,
                    sync_product_from_metadata_row,
                )

                set_folder_path(session, pc, None)
                sync_product_from_metadata_row(session, row)
                clear_video_files_for_product(session, pc)
                session.commit()
                hooks.toast("폴더 연결이 해제되었습니다.", "success")
                hooks.refresh_product(pc)
                hooks.summaries_reloaded()
                return True
            finally:
                session.close()
        except Exception as e:
            hooks.toast(f"연결 해제 실패: {e}", "error")
            return False
