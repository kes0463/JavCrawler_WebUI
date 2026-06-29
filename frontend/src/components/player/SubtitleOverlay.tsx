import { useMemo, type CSSProperties } from "react";
import type { AssSubtitleLine, SubtitleCue } from "@/api/playback";
import {
  SUBTITLE_DEFAULTS,
  type SubtitleDisplayOptions,
} from "@/components/player/subtitleOptions";

const ASS_ALIGN: Record<number, { x: string; y: string; textAlign: "left" | "center" | "right" }> = {
  1: { x: "left", y: "bottom", textAlign: "left" },
  2: { x: "center", y: "bottom", textAlign: "center" },
  3: { x: "right", y: "bottom", textAlign: "right" },
  4: { x: "left", y: "middle", textAlign: "left" },
  5: { x: "center", y: "middle", textAlign: "center" },
  6: { x: "right", y: "middle", textAlign: "right" },
  7: { x: "left", y: "top", textAlign: "left" },
  8: { x: "center", y: "top", textAlign: "center" },
  9: { x: "right", y: "top", textAlign: "right" },
};

function lineStyle(
  line: AssSubtitleLine,
  scaleX: number,
  scaleY: number,
): CSSProperties {
  const align = ASS_ALIGN[line.an] || ASS_ALIGN[2];
  const style: CSSProperties = {
    position: "absolute",
    textAlign: align.textAlign,
    whiteSpace: "pre-wrap",
    pointerEvents: "none",
    lineHeight: 1.25,
  };

  if (line.pos && line.pos.length >= 2) {
    style.left = `${(line.pos[0] / scaleX) * 100}%`;
    style.top = `${(line.pos[1] / scaleY) * 100}%`;
    style.transform = "translate(-50%, -50%)";
    return style;
  }

  const ml = (line.margin_l / scaleX) * 100;
  const mr = (line.margin_r / scaleX) * 100;
  const mv = (line.margin_v / scaleY) * 100;

  if (align.x === "left") style.left = `${ml}%`;
  if (align.x === "right") style.right = `${mr}%`;
  if (align.x === "center") {
    style.left = `${ml}%`;
    style.right = `${mr}%`;
  }
  if (align.y === "bottom") style.bottom = `${mv}%`;
  if (align.y === "top") style.top = `${mv}%`;
  if (align.y === "middle") {
    style.top = "50%";
    style.transform = "translateY(-50%)";
  }
  return style;
}

function verticalOffsetPx(
  videoHeight: number,
  bottomPercent: number,
): number {
  const delta = bottomPercent - SUBTITLE_DEFAULTS.bottomPercent;
  return -(delta / 100) * (videoHeight > 0 ? videoHeight : 480);
}

export function AssSubtitleOverlay({
  cue,
  videoWidth,
  videoHeight,
  display,
}: {
  cue: SubtitleCue;
  videoWidth: number;
  videoHeight: number;
  display: SubtitleDisplayOptions;
}) {
  const ass = cue.ass;
  const scale = useMemo(() => {
    if (!ass) return { sx: 1920, sy: 1080 };
    return {
      sx: ass.play_res_x || 1920,
      sy: ass.play_res_y || 1080,
    };
  }, [ass]);

  if (!ass?.lines?.length) return null;

  const fontScale = (videoWidth > 0 ? videoWidth / scale.sx : 1) * display.sizeScale;
  const offsetY = verticalOffsetPx(videoHeight, display.bottomPercent);

  return (
    <div
      className="absolute inset-0 overflow-hidden pointer-events-none"
      style={{ transform: `translateY(${offsetY}px)` }}
    >
      {ass.lines.map((line, li) => (
        <div key={li} style={lineStyle(line, scale.sx, scale.sy)}>
          {line.runs.map((run, ri) => {
            if (run.kind === "drawing" && run.path) {
              const bbox = run.bbox || [0, 0, 100, 100];
              return (
                <svg
                  key={ri}
                  viewBox={`${bbox[0]} ${bbox[1]} ${bbox[2]} ${bbox[3]}`}
                  className="inline-block"
                  style={{ width: bbox[2] * fontScale, height: bbox[3] * fontScale }}
                >
                  <path
                    d={run.path}
                    fill={run.fill || "#FFFFFFFF"}
                    stroke={run.stroke}
                    strokeWidth={run.stroke_w || 0}
                  />
                </svg>
              );
            }
            const f = run.font;
            return (
              <span
                key={ri}
                style={{
                  color: run.primary || "#FFFFFF",
                  WebkitTextStroke: run.bord
                    ? `${Math.max(1, (run.bord || 0) * fontScale * 0.5)}px ${run.outline || "#000000"}`
                    : undefined,
                  textShadow: run.shad
                    ? `${run.shad}px ${run.shad}px 2px ${run.shadow || "#80000000"}`
                    : undefined,
                  fontFamily: f?.family || "Arial, sans-serif",
                  fontSize: `${(f?.size || 20) * fontScale}px`,
                  fontWeight: f?.bold ? 700 : 400,
                  fontStyle: f?.italic ? "italic" : "normal",
                  textDecoration: [
                    f?.underline ? "underline" : "",
                    f?.strike ? "line-through" : "",
                  ].filter(Boolean).join(" ") || "none",
                  letterSpacing: f?.spacing ? `${f.spacing * fontScale}px` : undefined,
                }}
              >
                {run.text}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function PlainSubtitleOverlay({
  text,
  display,
}: {
  text: string;
  display: SubtitleDisplayOptions;
}) {
  if (!text.trim()) return null;
  const basePx = 18;
  return (
    <div
      className="absolute inset-x-0 flex justify-center px-6 pointer-events-none"
      style={{ bottom: `${display.bottomPercent}%` }}
    >
      <p
        className="max-w-[90%] text-center text-white leading-relaxed px-4 py-2 rounded-lg"
        style={{
          fontSize: `${basePx * display.sizeScale}px`,
          background: "rgba(0,0,0,0.72)",
          textShadow: "0 1px 3px rgba(0,0,0,0.9)",
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </p>
    </div>
  );
}

export function SubtitleOverlay({
  cue,
  videoWidth,
  videoHeight,
  display,
}: {
  cue: SubtitleCue | null;
  videoWidth: number;
  videoHeight: number;
  display: SubtitleDisplayOptions;
}) {
  if (!cue) return null;
  if (cue.ass?.lines?.length) {
    return (
      <AssSubtitleOverlay
        cue={cue}
        videoWidth={videoWidth}
        videoHeight={videoHeight}
        display={display}
      />
    );
  }
  return <PlainSubtitleOverlay text={cue.text} display={display} />;
}
