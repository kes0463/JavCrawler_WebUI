"""
파일명/경로에서 JAV 품번 추출.

실제 수집 파일명 패턴(접두 숫자, FC2-PPV 다중 하이픈, HEYZO 공백, 괄호 속 품번 등)을 반영.
잘못된 `[` … `)` 매칭으로 품번이 지워지지 않도록, 괄호 제거는 균형 잡힌 `[...]` 만 처리한다.

동일 작품 분할 파일( A/B/C, Part 1/2, (1) 등)은 품번 정규화 시 끝부분 표기를 제거해
같은 품번으로 인식한다. `extract_split_part_label` 로 파트만 따로 조회 가능.
"""
from __future__ import annotations

import re
from pathlib import Path


def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _strip_leading_bullet(s: str) -> str:
    if s.startswith("- "):
        return s[2:]
    return s


def _remove_balanced_square_brackets(s: str) -> str:
    """`[FHD]`, `[Meguri, 메구리]` 처럼 닫는 `]` 가 있는 블록만 제거."""
    while True:
        m = re.search(r"\[[^\]]+\]", s)
        if not m:
            break
        s = s[: m.start()] + " " + s[m.end() :]
    return s


def _remove_common_parenthetical_tags(s: str) -> str:
    """날짜·해상도 등 흔한 괄호 구간만 제거 (품번이 들어간 짧은 괄호는 건드리지 않음)."""
    s = re.sub(r"\(\d{4}-\d{2}-\d{2}\)", " ", s)
    s = re.sub(r"\(\d{4}년\s*\d{1,2}월\)", " ", s)
    s = re.sub(r"\(\d{4}\s*년\s*\d{1,2}\s*월\)", " ", s)
    return s


def _stem_only(video_path: str | Path) -> str:
    raw = str(video_path).strip().strip('"').strip("'")
    stem = Path(raw).stem if Path(raw).suffix else raw
    stem = _strip_leading_bullet(stem)
    return _normalize_whitespace(stem)


# 동일 작품 분할: 파일명 **끝**에 붙는 표기만 제거 (중간 제목은 유지)
_SPLIT_TAIL_PATTERNS: tuple[tuple[str, int], ...] = (
    # Part 1, Part 12, Part01, Pt.2, P3 (맨 끝 한 토큰)
    (r"\s+Part\s*\d{1,3}\s*$", re.IGNORECASE),
    (r"\s+Pt\.?\s*\d{1,3}\s*$", re.IGNORECASE),
    (r"\s+P\s*\d{1,3}\s*$", re.IGNORECASE),
    (r"\s+CD\s*\d{1,2}\s*$", re.IGNORECASE),
    (r"\s+Disc\s*\d{1,2}\s*$", re.IGNORECASE),
    (r"\s+vol\.?\s*\d{1,2}\s*$", re.IGNORECASE),
    (r"\s+Episode\s*\d{1,3}\s*$", re.IGNORECASE),
    (r"\s+Ep\.?\s*\d{1,3}\s*$", re.IGNORECASE),
    # (1) (2) — 끝 괄호 숫자 (짧은 것만)
    (r"\s*\(\d{1,2}\)\s*$", 0),
    # - A … - Z, 공백 A … (분할 권 구분)
    (r"\s+-\s*[A-Z]\s*$", 0),
    (r"\s+[A-Z]\s*$", 0),
    # _1 _2 (짧은 꼬리만)
    (r"_\d{1,2}\s*$", 0),
    (r"\s+_\s*\d{1,2}\s*$", 0),
    (r"_full\s*$", re.IGNORECASE),
    (r"\s+full\s*$", re.IGNORECASE),
)


def strip_split_suffixes(stem: str) -> str:
    """품번 추출용: 끝에 붙은 Part/A/B/_1 등 분할 표기를 반복 제거."""
    s = stem.strip()
    if not s:
        return s
    changed = True
    while changed:
        changed = False
        before = s
        for pat, flags in _SPLIT_TAIL_PATTERNS:
            fl = flags if flags else 0
            s2 = re.sub(pat, "", s, flags=fl)
            if s2 != s:
                s = _normalize_whitespace(s2)
                changed = True
                break
        if s == before and not changed:
            break
    return s


