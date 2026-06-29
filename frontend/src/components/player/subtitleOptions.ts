export interface SubtitleDisplayOptions {
  /** 0.5 – 2.0 (기본 1) */
  sizeScale: number;
  /** 화면 하단에서의 거리 % (기본 12) */
  bottomPercent: number;
}

export const SUBTITLE_DEFAULTS: SubtitleDisplayOptions = {
  sizeScale: 1,
  bottomPercent: 12,
};

const STORAGE_KEY = "javstory.player.subtitle";

export function loadSubtitleOptions(): SubtitleDisplayOptions {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...SUBTITLE_DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<SubtitleDisplayOptions>;
    return {
      sizeScale: clamp(parsed.sizeScale ?? SUBTITLE_DEFAULTS.sizeScale, 0.5, 2.5),
      bottomPercent: clamp(parsed.bottomPercent ?? SUBTITLE_DEFAULTS.bottomPercent, 4, 40),
    };
  } catch {
    return { ...SUBTITLE_DEFAULTS };
  }
}

export function saveSubtitleOptions(opts: SubtitleDisplayOptions): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(opts));
  } catch {
    /* ignore */
  }
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}
