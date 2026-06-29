import { useState } from "react";
import { Heart, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { actressPhotoUrl, type ActressListItem } from "@/api/actress";
import { displayActressName, parseGenreTags } from "./utils";

interface ActressCardProps {
  item: ActressListItem;
  selected: boolean;
  onClick: () => void;
}

export function ActressCard({ item, selected, onClick }: ActressCardProps) {
  const [imgError, setImgError] = useState(false);
  const genreTags = parseGenreTags(item.genres, 2);
  const photoSrc = item.profile_image_url ? actressPhotoUrl(item.profile_image_url) : "";
  const showImage = Boolean(photoSrc) && !imgError;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "group w-full flex flex-col rounded-xl border overflow-hidden cursor-pointer",
        "transition-all duration-200 text-left",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50",
        selected
          ? "border-violet-500/50 bg-violet-500/10 shadow-glow-blue"
          : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.06] hover:border-white/[0.14]",
      )}
    >
      <div className="relative w-full aspect-[3/4] bg-[#0a0a12] overflow-hidden shrink-0">
        {showImage ? (
          <img
            src={photoSrc}
            alt=""
            draggable={false}
            loading="lazy"
            onError={() => setImgError(true)}
            className="absolute inset-0 w-full h-full object-cover object-top pointer-events-none"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-slate-600">
            <User className="w-10 h-10 opacity-60" />
          </div>
        )}
        {item.is_favorite && (
          <Heart className="absolute top-1.5 right-1.5 w-4 h-4 fill-rose-400 text-rose-400 z-10" />
        )}
        {item.user_score > 0 && (
          <span className="absolute bottom-1.5 left-1.5 z-10 px-1.5 py-0.5 rounded bg-black/60 text-amber-300 text-xs font-semibold">
            {item.user_score.toFixed(1)}
          </span>
        )}
      </div>
      <div className="p-2 min-w-0">
        <p
          className="font-semibold text-sm leading-snug truncate"
          title={displayActressName(item)}
        >
          {displayActressName(item)}
        </p>
        {item.name_ja && item.name_ko && (
          <p className="text-xs text-slate-400 truncate mt-0.5" title={item.name_ja}>
            {item.name_ja}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-1 mt-1">
          <p className="text-xs text-slate-500">작품 {item.work_count}</p>
          {genreTags.map(g => (
            <span
              key={g}
              className="px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-200 text-[11px] truncate max-w-[4rem]"
              title={g}
            >
              {g}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