def extract_split_part_label(video_path: str | Path) -> str | None:
    """
    분할 표기만 반환 (품번과 별도). 없으면 None.

    예: ``Part 2``, ``A``, ``(1)``, ``_2``
    """
    stem = _stem_only(video_path)
    if not stem:
        return None

    # Part / Pt 는 문자열 어디에 있어도 우선 (Part 12 (1) 처럼 괄호가 뒤에 있어도)
    m = re.search(r"(?i)\bPart\s*(\d{1,3})\b", stem)
    if m:
        return f"Part {m.group(1)}"

    m = re.search(r"(?i)\bPt\.?\s*(\d{1,3})\b", stem)
    if m:
        return f"Part {m.group(1)}"

    m = re.search(r"(?i)(?<!\w)P\s*(\d{1,3})\s*$", stem)
    if m and not re.search(r"(?i)FC2\s*-\s*PPV|FC2PPV", stem):
        return f"P{m.group(1)}"

    m = re.search(r"\s+-\s*([A-Z])\s*$", stem)
    if m:
        return m.group(1)

    m = re.search(r"\s+([A-Z])\s*$", stem)
    if m:
        return m.group(1)

    m = re.search(r"\((\d{1,2})\)\s*$", stem)
    if m:
        return f"({m.group(1)})"

    m = re.search(r"_(\d{1,2})\s*$", stem)
    if m:
        return f"_{m.group(1)}"

    return None


def _prepare_text_from_path(video_path: str | Path) -> str:
    stem = _stem_only(video_path)
    stem = _remove_balanced_square_brackets(stem)
    stem = _remove_common_parenthetical_tags(stem)
    stem = _normalize_whitespace(stem)
    stem = strip_split_suffixes(stem)
    return stem


