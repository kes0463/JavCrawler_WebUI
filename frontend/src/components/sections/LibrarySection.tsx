import { memo, useCallback } from "react";
import { Trash2, X, SquareCheck, Square } from "lucide-react";

import { cn, sleep } from "@/lib/utils";
import type { LibraryItem } from "@/lib/types";
import { useAsync } from "@/hooks/useAsync";
import { useSelection } from "@/hooks/useSelection";
import { GlassCard } from "@/components/ui/GlassCard";
import { ActionButton } from "@/components/ui/ActionButton";

const simulateDelete = () => sleep(1600);

const getKey = (item: LibraryItem) => String(item.id);

interface LibrarySectionProps {
  items: LibraryItem[];
}

export function LibrarySection({ items }: LibrarySectionProps) {
  const sel = useSelection(items, getKey);
  const deleteAction = useAsync(simulateDelete);

  const handleDelete = useCallback(async () => {
    await deleteAction.execute();
    sel.clearAll();
  }, [deleteAction.execute, sel.clearAll]);

  return (
    <div className="space-y-3">
      {sel.count > 0 && (
        <div className="space-y-3">
          <span className="text-xs text-indigo-400">{sel.count}개 선택됨</span>

          <GlassCard
            variant="accent"
            noPadding
            className="px-4 py-2.5 flex items-center gap-3 animate-slide-in"
          >
            <span className="text-sm font-medium text-indigo-300 flex-1">
              {sel.count}개 항목 선택됨
            </span>
            <ActionButton
              size="sm"
              variant="ghost"
              onClick={sel.allSelected ? sel.clearAll : sel.selectAll}
            >
              {sel.allSelected ? "전체 해제" : "전체 선택"}
            </ActionButton>
            <ActionButton
              size="sm"
              variant="danger"
              loading={deleteAction.loading}
              icon={<Trash2 className="w-3.5 h-3.5" />}
              onClick={handleDelete}
            >
              삭제
            </ActionButton>
            <ActionButton size="icon" variant="ghost" onClick={sel.clearAll}>
              <X className="w-3.5 h-3.5" />
            </ActionButton>
          </GlassCard>
        </div>
      )}

      <button
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-white transition-colors px-0.5"
        onClick={sel.allSelected ? sel.clearAll : sel.selectAll}
      >
        {sel.allSelected
          ? <SquareCheck className="w-3.5 h-3.5 text-indigo-400" />
          : <Square className="w-3.5 h-3.5" />}
        전체 선택
      </button>

      <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-2">
        {items.map((item, i) => (
          <SelectableCard
            key={item.id}
            item={item}
            selected={sel.isSelected(item)}
            onToggle={sel.toggle}
            delay={i * 20}
          />
        ))}
      </div>
    </div>
  );
}

// ── SelectableCard ───────────────────────────────────────────────────

interface SelectableCardProps {
  item: LibraryItem;
  selected: boolean;
  onToggle: (item: LibraryItem) => void;
  delay: number;
}

const SelectableCard = memo(function SelectableCard({
  item,
  selected,
  onToggle,
  delay,
}: SelectableCardProps) {
  return (
    <button
      onClick={() => onToggle(item)}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "relative aspect-[2/3] rounded-xl border text-left",
        "transition-all duration-150 animate-scale-in",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50",
        selected
          ? "border-indigo-500/60 bg-indigo-500/10 scale-[0.97]"
          : "border-white/[0.06] bg-bg-card hover:border-white/[0.12] hover:bg-bg-surface hover:-translate-y-0.5",
      )}
    >
      <div className="absolute inset-0 rounded-xl flex flex-col items-center justify-center p-2 bg-gradient-to-b from-bg-surface to-bg-base">
        <span className="text-[9px] font-mono font-bold text-indigo-400 text-center leading-tight break-all">
          {item.code}
        </span>
      </div>

      <div
        className={cn(
          "absolute top-1.5 right-1.5 w-4 h-4 rounded-full border",
          "flex items-center justify-center transition-all duration-150",
          selected ? "bg-indigo-500 border-indigo-500 scale-110" : "bg-black/40 border-white/20",
        )}
      >
        {selected && <span className="text-white text-[8px] font-bold leading-none">✓</span>}
      </div>
    </button>
  );
});
