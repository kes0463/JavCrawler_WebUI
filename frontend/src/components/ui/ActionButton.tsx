import { cn } from "@/lib/utils";
import { type ButtonHTMLAttributes, forwardRef, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { useRipple } from "@/hooks/useRipple";

interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "outline";
  size?: "sm" | "md" | "lg" | "icon";
  loading?: boolean;
  icon?: React.ReactNode;
}

const ActionButton = forwardRef<HTMLButtonElement, ActionButtonProps>(
  (
    {
      className,
      variant = "secondary",
      size = "md",
      loading,
      icon,
      children,
      disabled,
      onMouseDown,
      ...props
    },
    ref,
  ) => {
    const { ripples, onMouseDown: rippleMouseDown } = useRipple();

    const handleMouseDown = useCallback(
      (e: React.MouseEvent<HTMLButtonElement>) => {
        rippleMouseDown(e);
        onMouseDown?.(e);
      },
      [rippleMouseDown, onMouseDown],
    );

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        onMouseDown={handleMouseDown}
        className={cn(
          "relative overflow-hidden inline-flex items-center justify-center gap-2 rounded-xl font-medium",
          "transition-all duration-200 ease-spring gpu",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-1 focus-visible:ring-offset-bg-base",
          "disabled:opacity-35 disabled:pointer-events-none",
          "active:scale-[0.96]",
          size === "sm"   && "h-8  px-3.5 text-xs",
          size === "md"   && "h-9  px-4   text-sm",
          size === "lg"   && "h-11 px-6   text-sm",
          size === "icon" && "h-9  w-9",
          variant === "primary" && [
            "bg-accent text-white",
            "shadow-[0_1px_2px_rgba(0,0,0,0.4),inset_0_1px_0_rgba(255,255,255,0.15)]",
            "hover:bg-accent-light hover:shadow-glow-sm hover:scale-[1.025]",
            "active:bg-accent-dark",
          ],
          variant === "secondary" && [
            "bg-bg-surface text-[#c8c8e0] border border-white/[0.09]",
            "shadow-[0_1px_2px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.05)]",
            "hover:bg-bg-hover hover:border-white/[0.15] hover:text-white hover:-translate-y-px",
          ],
          variant === "ghost" && [
            "text-muted-foreground",
            "hover:bg-white/[0.05] hover:text-[#d4d4ec]",
          ],
          variant === "outline" && [
            "border border-accent/28 text-accent-light",
            "hover:bg-accent/10 hover:border-accent/48 hover:-translate-y-px",
          ],
          variant === "danger" && [
            "bg-rose-500/10 text-rose-400 border border-rose-500/20",
            "hover:bg-rose-500/18 hover:border-rose-500/38 hover:text-rose-300",
          ],
          className,
        )}
        {...props}
      >
        {ripples.map(r => (
          <span
            key={r.id}
            className="absolute rounded-full pointer-events-none animate-ripple"
            style={{
              left: r.x,
              top: r.y,
              width: r.size,
              height: r.size,
              background: variant === "primary" ? "rgba(255,255,255,0.22)" : "rgba(255,255,255,0.10)",
            }}
          />
        ))}

        {loading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          icon && <span className="flex-shrink-0">{icon}</span>
        )}
        {children}
      </button>
    );
  },
);

ActionButton.displayName = "ActionButton";
export { ActionButton };
