interface SectionLabelProps {
  children: React.ReactNode;
  hint?: string;
}

export function SectionLabel({ children, hint }: SectionLabelProps) {
  return (
    <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
      {children}
      {hint && <span className="normal-case font-normal opacity-50">— {hint}</span>}
    </h2>
  );
}
