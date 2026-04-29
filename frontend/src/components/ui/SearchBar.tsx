import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface SearchBarProps {
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
  onSearch?: (value: string) => void;
  className?: string;
}

export function SearchBar({
  value,
  placeholder = "검색...",
  onChange,
  onSearch,
  className,
}: SearchBarProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") onSearch?.(value);
    if (e.key === "Escape") onChange("");
  };

  return (
    <div className={cn("relative flex items-center", className)}>
      <Search className="absolute left-3 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onKeyDown={handleKeyDown}
        onChange={e => onChange(e.target.value)}
        className={cn(
          "w-full h-9 pl-9 pr-9 text-sm rounded-xl",
          "bg-bg-surface border border-white/[0.08] text-white placeholder:text-muted-foreground",
          "focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30",
          "transition-all duration-150",
        )}
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 text-muted-foreground hover:text-white transition-colors"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
