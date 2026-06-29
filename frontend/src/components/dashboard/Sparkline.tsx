interface SparklineProps {
  values: number[];
  color?: string;
  className?: string;
}

export function Sparkline({
  values,
  color = "#f43f5e",
  className,
}: SparklineProps) {
  const data = values.length ? values : [0, 0, 0, 0, 0];
  const max = Math.max(...data, 1);
  const w = 120;
  const h = 36;
  const step = w / Math.max(data.length - 1, 1);
  const points = data
    .map((v, i) => `${i * step},${h - (v / max) * (h - 4) - 2}`)
    .join(" ");

  return (
    <svg width={w} height={h} className={className} viewBox={`0 0 ${w} ${h}`}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        style={{ filter: `drop-shadow(0 0 6px ${color}88)` }}
      />
    </svg>
  );
}
