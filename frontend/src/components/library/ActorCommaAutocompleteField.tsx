import { useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { searchActresses } from "@/api/actress";

export interface ActressSuggestion {
  id: number;
  name_ko: string;
  name_ja: string;
}

function splitCommaField(value: string): { committed: string[]; current: string } {
  const lastComma = value.lastIndexOf(",");
  if (lastComma < 0) {
    return { committed: [], current: value };
  }
  const before = value.slice(0, lastComma);
  const committed = before
    .split(",")
    .map(s => s.trim())
    .filter(Boolean);
  return { committed, current: value.slice(lastComma + 1) };
}

function joinCommaField(committed: string[], current: string): string {
  if (committed.length === 0) return current;
  if (!current.trim()) return committed.join(", ");
  return `${committed.join(", ")}, ${current}`;
}

function applyActressSelection(
  koValue: string,
  jaValue: string,
  pick: Pick<ActressSuggestion, "name_ko" | "name_ja">,
): { actors_ko: string; actors_ja: string } {
  const ko = splitCommaField(koValue);
  const ja = splitCommaField(jaValue);
  const nextKoCommitted = [...ko.committed, pick.name_ko.trim()].filter(Boolean);
  const nextJaCommitted = [...ja.committed];
  while (nextJaCommitted.length < nextKoCommitted.length) {
    nextJaCommitted.push("");
  }
  nextJaCommitted[nextKoCommitted.length - 1] = pick.name_ja.trim();
  return {
    actors_ko: joinCommaField(nextKoCommitted, ""),
    actors_ja: joinCommaField(nextJaCommitted, ja.current),
  };
}

interface ActorCommaAutocompleteFieldProps {
  label: string;
  actorsKo: string;
  actorsJa: string;
  onChange: (patch: { actors_ko: string; actors_ja: string }) => void;
}

export function ActorCommaAutocompleteField({
  label,
  actorsKo,
  actorsJa,
  onChange,
}: ActorCommaAutocompleteFieldProps) {
  const listId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ActressSuggestion[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  const { current } = splitCommaField(actorsKo);
  const query = current.trim();

  useEffect(() => {
    if (!open || query.length < 1) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = window.setTimeout(() => {
      searchActresses(query)
        .then(rows => {
          setItems(rows);
          setActiveIndex(0);
        })
        .catch(() => setItems([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [open, query]);

  useEffect(() => {
    const onDocDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, []);

  const pick = (item: ActressSuggestion) => {
    onChange(applyActressSelection(actorsKo, actorsJa, item));
    setOpen(false);
    inputRef.current?.focus();
  };

  const showList = open && query.length >= 1 && (loading || items.length > 0);

  return (
    <div ref={wrapRef} className="relative block">
      <label className="block">
        <span className="text-slate-400 text-base mb-1 block">{label}</span>
        <input
          ref={inputRef}
          type="text"
          value={actorsKo}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          onChange={e => {
            onChange({ actors_ko: e.target.value, actors_ja: actorsJa });
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={e => {
            if (!showList) return;
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActiveIndex(i => Math.min(i + 1, Math.max(items.length - 1, 0)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActiveIndex(i => Math.max(i - 1, 0));
            } else if (e.key === "Enter" && items[activeIndex]) {
              e.preventDefault();
              pick(items[activeIndex]);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          placeholder="이름 입력 후 자동완성 (쉼표로 여러 명)"
          className="w-full rounded-lg bg-white/[0.06] border border-white/[0.12] px-3 py-2 text-lg text-[#ececf4] focus:outline-none focus:border-violet-400/50"
        />
      </label>

      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 left-0 right-0 mt-1 max-h-56 overflow-y-auto rounded-lg border border-white/[0.12] bg-[#12121c] shadow-xl py-1"
        >
          {loading && items.length === 0 && (
            <li className="px-3 py-2 text-sm text-slate-500">검색 중…</li>
          )}
          {items.map((item, idx) => (
            <li key={item.id} role="option" aria-selected={idx === activeIndex}>
              <button
                type="button"
                onMouseDown={e => e.preventDefault()}
                onClick={() => pick(item)}
                className={cn(
                  "w-full text-left px-3 py-2 text-sm transition-colors",
                  idx === activeIndex
                    ? "bg-violet-500/25 text-violet-100"
                    : "text-slate-200 hover:bg-white/[0.06]",
                )}
              >
                <span className="font-medium">{item.name_ko || item.name_ja}</span>
                {item.name_ko && item.name_ja && (
                  <span className="text-slate-400 ml-2">{item.name_ja}</span>
                )}
              </button>
            </li>
          ))}
          {!loading && items.length === 0 && (
            <li className="px-3 py-2 text-sm text-slate-500">검색 결과 없음</li>
          )}
        </ul>
      )}
    </div>
  );
}
