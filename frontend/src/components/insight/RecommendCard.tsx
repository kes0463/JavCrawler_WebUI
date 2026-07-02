import { Play } from "lucide-react";
import { coverUrl } from "@/api/library";
import type { RecommendItem } from "@/api/insight";
import { cn } from "@/lib/utils";

interface RecommendCardProps {
  item: RecommendItem;
  onOpen: (code: string) => void;
  onPlay?: (code: string) => void;
}

export function RecommendCard({ item, onOpen, onPlay }: RecommendCardProps) {
  const code = item.product_code;
  const score = item.rec_score ?? item.gap_score;

  return (
    <button
      type="button"
      onClick={() => onOpen(code)}
      className={cn(
        "group relative aspect-square w-full rounded-xl border border-white/[0.08]",
        "overflow-hidden bg-black/40 hover:border-accent/40 transition-colors",
      )}
    >
      <img
        src={coverUrl(code)}
        alt={code}
        className="absolute inset-0 w-full h-full object-cover"
        loading="lazy"
        onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
      />
      <div
        className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/35 to-black/10"
        aria-hidden
      />
      {onPlay && (
        <button
          type="button"
          onClick={e => { e.stopPropagation(); void onPlay(code); }}
          className="absolute top-2 right-2 z-10 w-9 h-9 rounded-full bg-black/55 border border-white/20 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <Play className="w-4 h-4 text-white fill-white" />
        </button>
      )}
      <div className="absolute inset-x-0 bottom-0 z-10 p-3 text-left">
        <p className="text-sm font-semibold text-white truncate">{code}</p>
        <p className="text-xs text-slate-300 line-clamp-2 leading-snug mt-0.5">{item.title_ko || "—"}</p>
        {score != null && (
          <p className="text-xs text-amber-400 tabular-nums mt-1">
            ★ {typeof score === "number" ? score.toFixed(2) : score}
          </p>
        )}
      </div>
    </button>
  );
}
