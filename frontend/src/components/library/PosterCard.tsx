import { useState } from "react";
import { FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";

interface PosterCardProps {
  productCode: string;
  coverSrc?: string;
  hasFolder?: boolean;
  hasMeta?: boolean;
  delay?: number;
  onClick?: () => void;
}

export function PosterCard({
  productCode,
  coverSrc,
  hasFolder,
  hasMeta = true,
  delay = 0,
  onClick,
}: PosterCardProps) {
  const [imgError, setImgError] = useState(false);

  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "relative aspect-[2/3] rounded-xl border border-white/[0.06]",
        "bg-bg-card hover:border-white/[0.14] hover:scale-[1.03]",
        "transition-all duration-150 animate-scale-in overflow-hidden",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
      )}
    >
      {coverSrc && !imgError ? (
        <img
          src={coverSrc}
          alt={productCode}
          loading="lazy"
          onError={() => setImgError(true)}
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 bg-bg-surface flex items-center justify-center">
          <span className="text-[10px] font-mono text-muted-foreground opacity-50">NO IMG</span>
        </div>
      )}

      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent flex flex-col items-center justify-end p-1.5">
        <span className="text-[8px] font-mono font-bold text-indigo-300 text-center leading-tight">
          {productCode}
        </span>
        {!hasMeta && (
          <span className="text-[7px] text-amber-400 mt-0.5">미수집</span>
        )}
      </div>

      {hasFolder && (
        <div className="absolute top-1 right-1 w-3.5 h-3.5 rounded-full bg-indigo-500/70 flex items-center justify-center">
          <FolderOpen className="w-2 h-2 text-white" />
        </div>
      )}
    </button>
  );
}
