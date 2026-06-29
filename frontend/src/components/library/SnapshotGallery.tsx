import { cn } from "@/lib/utils";
import { snapshotUrl } from "@/api/library";
import { ImageLightbox } from "@/components/library/ImageLightbox";
import { useCallback, useEffect, useState } from "react";
import { ImageIcon } from "lucide-react";

interface SnapshotGalleryProps {
  productCode: string;
  count: number;
  className?: string;
  onStackOpenChange?: (open: boolean) => void;
}

const LIGHTBOX_Z = 115;

export function SnapshotGallery({
  productCode,
  count,
  className,
  onStackOpenChange,
}: SnapshotGalleryProps) {
  const [focusIndex, setFocusIndex] = useState<number | null>(null);

  useEffect(() => {
    onStackOpenChange?.(focusIndex !== null);
  }, [focusIndex, onStackOpenChange]);

  const goPrevious = useCallback(() => {
    setFocusIndex(i => (i == null ? null : Math.max(0, i - 1)));
  }, []);

  const goNext = useCallback(() => {
    setFocusIndex(i => (i == null ? null : Math.min(count - 1, i + 1)));
  }, [count]);

  if (count <= 0) {
    return (
      <div
        className={cn(
          "rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 text-center",
          className,
        )}
      >
        <ImageIcon className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        <p className="text-sm text-slate-500">스냅샷 없음</p>
        <p className="text-xs text-slate-600 mt-1 leading-relaxed">
          수집 완료 후 자동 생성되거나 데스크톱 앱에서 추출할 수 있습니다.
        </p>
      </div>
    );
  }

  const indices = Array.from({ length: count }, (_, i) => i);

  return (
    <>
      <div className={cn("space-y-2", className)}>
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-slate-300">스냅샷</p>
          <span className="text-xs text-slate-500 tabular-nums">{count}장</span>
        </div>
        <div className="max-h-[min(520px,50vh)] overflow-y-auto pr-1">
          <div className="grid grid-cols-3 gap-2">
            {indices.map(i => (
              <button
                key={i}
                type="button"
                onClick={() => setFocusIndex(i)}
                className="relative aspect-video rounded-lg overflow-hidden bg-black/40 border border-white/[0.08] hover:border-indigo-400/40 transition-colors group"
                aria-label={`스냅샷 ${i + 1} 확대`}
              >
                <img
                  src={snapshotUrl(productCode, i)}
                  alt={`스냅샷 ${i + 1}`}
                  loading="lazy"
                  decoding="async"
                  draggable={false}
                  className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform"
                />
              </button>
            ))}
          </div>
        </div>
      </div>

      {focusIndex != null && (
        <ImageLightbox
          open
          src={snapshotUrl(productCode, focusIndex)}
          alt={`${productCode} 스냅샷 ${focusIndex + 1}`}
          onClose={() => setFocusIndex(null)}
          zIndex={LIGHTBOX_Z}
          ariaLabel={`스냅샷 ${focusIndex + 1} 확대`}
          navigation={{
            index: focusIndex,
            total: count,
            onPrevious: goPrevious,
            onNext: goNext,
          }}
        />
      )}
    </>
  );
}
