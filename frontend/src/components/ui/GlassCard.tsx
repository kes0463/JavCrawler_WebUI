import { cn } from "@/lib/utils";
import { type HTMLAttributes, forwardRef } from "react";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "strong" | "accent" | "subtle";
  hoverable?: boolean;
  noPadding?: boolean;
}

const GlassCard = forwardRef<HTMLDivElement, GlassCardProps>(
  ({ className, variant = "default", hoverable = false, noPadding = false, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "rounded-2xl transition-all duration-250 ease-spring",
          !noPadding && "p-5",
          variant === "default" && "glass",
          variant === "strong"  && "glass-strong",
          variant === "accent"  && "bg-accent-subtle border border-accent/20 shadow-accent",
          variant === "subtle"  && "bg-bg-surface/50 border border-white/[0.05]",
          hoverable && [
            "cursor-pointer gpu",
            "hover:border-white/[0.13] hover:shadow-hover hover:-translate-y-1",
            "active:translate-y-0 active:shadow-card",
          ],
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);

GlassCard.displayName = "GlassCard";
export { GlassCard };
