import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface AppScrollViewProps extends HTMLAttributes<HTMLDivElement> {
  horizontal?: boolean;
}

export const AppScrollView = forwardRef<HTMLDivElement, AppScrollViewProps>(
  ({ className, horizontal = false, children, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "overflow-auto",
        horizontal ? "overflow-y-hidden overflow-x-auto" : "overflow-x-hidden overflow-y-auto",
        "no-scrollbar",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  ),
);

AppScrollView.displayName = "AppScrollView";
