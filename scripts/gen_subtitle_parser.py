"""One-off: extract subtitle parsing from gui/models/player_model.py."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src_path = ROOT / "gui/models/player_model.py"
src = src_path.read_text(encoding="utf-8")
tree = ast.parse(src)

names = {
    "_ts_to_ms",
    "_parse_srt",
    "_parse_vtt",
    "_split_ass_comma_fields",
    "_parse_ass_timestamp",
    "_ass_default_style",
    "_ass_color_to_argb",
    "_ass_alpha_to_byte",
    "_ass_drawing_to_svg",
    "_parse_ass_overrides",
    "_apply_style_to_state",
    "_parse_ass",
    "_safe_int",
    "_build_ass_line",
    "_parse_smi",
}


class Extractor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.methods: dict[str, str] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in names:
            seg = ast.get_source_segment(src, node)
            if seg:
                self.methods[node.name] = seg


ex = Extractor()
ex.visit(tree)

header = '''"""Subtitle discovery and parsing — shared by QML player and WebUI."""
from __future__ import annotations

import json
import re
from pathlib import Path

'''

body_parts: list[str] = []
for name in [
    "_ts_to_ms",
    "_parse_srt",
    "_parse_vtt",
    "_split_ass_comma_fields",
    "_parse_ass_timestamp",
    "_ass_default_style",
    "_ass_color_to_argb",
    "_ass_alpha_to_byte",
    "_ass_drawing_to_svg",
    "_parse_ass_overrides",
    "_apply_style_to_state",
    "_parse_ass",
    "_safe_int",
    "_build_ass_line",
    "_parse_smi",
]:
    seg = ex.methods.get(name)
    if not seg:
        raise SystemExit(f"missing {name}")
    seg = re.sub(r"^    @staticmethod\n    ", "", seg, flags=re.M)
    seg = re.sub(r"^    def ", "def ", seg, flags=re.M)
    seg = re.sub(r"\n        ", "\n    ", seg)
    seg = re.sub(r"self\._", "_", seg)
    seg = re.sub(r"self\.", "", seg)
    seg = re.sub(r"def (\w+)\(self,", r"def \1(", seg)
    seg = re.sub(r"def (\w+)\(self\)", r"def \1()", seg)
    body_parts.append(seg)

footer = '''

def find_subtitle_files(video_path: str) -> list[dict]:
    if not video_path:
        return []
    try:
        vp = Path(video_path)
        if not vp.exists():
            return []
        stem = vp.stem
        folder = vp.parent
        candidates = [
            (f"{stem}.ko.srt", "ko"),
            (f"{stem}.ko.vtt", "ko"),
            (f"{stem}.ko.smi", "ko"),
            (f"{stem}.ko.ass", "ko"),
            (f"{stem}.ko.ssa", "ko"),
            (f"{stem}.srt", "sub"),
            (f"{stem}.smi", "sub"),
            (f"{stem}.ass", "sub"),
            (f"{stem}.ssa", "sub"),
            (f"{stem}.vtt", "sub"),
            (f"{stem}.ja.srt", "ja"),
            (f"{stem}.ja.corrected.srt", "ja-corrected"),
            (f"{stem}.ja.vtt", "ja"),
            (f"{stem}.ja.ass", "ja"),
        ]
        labels = {
            "ko": "\ud55c\uad6d\uc5b4",
            "sub": "\uc790\ub9d9",
            "ja": "\uc77c\ubcf8\uc5b4",
            "ja-corrected": "\uc77c\ubcf8\uc5b4(\uad50\uc815)",
        }
        result = []
        for filename, key in candidates:
            p = folder / filename
            if p.is_file():
                result.append({
                    "path": str(p.resolve()),
                    "label": labels[key],
                    "filename": filename,
                })
        return result
    except Exception:
        return []


def load_subtitle_cues(path: str) -> list[dict]:
    if not path:
        return []
    try:
        p = Path(path)
        if not p.is_file():
            return []
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
            cues = _parse_srt(text)
        elif ext == ".smi":
            cues = _parse_smi(text)
        elif ext == ".vtt":
            cues = _parse_vtt(text)
        elif ext in (".ass", ".ssa"):
            cues = _parse_ass(text)
        else:
            cues = _parse_srt(text)
        return cues
    except Exception:
        return []


def find_subtitle_files_json(video_path: str) -> str:
    return json.dumps(find_subtitle_files(video_path), ensure_ascii=False)


def load_subtitle_cues_json(path: str) -> str:
    return json.dumps(load_subtitle_cues(path), ensure_ascii=False)
'''

out = header + "\n\n".join(body_parts) + footer
out_path = ROOT / "javstory/library/subtitle_parser.py"
out_path.write_text(out, encoding="utf-8")
print("written", out_path, len(out))