def _try_high_priority_before_brackets(stem: str) -> str | None:
    """
    `[FC2] PPV3193265`, `Caribbeancompr.com] 052716-003` 등
    대괄호 제거 시 맥락이 사라지는 형식을 먼저 처리.
    숫자 뒤에는 `_full`, `_1` 등이 올 수 있어 \\b 대신 (?![0-9]) 사용.
    """
    t = stem

    m = re.search(r"FC2\s*-\s*PPV\s*-\s*(\d{5,10})(?![0-9])", t, flags=re.IGNORECASE)
    if m:
        return f"FC2-PPV-{m.group(1)}"

    m = re.search(
        r"(?:\[FC2\]|FC2)\s*\]?\s*PPV\s*[-]?\s*(\d{5,10})(?![0-9])",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        return f"FC2PPV-{m.group(1)}"

    m = re.search(r"FC2PPV\s*-\s*(\d{5,10})(?![0-9])", t, flags=re.IGNORECASE)
    if m:
        return f"FC2PPV-{m.group(1)}"

    m = re.search(
        r"(?i)Caribbeancom(?:pr)?(?:\.com)?\s*\]?\s*(\d{6})[-_\s]+(\d{2,3})(?![0-9])",
        t,
    )
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    m = re.search(r"(?i)\[Tokyo Hot\]\s*([A-Z]\d{3,5})\b", t)
    if m:
        return m.group(1).upper()

    m = re.search(r"(?i)Tokyo Hot\s+([A-Z]\d{3,5})\b", t)
    if m:
        return m.group(1).upper()

    m = re.search(
        r"(?i)\[1Pondo\]\s*#?\s*(\d{6})[-_](\d{2,3})(?![0-9])",
        t,
    )
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    m = re.search(
        r"(?i)\[10Musume\]\s*#?\s*(\d{6})[-_](\d{2,3})(?![0-9])",
        t,
    )
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    return None


def _uniq_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _collect_candidates(text: str) -> list[str]:
    """우선순위대로 후보를 모은 뒤, 길이·형식으로 정렬해 하나를 고른다."""
    t = text

    # FC2 계열 (태그 제거 후에도 동작하도록 유지; `_full` 등 접미사 허용)
    m = re.search(r"FC2\s*-\s*PPV\s*-\s*(\d{5,10})(?![0-9])", t, flags=re.IGNORECASE)
    if m:
        return [f"FC2-PPV-{m.group(1)}"]
    m = re.search(r"FC2PPV\s*-\s*(\d{5,10})(?![0-9])", t, flags=re.IGNORECASE)
    if m:
        return [f"FC2PPV-{m.group(1)}"]

    found: list[str] = []

    # 1Pondo / 10Musume: 태그 제거 후 남는 `032022-001` 등
    for m in re.finditer(
        r"(?i)(?:1Pondo|10Musume)\s*\]?\s*#?\s*(\d{6})[-_](\d{2,3})(?![0-9])",
        t,
    ):
        found.append(f"{m.group(1)}-{m.group(2)}")

    # 6자리-3자리 / 6자리_3자리 / 6자리 공백 3자리 (태그 제거 후 본문만 남은 경우)
    for m in re.finditer(r"(?<![0-9])(\d{6})-(\d{3})(?![0-9])", t):
        found.append(f"{m.group(1)}-{m.group(2)}")
    for m in re.finditer(r"(?<![0-9])(\d{6})_(\d{2,3})(?![0-9])", t):
        found.append(f"{m.group(1)}-{m.group(2)}")
    for m in re.finditer(r"(?<![0-9])(\d{6})\s+(\d{3})(?![0-9])", t):
        found.append(f"{m.group(1)}-{m.group(2)}")

    # Caribbeancom (짧은 형태)
    for m in re.finditer(
        r"(?i)Caribbeancom\s+(\d{6})-(\d{3})(?![0-9])",
        t,
    ):
        found.append(f"{m.group(1)}-{m.group(2)}")

    # 3) 숫자 접두 + 스튜디오코드-번호 (420HOI-376, 300MIUM-1021, 261ARA-537, 116SHH-004 …)
    for m in re.finditer(
        r"(?<![A-Za-z0-9])(\d{2,4}[A-Za-z]{2,12})-(\d{2,8})(?![0-9])",
        t,
        flags=re.IGNORECASE,
    ):
        found.append(f"{m.group(1).upper()}-{m.group(2)}")

    # 3b) H4610-ki180902, H4610-KI220320 (H + 4자리 - 2글자+6자리)
    for m in re.finditer(
        r"(?<![A-Za-z0-9])(H\d{4})-([A-Za-z]{2}\d{6})(?![0-9])",
        t,
        flags=re.IGNORECASE,
    ):
        found.append(f"{m.group(1).upper()}-{m.group(2).upper()}")

    # 3c) C0930 pla0093
    for m in re.finditer(
        r"(?i)\b(C\d{4})\s+(pla\d{4,})\b",
        t,
    ):
        found.append(f"{m.group(1).upper()}-{m.group(2).upper()}")

    # 4) HEYZO 1037 / OKSN 202 (스튜디오코드 공백 번호)
    for m in re.finditer(
        r"(?<![A-Za-z0-9])HEYZO\s+(\d{3,5})(?![0-9])", t, flags=re.IGNORECASE
    ):
        found.append(f"HEYZO-{m.group(1)}")
    for m in re.finditer(
        r"(?<![A-Za-z0-9])OKSN\s+(\d{2,4})(?![0-9])", t, flags=re.IGNORECASE
    ):
        found.append(f"OKSN-{m.group(1)}")

    # 5) MX(G)S-1243 → 검색·파일명 일치용으로 MXGS-1243 로 정규화
    for m in re.finditer(
        r"(?<![A-Za-z0-9])M[Xx]\([Gg]\)[Ss]-(\d{2,5})(?![0-9])", t
    ):
        found.append(f"MXGS-{m.group(1)}")

    # 6) (NTR-021) 처럼 괄호만 감싼 품번
    for m in re.finditer(r"\(([A-Za-z]{2,12})-(\d{2,8})\)", t):
        found.append(f"{m.group(1).upper()}-{m.group(2)}")

    # 7) 언더스코어 ABCD_123
    for m in re.finditer(
        r"(?<![A-Za-z0-9])([A-Za-z]{2,12})_(\d{2,8})(?![0-9])",
        t,
        flags=re.IGNORECASE,
    ):
        found.append(f"{m.group(1).upper()}-{m.group(2)}")

    # 8) 일반 AAA-123 / ABCD-12345
    for m in re.finditer(
        r"(?<![A-Za-z0-9])([A-Za-z]{2,12})-(\d{2,8})(?![0-9])",
        t,
        flags=re.IGNORECASE,
    ):
        found.append(f"{m.group(1).upper()}-{m.group(2)}")

    found = _uniq_preserve_order(found)
    if not found:
        return []

    # 동일 품번의 변형(예: FC2PPV vs FC2-PPV) 중 더 긴/구체적인 문자열 선호
    def score(code: str) -> tuple[int, int]:
        return (len(code), code.count("-"))

    found.sort(key=score, reverse=True)
    return found


def extract_product_code_from_folder_name(folder: str | Path) -> str | None:
    """
    폴더 **이름**(basename)에서 품번 1개 추출.
    파일명 추출과 동일한 규칙(`extract_product_code_from_path`).
    """
    label = Path(folder).name
    if not (label or "").strip():
        return None
    return extract_product_code_from_path(label + ".mp4")


def list_distinct_product_codes_from_folder_label(label: str) -> list[str]:
    """
    폴더명에 등장할 수 있는 품번 후보를 중복 없이 나열(길이·형식 우선순위는 `_collect_candidates`와 동일).
    후보가 둘 이상이면 품번이 모호할 수 있음.
    """
    label = (label or "").strip()
    if not label:
        return []
    text = _prepare_text_from_path(label + ".mp4")
    if not text:
        return []
    cands = _collect_candidates(text)
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        u = c.upper()
        if u not in seen:
            seen.add(u)
            out.append(c)
    return out


def extract_product_code_from_path(video_path: str | Path) -> str | None:
    """
    파일 경로/이름에서 품번 한 개를 추출.

    - 여러 후보가 있으면 길이가 길고 하이픈이 많은 쪽(예: FC2-PPV-…)을 우선.
    - 동일 작품 분할( Part 1, A/B, _1 등)은 `strip_split_suffixes` 로 끝 표기를 제거한 뒤 같은 품번으로 인식.
    - 표지/자막/스토리.txt 등 품번이 없는 파일은 None.
    """
    stem_raw = _stem_only(video_path)
    if not stem_raw:
        return None

    stem_for_early = strip_split_suffixes(stem_raw)
    early = _try_high_priority_before_brackets(stem_for_early)
    if early:
        return early

    text = _prepare_text_from_path(video_path)
    if not text:
        return None

    # 의미 없는 단일 파일명
    if re.fullmatch(r"\d+\.?", text):
        return None
    if text.lower() in {"스토리", "story", "name"}:
        return None

    cands = _collect_candidates(text)
    if not cands:
        return None

    # 가장 점수 높은 하나
    best = cands[0]

    # 흔한 오탐: 순수 날짜/버전 (2025-12 등) — 품번은 보통 알파벳 포함
    if re.fullmatch(r"\d{4}-\d{1,2}", best):
        if len(cands) > 1:
            return cands[1]
        return None

    return best


def resolve_product_code_for_video(
    video_path: str | Path,
    hint: str | None = None,
) -> str:
    """
    워커·큐 공통 품번 해석: 경로에서 추출 → hint → 파일 stem 순.
    """
    extracted = extract_product_code_from_path(video_path)
    if extracted:
        return extracted.strip().upper()
    h = (hint or "").strip().upper()
    if h:
        return h
    stem = Path(str(video_path)).stem.strip()
    return stem.upper() if stem else ""
