from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from gui.watch_resume import (
    last_position_ms_for_video,
    merge_last_positions_json,
    normalize_watch_video_key,
)
from javstory.harvest.database import get_db_session_ctx, UserPreference, WatchHistory

class PlayerModel(QObject):
    """
    QML 플레이어의 상태와 시청 데이터를 관리하는 백엔드 모델.
    재생 진척도, 시청 시간, 스킵 감지, 배우/장르 선호도 가중치를 실시간으로 처리합니다.
    """

    currentProductChanged = Signal()
    playbackStateChanged = Signal()
    ratingChanged = Signal(int)         # 별점 변경 알림 (QML 초기값 표시용)
    likeStateChanged = Signal(bool, bool)  # (liked, disliked) 변경 알림
    closePlayerRequested = Signal()     # Python 이벤트 필터 → QML 플레이어 닫기

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_product = ""
        self._is_playing = False
        self._current_rating = 0
        self._is_liked = False
        self._is_disliked = False
        self._player_open = False

    @Slot(bool)
    def setPlayerOpen(self, is_open: bool):
        """QML playerLoader의 active 상태를 동기화한다."""
        self._player_open = bool(is_open)

    @Slot()
    def closePlayer(self):
        """Python 이벤트 필터에서 ESC/Backspace 감지 시 호출 — closePlayerRequested 시그널 발생."""
        if self._player_open:
            self._player_open = False  # 중복 호출 방지
            self.closePlayerRequested.emit()

    # ── Properties ──────────────────────────────────────────

    @Property(str, notify=currentProductChanged)
    def currentProduct(self):
        return self._current_product

    @Property(int, notify=ratingChanged)
    def currentRating(self):
        return self._current_rating

    @Property(bool, notify=likeStateChanged)
    def isLiked(self):
        return self._is_liked

    @Property(bool, notify=likeStateChanged)
    def isDisliked(self):
        return self._is_disliked

    # ── 재생 세션 시작 ───────────────────────────────────────

    @Slot(str, int)
    def startWatch(self, product_code: str, total_sec: int):
        """재생 시작 시 호출하여 세션을 초기화합니다."""
        self._current_product = product_code
        self.currentProductChanged.emit()

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    total_duration=total_sec,
                    session_count=1,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)
            else:
                history.session_count = (history.session_count or 0) + 1
                if total_sec > 0:
                    history.total_duration = total_sec
                history.updated_at = datetime.datetime.now()
            session.commit()

            # 현재 별점 & 좋아요 상태 로드
            self._current_rating = history.rating or 0
            self._is_liked = bool(history.liked)
            self._is_disliked = bool(history.disliked)

        self.ratingChanged.emit(self._current_rating)
        self.likeStateChanged.emit(self._is_liked, self._is_disliked)

    # ── 진척도 업데이트 ─────────────────────────────────────

    @Slot(str, int, int, str)
    def updateProgress(self, product_code: str, position_ms: int, duration_sec: int, video_path: str):
        """
        재생 중 주기적으로 호출되어 현재 위치를 저장합니다.
        video_path가 비어 있으면 JSON 파트 맵은 건너뜁니다(레거시).
        90% 이상 시청 시 완료 처리 + 취향 점수 1 증가.
        """
        if not product_code:
            return

        vkey = normalize_watch_video_key(video_path or "")

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.last_position = position_ms
                if vkey:
                    history.last_positions_json = merge_last_positions_json(
                        getattr(history, "last_positions_json", None),
                        vkey,
                        position_ms,
                    )
                if duration_sec > 0:
                    progress = position_ms / (duration_sec * 1000)
                    if progress > 0.9 and not history.is_completed:
                        history.is_completed = True
                        # 완독 시 취향 점수 자동 반영
                        try:
                            from javstory.analytics.preference_engine import score_preferences
                            score_preferences(product_code, delta=2)
                        except Exception:
                            pass
                history.updated_at = datetime.datetime.now()
                session.commit()

    # ── 누적 시청 시간 업데이트 (30초마다) ─────────────────

    @Slot(str, int)
    def updateWatchDuration(self, product_code: str, elapsed_sec: int):
        """
        누적 시청 시간을 증가시킵니다. QML에서 30초마다 호출.
        """
        if not product_code or elapsed_sec <= 0:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.watch_duration = (history.watch_duration or 0) + elapsed_sec
                history.updated_at = datetime.datetime.now()
                session.commit()

    # ── 스킵 감지 ───────────────────────────────────────────

    @Slot(str, int, int)
    def recordSkip(self, product_code: str, from_ms: int, to_ms: int):
        """
        앞으로 5초 이상 건너뛸 때 스킵으로 기록합니다.
        QML의 onPositionChanged에서 이전 위치와 비교하여 호출.
        """
        if not product_code:
            return
        jump_sec = (to_ms - from_ms) / 1000
        if jump_sec < 5:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.skip_count = (history.skip_count or 0) + 1
                history.updated_at = datetime.datetime.now()
                session.commit()

    # ── 명시적 피드백: 좋아요 ───────────────────────────────

    @Slot(str)
    def setLike(self, product_code: str):
        """좋아요 토글 + 취향 점수 +3."""
        if not product_code:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)

            new_liked = not bool(history.liked)
            history.liked = new_liked
            history.disliked = False  # 좋아요 누르면 싫어요 해제
            history.updated_at = datetime.datetime.now()
            session.commit()

            self._is_liked = new_liked
            self._is_disliked = False

        self.likeStateChanged.emit(self._is_liked, self._is_disliked)

        delta = 3 if self._is_liked else -3
        try:
            from javstory.analytics.preference_engine import score_preferences
            score_preferences(product_code, delta=delta)
        except Exception:
            pass

    # ── 명시적 피드백: 싫어요 ───────────────────────────────

    @Slot(str)
    def setDislike(self, product_code: str):
        """싫어요 토글 + 취향 점수 -2."""
        if not product_code:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)

            new_disliked = not bool(history.disliked)
            history.disliked = new_disliked
            history.liked = False  # 싫어요 누르면 좋아요 해제
            history.updated_at = datetime.datetime.now()
            session.commit()

            self._is_disliked = new_disliked
            self._is_liked = False

        self.likeStateChanged.emit(self._is_liked, self._is_disliked)

        delta = -2 if self._is_disliked else 2
        try:
            from javstory.analytics.preference_engine import score_preferences
            score_preferences(product_code, delta=delta)
        except Exception:
            pass

    # ── 별점 ────────────────────────────────────────────────

    @Slot(str, int)
    def setRating(self, product_code: str, rating: int):
        """사용자가 부여한 별점(0~5)을 저장하고 취향 점수를 업데이트합니다."""
        if not product_code:
            return
        rating = max(0, min(5, rating))

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)

            old_rating = history.rating or 0
            history.rating = rating
            history.updated_at = datetime.datetime.now()
            session.commit()

        self._current_rating = rating
        self.ratingChanged.emit(rating)

        # 별점 변화에 따른 취향 점수 delta 계산
        delta = 0
        if rating >= 4:
            delta = 3
        elif rating == 3:
            delta = 1
        elif rating <= 1 and old_rating > rating:
            delta = -1

        if delta != 0:
            try:
                from javstory.analytics.preference_engine import score_preferences
                score_preferences(product_code, delta=delta)
            except Exception:
                pass

    # ── 기존 호환 API ────────────────────────────────────────

    @Slot(str, str)
    def trackPreference(self, category_type: str, value: str):
        """
        배우(actor), 장르(genre), 제작사(maker) 선호도 점수를 직접 증가시킵니다.
        레거시 호환 및 QML 직접 호출용.
        """
        if not category_type or not value:
            return

        with get_db_session_ctx() as session:
            pref = session.query(UserPreference).filter_by(
                category_type=category_type,
                category_value=value,
                time_slot="all",
            ).first()

            if not pref:
                pref = UserPreference(
                    category_type=category_type,
                    category_value=value,
                    score=1,
                    recent_score=1,
                    time_slot="all",
                    last_watched_at=datetime.datetime.now(),
                )
                session.add(pref)
            else:
                pref.score += 1
                pref.recent_score += 1
                pref.last_watched_at = datetime.datetime.now()

            session.commit()

    @Slot(str, result=int)
    def getRatingForProduct(self, product_code: str) -> int:
        """현재 저장된 별점을 반환합니다 (QML 초기값 표시용)."""
        if not product_code:
            return 0
        with get_db_session_ctx() as session:
            h = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            return h.rating if h else 0

    # ── 마지막 재생 위치 ─────────────────────────────────────

    @Slot(str, int)
    def updateTotalDuration(self, product_code: str, total_sec: int):
        """영상 duration 확정 시 총 길이만 업데이트합니다 (session_count 변경 없음)."""
        if not product_code or total_sec <= 0:
            return
        try:
            with get_db_session_ctx() as session:
                history = session.query(WatchHistory).filter_by(
                    product_code=product_code
                ).first()
                if history:
                    history.total_duration = total_sec
                    history.updated_at = datetime.datetime.now()
                    session.commit()
        except Exception:
            pass

    @Slot(str, str, result=int)
    def getLastPosition(self, product_code: str, video_path: str) -> int:
        """마지막 시청 위치(ms). video_path가 비면 레거시 last_position만 사용."""
        if not product_code:
            return 0
        try:
            with get_db_session_ctx() as session:
                h = session.query(WatchHistory).filter_by(
                    product_code=product_code
                ).first()
                if not h:
                    return 0
                return last_position_ms_for_video(
                    legacy_last_position=int(h.last_position or 0),
                    last_positions_json=getattr(h, "last_positions_json", None),
                    video_path=video_path or "",
                )
        except Exception:
            return 0

    # ── 자막 파일 탐색 ───────────────────────────────────────

    @Slot(str, result=str)
    def findSubtitleFiles(self, video_path: str) -> str:
        """영상 파일 옆에서 자막 파일을 탐색하여 JSON 배열로 반환합니다.

        우선순위: .ko.*(srt/vtt/smi/ass) → 같은 이름 .srt/.smi/.ass/.ssa/.vtt → .ja.*
        반환 형식: [{"path": "...", "label": "...", "filename": "..."}]
        """
        if not video_path:
            return "[]"
        try:
            vp = Path(video_path)
            if not vp.exists():
                return "[]"
            stem = vp.stem
            folder = vp.parent

            candidates = [
                (f"{stem}.ko.srt", "한국어"),
                (f"{stem}.ko.vtt", "한국어"),
                (f"{stem}.ko.smi", "한국어"),
                (f"{stem}.ko.ass", "한국어"),
                (f"{stem}.ko.ssa", "한국어"),
                (f"{stem}.srt", "자막"),
                (f"{stem}.smi", "자막"),
                (f"{stem}.ass", "자막"),
                (f"{stem}.ssa", "자막"),
                (f"{stem}.vtt", "자막"),
                (f"{stem}.ja.srt", "일본어"),
                (f"{stem}.ja.corrected.srt", "일본어(교정)"),
                (f"{stem}.ja.vtt", "일본어"),
                (f"{stem}.ja.ass", "일본어"),
            ]

            result = []
            for filename, label in candidates:
                p = folder / filename
                if p.is_file():
                    result.append({
                        "path": str(p.resolve()),
                        "label": label,
                        "filename": filename,
                    })
            return json.dumps(result, ensure_ascii=False)
        except Exception:
            return "[]"

    # ── 자막 파일 파싱 ───────────────────────────────────────

    @Slot(str, result=str)
    def loadSubtitleFile(self, path: str) -> str:
        """자막 파일을 파싱하여 큐 배열을 JSON으로 반환합니다.

        반환 형식: [{"start_ms": 0, "end_ms": 1000, "text": "..."}]
        """
        if not path:
            return "[]"
        try:
            p = Path(path)
            if not p.is_file():
                return "[]"
            ext = p.suffix.lower()
            try:
                text = p.read_text(encoding="utf-8-sig", errors="strict")
            except (UnicodeDecodeError, OSError):
                text = (
                    p.read_text(encoding="cp949", errors="replace")
                    if ext == ".smi"
                    else p.read_text(encoding="utf-8-sig", errors="replace")
                )
            if ext == ".srt":
                cues = self._parse_srt(text)
            elif ext == ".smi":
                cues = self._parse_smi(text)
            elif ext == ".vtt":
                cues = self._parse_vtt(text)
            elif ext in (".ass", ".ssa"):
                cues = self._parse_ass(text)
            else:
                cues = self._parse_srt(text)
            return json.dumps(cues, ensure_ascii=False)
        except Exception:
            return "[]"

    def _ts_to_ms(self, ts: str) -> int:
        """HH:MM:SS,mmm 또는 HH:MM:SS.mmm 형식의 타임스탬프를 ms로 변환."""
        ts = ts.strip().replace(",", ".")
        parts = ts.split(":")
        try:
            if len(parts) == 3:
                h, m, s = parts
                s, ms = (s.split(".") + ["0"])[:2]
                return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms[:3].ljust(3, "0"))
            elif len(parts) == 2:
                m, s = parts
                s, ms = (s.split(".") + ["0"])[:2]
                return (int(m) * 60 + int(s)) * 1000 + int(ms[:3].ljust(3, "0"))
        except Exception:
            pass
        return 0

    def _parse_srt(self, text: str) -> list:
        """SRT를 큐 목록으로 파싱.

        기존 구현은 블록을 ``\\n\\n``(빈 줄)로만 나눠서, 블록 사이 빈 줄이 없는 SRT(연속 큐)에서
        여러 자막이 한 덩어리로 합쳐져 번호·타임코드·대사가 한꺼번에 표시되는 문제가 있었다.
        """
        cues: list[dict] = []
        raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = raw.split("\n")
        n = len(lines)
        i = 0

        def _is_timing_line(s: str) -> bool:
            s = (s or "").strip()
            return bool(re.match(r"^[\d:,\.]+\s*-->\s*[\d:,\.]+", s))

        while i < n:
            while i < n and not lines[i].strip():
                i += 1
            if i >= n:
                break
            if lines[i].strip().isdigit():
                i += 1
                if i >= n:
                    break
            if not _is_timing_line(lines[i]):
                i += 1
                continue
            m = re.match(r"([\d:,\.]+)\s*-->\s*([\d:,\.]+)", lines[i].strip())
            if not m:
                i += 1
                continue
            start_ms = self._ts_to_ms(m.group(1))
            end_ms = self._ts_to_ms(m.group(2))
            i += 1
            body: list[str] = []
            while i < n:
                if _is_timing_line(lines[i]):
                    break
                nxt = lines[i].strip()
                if nxt.isdigit() and i + 1 < n and _is_timing_line(lines[i + 1]):
                    break
                body.append(lines[i])
                i += 1
            txt = "\n".join(body).strip()
            txt = re.sub(r"<[^>]+>", "", txt)
            if txt:
                cues.append({"start_ms": start_ms, "end_ms": end_ms, "text": txt})
        return cues

    def _parse_vtt(self, text: str) -> list:
        lines = text.splitlines()
        # VTT 헤더(WEBVTT) 제거
        start = next((i for i, l in enumerate(lines) if "-->" in l), 0)
        cleaned = "\n".join(lines[max(0, start - 1):])
        return self._parse_srt(cleaned)

    def _split_ass_comma_fields(self, body: str) -> list[str]:
        """ASS Dialogue 본문: 콤마로 필드 분리 ({...}) 안쪽 콤마는 유지."""
        parts: list[str] = []
        cur: list[str] = []
        depth = 0
        for ch in body:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth = max(0, depth - 1)
            if ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
                continue
            cur.append(ch)
        parts.append("".join(cur).strip())
        return parts

    def _parse_ass_timestamp(self, ts: str) -> int:
        """ASS/SSA: H:MM:SS.cc 또는 H:MM:SS.mmm 형태를 ms로."""
        ts = (ts or "").strip().replace(",", ".")
        m = re.match(r"^(\d+):(\d+):(\d+)(?:\.(\d+))?\s*$", ts)
        if not m:
            return 0
        h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3))
        frac = m.group(4) or ""
        base = (h * 3600 + mi * 60 + sec) * 1000
        if not frac:
            return base
        if len(frac) <= 2:
            return base + int(frac.ljust(2, "0")[:2]) * 10
        return base + min(int(frac[:3]), 999)

    # ── ASS 서브셋 렌더링 헬퍼 ─────────────────────────────

    @staticmethod
    def _ass_default_style() -> dict:
        return {
            "Fontname": "Arial",
            "Fontsize": 20.0,
            "PrimaryColour": "&H00FFFFFF",
            "SecondaryColour": "&H000000FF",
            "OutlineColour": "&H00000000",
            "BackColour": "&H80000000",
            "Bold": 0,
            "Italic": 0,
            "Underline": 0,
            "StrikeOut": 0,
            "Spacing": 0.0,
            "BorderStyle": 1,
            "Outline": 2.0,
            "Shadow": 0.0,
            "Alignment": 2,
            "MarginL": 10,
            "MarginR": 10,
            "MarginV": 10,
        }

    @staticmethod
    def _ass_color_to_argb(value: str | int, override_alpha: int | None = None) -> str:
        """ASS 색 표현(`&HAABBGGRR&` / `&HBBGGRR&` / 정수)을 `#AARRGGBB`로 변환.

        - override_alpha: 0..255 (있으면 알파 덮어쓰기, 없으면 원본 유지).
        """
        try:
            if isinstance(value, int):
                v = value & 0xFFFFFFFF
                a = (v >> 24) & 0xFF
                b = (v >> 16) & 0xFF
                g = (v >> 8) & 0xFF
                r = v & 0xFF
            else:
                s = str(value or "").strip()
                if s.startswith("&H") or s.startswith("&h"):
                    s = s[2:]
                s = s.rstrip("&").lstrip("&")
                s = s or "0"
                num = int(s, 16)
                if len(s) <= 6:
                    a = 0
                    b = (num >> 16) & 0xFF
                    g = (num >> 8) & 0xFF
                    r = num & 0xFF
                else:
                    a = (num >> 24) & 0xFF
                    b = (num >> 16) & 0xFF
                    g = (num >> 8) & 0xFF
                    r = num & 0xFF
        except (ValueError, TypeError):
            a, r, g, b = 0, 255, 255, 255
        if override_alpha is not None:
            a = max(0, min(255, int(override_alpha)))
        # ASS 알파는 'Transparency'(0=불투명, 255=투명) → ARGB 알파로 반전
        argb_a = 255 - a
        return f"#{argb_a:02X}{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def _ass_alpha_to_byte(value: str) -> int | None:
        """`&Hxx&` 알파 표현 → 0..255 정수(원본 ASS 'Transparency' 값)."""
        try:
            s = str(value or "").strip()
            if s.startswith("&H") or s.startswith("&h"):
                s = s[2:]
            s = s.rstrip("&")
            return int(s, 16) & 0xFF
        except (ValueError, TypeError):
            return None

    def _ass_drawing_to_svg(self, raw: str, scale_exp: int) -> tuple[str, tuple[float, float, float, float]]:
        """ASS 드로잉 문자열을 SVG path d 문자열과 (minx, miny, maxx, maxy)로 변환.

        scale_exp: `\\p<n>`의 n. n>=1이면 좌표를 2^(n-1)로 나눔.
        지원: m, n(이동만), l, b(3제어점), s/p/c (단순화: 직선/닫기로 처리).
        """
        if not raw:
            return "", (0.0, 0.0, 0.0, 0.0)
        divisor = (1 << max(0, int(scale_exp) - 1)) or 1

        tokens = re.findall(r"[a-zA-Z]|-?\d+(?:\.\d+)?", raw)
        i = 0
        out: list[str] = []
        bbox = [float("inf"), float("inf"), float("-inf"), float("-inf")]

        def _track(x: float, y: float) -> None:
            if x < bbox[0]:
                bbox[0] = x
            if y < bbox[1]:
                bbox[1] = y
            if x > bbox[2]:
                bbox[2] = x
            if y > bbox[3]:
                bbox[3] = y

        def _take_num() -> float | None:
            nonlocal i
            while i < len(tokens) and re.match(r"^[a-zA-Z]$", tokens[i]):
                i += 1
            if i >= len(tokens):
                return None
            try:
                v = float(tokens[i]) / divisor
            except ValueError:
                i += 1
                return None
            i += 1
            return v

        cmd = ""
        while i < len(tokens):
            tok = tokens[i]
            if re.match(r"^[a-zA-Z]$", tok):
                cmd = tok.lower()
                i += 1
                continue
            if cmd in ("m", "n"):
                x = _take_num()
                y = _take_num()
                if x is None or y is None:
                    break
                out.append(f"M {x} {y}")
                _track(x, y)
            elif cmd == "l":
                x = _take_num()
                y = _take_num()
                if x is None or y is None:
                    break
                out.append(f"L {x} {y}")
                _track(x, y)
            elif cmd == "b":
                xs = []
                for _ in range(6):
                    v = _take_num()
                    if v is None:
                        break
                    xs.append(v)
                if len(xs) == 6:
                    out.append(f"C {xs[0]} {xs[1]} {xs[2]} {xs[3]} {xs[4]} {xs[5]}")
                    _track(xs[0], xs[1]); _track(xs[2], xs[3]); _track(xs[4], xs[5])
                else:
                    break
            elif cmd in ("s", "p"):
                x = _take_num()
                y = _take_num()
                if x is None or y is None:
                    break
                out.append(f"L {x} {y}")
                _track(x, y)
            elif cmd == "c":
                out.append("Z")
            else:
                # 알 수 없는 명령 토큰 → 단순히 좌표 짝으로 흡수
                _take_num()

        if bbox[0] == float("inf"):
            bbox = [0.0, 0.0, 0.0, 0.0]
        # 마지막 닫힘이 없으면 자동 닫음 (ASS 영역 채우기 의미)
        if out and not out[-1].startswith("Z"):
            out.append("Z")
        return " ".join(out), tuple(bbox)

    def _parse_ass_overrides(self, block: str, state: dict, styles: dict, default_style: str) -> None:
        """`{...}` 내부 override 문자열을 읽어 `state`를 갱신한다."""
        if not block:
            return
        # 인자 있는 함수형 (\fad, \pos, \move, \fade, \t, \clip, \iclip, \org)
        for fn_match in re.finditer(r"\\(fad|pos|move|fade|t|clip|iclip|org)\s*\(([^()]*)\)", block):
            name = fn_match.group(1).lower()
            args = [a.strip() for a in fn_match.group(2).split(",") if a.strip() != ""]
            if name == "fad" and len(args) >= 2:
                try:
                    state["fade_in_ms"] = max(0, int(float(args[0])))
                    state["fade_out_ms"] = max(0, int(float(args[1])))
                except ValueError:
                    pass
            elif name == "pos" and len(args) >= 2:
                try:
                    state["pos"] = [float(args[0]), float(args[1])]
                except ValueError:
                    pass
            elif name == "move" and len(args) >= 4:
                try:
                    mv = [float(args[0]), float(args[1]), float(args[2]), float(args[3])]
                    if len(args) >= 6:
                        mv.extend([float(args[4]), float(args[5])])
                    state["move"] = mv
                except ValueError:
                    pass
            elif name == "fade" and len(args) >= 7:
                try:
                    a1, a2 = int(float(args[0])), int(float(args[2]))
                    t2, t3 = int(float(args[4])), int(float(args[5]))
                    state["fade_in_ms"] = max(0, t2)
                    state["fade_out_ms"] = max(0, max(0, int(float(args[6])) - t3))
                except (ValueError, IndexError):
                    pass
            # t/clip/iclip/org는 스타일 변경에 사용하지 않음 (서브셋 제외)
        # 함수형 토큰을 제거한 잔여 문자열에서 단순 토큰 처리
        residual = re.sub(r"\\(fad|pos|move|fade|t|clip|iclip|org)\s*\([^()]*\)", "", block)

        token_re = re.compile(
            r"\\(?:1c|2c|3c|4c|c|alpha|1a|2a|3a|4a|fn|fs|fsp|bord|xbord|ybord|shad|xshad|yshad|an|a|b|i|u|s|q|r|p)"
            r"(?:&H[0-9A-Fa-f]+&?|-?\d+(?:\.\d+)?|@?[A-Za-z0-9 _\-]+)?",
            re.IGNORECASE,
        )

        for m in token_re.finditer(residual):
            tok = m.group(0)
            tag_match = re.match(r"\\([0-9]?[a-zA-Z]+)(.*)$", tok)
            if not tag_match:
                continue
            tag = tag_match.group(1).lower()
            arg = tag_match.group(2).strip()
            if tag in ("c", "1c"):
                state["primary_value"] = arg
            elif tag == "3c":
                state["outline_value"] = arg
            elif tag == "4c":
                state["shadow_value"] = arg
            elif tag == "alpha":
                a = self._ass_alpha_to_byte(arg)
                if a is not None:
                    state["primary_alpha"] = a
                    state["outline_alpha"] = a
                    state["shadow_alpha"] = a
            elif tag == "1a":
                state["primary_alpha"] = self._ass_alpha_to_byte(arg)
            elif tag == "3a":
                state["outline_alpha"] = self._ass_alpha_to_byte(arg)
            elif tag == "4a":
                state["shadow_alpha"] = self._ass_alpha_to_byte(arg)
            elif tag == "fn":
                state["font_family"] = arg.lstrip("@") or state.get("font_family", "Arial")
            elif tag == "fs":
                try:
                    state["font_size"] = float(arg)
                except ValueError:
                    pass
            elif tag == "fsp":
                try:
                    state["spacing"] = float(arg)
                except ValueError:
                    pass
            elif tag == "bord":
                try:
                    state["bord"] = max(0.0, float(arg))
                except ValueError:
                    pass
            elif tag == "shad":
                try:
                    state["shad"] = float(arg)
                except ValueError:
                    pass
            elif tag == "an":
                try:
                    n = int(arg)
                    if 1 <= n <= 9:
                        state["an"] = n
                except ValueError:
                    pass
            elif tag == "a":
                try:
                    legacy = int(arg)
                    # 레거시 alignment(1..11) → \an(1..9) 변환
                    table = {1: 1, 2: 2, 3: 3, 5: 7, 6: 8, 7: 9, 9: 4, 10: 5, 11: 6}
                    if legacy in table:
                        state["an"] = table[legacy]
                except ValueError:
                    pass
            elif tag == "b":
                state["bold"] = bool(arg and arg != "0")
            elif tag == "i":
                state["italic"] = bool(arg and arg != "0")
            elif tag == "u":
                state["underline"] = bool(arg and arg != "0")
            elif tag == "s":
                state["strike"] = bool(arg and arg != "0")
            elif tag == "p":
                try:
                    state["draw"] = max(0, int(arg or "0"))
                except ValueError:
                    state["draw"] = 0
            elif tag == "r":
                target = arg.strip() or default_style
                style = styles.get(target) or styles.get(default_style)
                if style:
                    self._apply_style_to_state(state, style)

    def _apply_style_to_state(self, state: dict, style: dict) -> None:
        state["font_family"] = str(style.get("Fontname") or "Arial").lstrip("@") or "Arial"
        try:
            state["font_size"] = float(style.get("Fontsize") or 20)
        except (ValueError, TypeError):
            state["font_size"] = 20.0
        state["bold"] = bool(int(style.get("Bold") or 0))
        state["italic"] = bool(int(style.get("Italic") or 0))
        state["underline"] = bool(int(style.get("Underline") or 0))
        state["strike"] = bool(int(style.get("StrikeOut") or 0))
        try:
            state["spacing"] = float(style.get("Spacing") or 0)
        except (ValueError, TypeError):
            state["spacing"] = 0.0
        try:
            state["bord"] = float(style.get("Outline") or 0)
        except (ValueError, TypeError):
            state["bord"] = 0.0
        try:
            state["shad"] = float(style.get("Shadow") or 0)
        except (ValueError, TypeError):
            state["shad"] = 0.0
        try:
            state["an"] = int(style.get("Alignment") or 2)
        except (ValueError, TypeError):
            state["an"] = 2
        state["primary_value"] = style.get("PrimaryColour") or "&H00FFFFFF"
        state["outline_value"] = style.get("OutlineColour") or "&H00000000"
        state["shadow_value"] = style.get("BackColour") or "&H80000000"
        state["primary_alpha"] = None
        state["outline_alpha"] = None
        state["shadow_alpha"] = None
        state["draw"] = 0

    def _parse_ass(self, text: str) -> list:
        """ASS/SSA 자막을 파싱해 큐 리스트를 반환.

        반환 큐 형식:
            {start_ms, end_ms, text(plain), ass: { play_res_x, play_res_y, lines: [...] }}
        """
        cues: list = []
        play_res_x = 384
        play_res_y = 288
        wrap_style = 0
        styles: dict[str, dict] = {"Default": self._ass_default_style()}
        style_format: list[str] = []
        event_format: list[str] = []
        section = ""

        for raw_line in text.splitlines():
            line_stripped = raw_line.strip()
            if not line_stripped or line_stripped.startswith(";") or line_stripped.startswith("!"):
                continue
            if line_stripped.startswith("[") and line_stripped.endswith("]"):
                section = line_stripped[1:-1].strip().lower()
                continue

            if section == "script info":
                key, _, val = line_stripped.partition(":")
                key, val = key.strip().lower(), val.strip()
                if key == "playresx":
                    try:
                        play_res_x = max(1, int(float(val)))
                    except ValueError:
                        pass
                elif key == "playresy":
                    try:
                        play_res_y = max(1, int(float(val)))
                    except ValueError:
                        pass
                elif key == "wrapstyle":
                    try:
                        wrap_style = int(val)
                    except ValueError:
                        pass
                continue

            if section in ("v4+ styles", "v4 styles", "v4+styles"):
                key, _, val = line_stripped.partition(":")
                key, val = key.strip().lower(), val.strip()
                if key == "format":
                    style_format = [c.strip() for c in val.split(",")]
                    continue
                if key == "style" and style_format:
                    fields = [c.strip() for c in val.split(",")]
                    if len(fields) < len(style_format):
                        fields += [""] * (len(style_format) - len(fields))
                    style = self._ass_default_style()
                    for k, v in zip(style_format, fields):
                        style[k] = v
                    name = (style.get("Name") or "Default").strip() or "Default"
                    styles[name] = style
                continue

            if section == "events":
                key, _, val = line_stripped.partition(":")
                key, val = key.strip().lower(), val.strip()
                if key == "format":
                    event_format = [c.strip() for c in val.split(",")]
                    continue
                if key != "dialogue":
                    continue
                if not event_format:
                    event_format = ["Layer", "Start", "End", "Style", "Name",
                                    "MarginL", "MarginR", "MarginV", "Effect", "Text"]
                # Text 컬럼은 마지막이고 콤마 포함 가능 → 헤더에 따라 분리
                text_idx = -1
                for idx, name in enumerate(event_format):
                    if name.lower() == "text":
                        text_idx = idx
                        break
                if text_idx < 0:
                    text_idx = len(event_format) - 1
                fields = val.split(",", text_idx)
                if len(fields) <= text_idx:
                    continue
                event = {}
                for idx, name in enumerate(event_format):
                    event[name.lower()] = fields[idx] if idx < len(fields) else ""
                start_ms = self._parse_ass_timestamp(event.get("start", ""))
                end_ms = self._parse_ass_timestamp(event.get("end", ""))
                if end_ms <= start_ms:
                    continue
                style_name = (event.get("style", "") or "Default").strip() or "Default"
                style = styles.get(style_name) or styles.get("Default") or self._ass_default_style()
                margin_l = self._safe_int(event.get("marginl", "0")) or self._safe_int(style.get("MarginL", 10)) or 10
                margin_r = self._safe_int(event.get("marginr", "0")) or self._safe_int(style.get("MarginR", 10)) or 10
                margin_v = self._safe_int(event.get("marginv", "0")) or self._safe_int(style.get("MarginV", 10)) or 10

                body = event.get("text", "") or ""
                # \h(non-breaking space) → 공백, \N/\n → 줄 분리
                body_norm = body.replace("\\h", " ")
                segments = re.split(r"\\[Nn]", body_norm)

                ass_lines = []
                plain_parts: list[str] = []
                for seg in segments:
                    line = self._build_ass_line(seg, styles, style_name, margin_l, margin_r, margin_v)
                    if line is None:
                        continue
                    ass_lines.append(line)
                    plain_parts.append("".join(
                        run.get("text", "") for run in line["runs"] if run.get("kind") == "text"
                    ))
                if not ass_lines:
                    continue
                cues.append({
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": "\n".join(plain_parts).strip(),
                    "ass": {
                        "play_res_x": play_res_x,
                        "play_res_y": play_res_y,
                        "wrap_style": wrap_style,
                        "lines": ass_lines,
                    },
                })

        return cues

    @staticmethod
    def _safe_int(val) -> int:
        try:
            return int(float(str(val)))
        except (ValueError, TypeError):
            return 0

    def _build_ass_line(
        self,
        segment: str,
        styles: dict,
        default_style: str,
        margin_l: int,
        margin_r: int,
        margin_v: int,
    ) -> dict | None:
        """`\\N`로 분리된 한 라인의 토큰을 분석해 line 구조체를 만든다."""
        state = {
            "an": 2, "pos": None, "move": None,
            "fade_in_ms": 0, "fade_out_ms": 0,
            "primary_value": "&H00FFFFFF", "outline_value": "&H00000000", "shadow_value": "&H80000000",
            "primary_alpha": None, "outline_alpha": None, "shadow_alpha": None,
            "font_family": "Arial", "font_size": 20.0, "spacing": 0.0,
            "bold": False, "italic": False, "underline": False, "strike": False,
            "bord": 2.0, "shad": 0.0, "draw": 0,
        }
        style = styles.get(default_style) or self._ass_default_style()
        self._apply_style_to_state(state, style)

        # Dialogue 자체 MarginL/R/V로 덮어쓴 값 사용
        runs: list[dict] = []
        i = 0
        while i < len(segment):
            ch = segment[i]
            if ch == "{":
                end = segment.find("}", i + 1)
                block = segment[i + 1:end] if end >= 0 else segment[i + 1:]
                self._parse_ass_overrides(block, state, styles, default_style)
                i = end + 1 if end >= 0 else len(segment)
                continue
            # 텍스트 런: 다음 `{`까지
            next_brace = segment.find("{", i)
            run_text = segment[i:next_brace] if next_brace >= 0 else segment[i:]
            i = next_brace if next_brace >= 0 else len(segment)
            if not run_text:
                continue
            if state.get("draw"):
                path, bbox = self._ass_drawing_to_svg(run_text, int(state.get("draw") or 1))
                if not path:
                    continue
                width = max(1.0, bbox[2] - bbox[0])
                height = max(1.0, bbox[3] - bbox[1])
                runs.append({
                    "kind": "drawing",
                    "path": path,
                    "bbox": [bbox[0], bbox[1], width, height],
                    "fill": self._ass_color_to_argb(state["primary_value"], state.get("primary_alpha")),
                    "stroke": self._ass_color_to_argb(state["outline_value"], state.get("outline_alpha")),
                    "stroke_w": float(state.get("bord") or 0),
                })
            else:
                runs.append({
                    "kind": "text",
                    "text": run_text,
                    "font": {
                        "family": state.get("font_family") or "Arial",
                        "size": float(state.get("font_size") or 20.0),
                        "bold": bool(state.get("bold")),
                        "italic": bool(state.get("italic")),
                        "underline": bool(state.get("underline")),
                        "strike": bool(state.get("strike")),
                        "spacing": float(state.get("spacing") or 0.0),
                    },
                    "primary": self._ass_color_to_argb(state["primary_value"], state.get("primary_alpha")),
                    "outline": self._ass_color_to_argb(state["outline_value"], state.get("outline_alpha")),
                    "shadow": self._ass_color_to_argb(state["shadow_value"], state.get("shadow_alpha")),
                    "bord": float(state.get("bord") or 0),
                    "shad": float(state.get("shad") or 0),
                })

        if not runs:
            return None

        return {
            "an": int(state.get("an") or 2),
            "pos": state.get("pos"),
            "move": state.get("move"),
            "fade_in_ms": int(state.get("fade_in_ms") or 0),
            "fade_out_ms": int(state.get("fade_out_ms") or 0),
            "margin_l": margin_l,
            "margin_r": margin_r,
            "margin_v": margin_v,
            "runs": runs,
        }

    def _parse_smi(self, text: str) -> list:
        cues = []
        # <SYNC Start=ms>...<SYNC Start=ms> 패턴 파싱
        syncs = re.findall(
            r"<SYNC[^>]+Start\s*=\s*(\d+)[^>]*>\s*(.*?)(?=<SYNC|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        entries = []
        for start_str, content in syncs:
            txt = re.sub(r"<[^>]+>", "", content).strip()
            entries.append((int(start_str), txt))

        for i, (start_ms, txt) in enumerate(entries):
            end_ms = entries[i + 1][0] if i + 1 < len(entries) else start_ms + 3000
            if txt and txt.upper() not in ("&NBSP;", ""):
                cues.append({"start_ms": start_ms, "end_ms": end_ms, "text": txt})
        return cues
