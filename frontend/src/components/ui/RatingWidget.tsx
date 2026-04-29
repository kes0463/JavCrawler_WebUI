import { useState } from "react";
import { cn } from "@/lib/utils";

interface RatingWidgetProps {
  value?: number;
  max?: number;
  readOnly?: boolean;
  size?: "sm" | "md" | "lg";
  onChange?: (value: number) => void;
  className?: string;
}

export function RatingWidget({
  value = 0,
  max = 5,
  readOnly = false,
  size = "md",
  onChange,
  className,
}: RatingWidgetProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  const displayValue = hovered ?? value;

  const sizes = {
    sm: "text-sm gap-0.5",
    md: "text-base gap-1",
    lg: "text-xl gap-1.5",
  };

  return (
    <div
      className={cn("flex items-center", sizes[size], className)}
      onMouseLeave={() => setHovered(null)}
    >
      {Array.from({ length: max }).map((_, i) => {
        const filled = i < displayValue;
        return (
          <button
            key={i}
            type="button"
            disabled={readOnly}
            onClick={() => onChange?.(i + 1)}
            onMouseEnter={() => !readOnly && setHovered(i + 1)}
            className={cn(
              "transition-all duration-100 leading-none",
              readOnly ? "cursor-default" : "cursor-pointer hover:scale-110",
              filled ? "text-amber-400" : "text-white/[0.15]",
            )}
          >
            ★
          </button>
        );
      })}
      {!readOnly && value > 0 && (
        <button
          type="button"
          onClick={() => onChange?.(0)}
          className="ml-1 text-[10px] text-muted-foreground hover:text-rose-400 transition-colors"
        >
          ✕
        </button>
      )}
    </div>
  );
}
