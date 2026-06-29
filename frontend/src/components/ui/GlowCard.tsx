import { cn } from "@/lib/utils";
import { type HTMLAttributes, forwardRef } from "react";
import { GlassCard } from "./GlassCard";

export type GlowAccent = "blue" | "green" | "orange" | "pink" | "purple" | "none";

const ACCENT_STYLES: Record<GlowAccent, string> = {
  blue: "border-blue-500/25 shadow-glow-blue",
  green: "border-emerald-500/25 shadow-glow-green",
  orange: "border-orange-500/25 shadow-glow-orange",
  pink: "border-rose-500/25 shadow-glow-pink",
  purple: "border-violet-500/25 shadow-glow-purple",
  none: "",
};

interface GlowCardProps extends HTMLAttributes<HTMLDivElement> {
  accent?: GlowAccent;
  hoverable?: boolean;
  noPadding?: boolean;
  variant?: "default" | "strong" | "subtle";
}

const GlowCard = forwardRef<HTMLDivElement, GlowCardProps>(
  (
    {
      className,
      accent = "none",
      hoverable = false,
      noPadding = false,
      variant = "default",
      children,
      ...props
    },
    ref,
  ) => {
    return (
      <GlassCard
        ref={ref}
        variant={variant}
        hoverable={hoverable}
        noPadding={noPadding}
        className={cn(
          "backdrop-blur-lg",
          accent !== "none" && ACCENT_STYLES[accent],
          className,
        )}
        {...props}
      >
        {children}
      </GlassCard>
    );
  },
);

GlowCard.displayName = "GlowCard";
export { GlowCard };
