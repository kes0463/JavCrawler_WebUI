export function displayActressName(a: { name_ko?: string; name_ja?: string }) {
  return (a.name_ko || a.name_ja || "—").trim();
}

export function ageFromBirthDate(birthStr?: string): number {
  if (!birthStr) return -1;
  const s = birthStr.trim();
  if (s.length < 7 || s[4] !== "-") return -1;
  const y = parseInt(s.slice(0, 4), 10);
  const m = parseInt(s.slice(5, 7), 10);
  const d = s.length >= 10 ? parseInt(s.slice(8, 10), 10) : 1;
  if (Number.isNaN(y) || Number.isNaN(m) || Number.isNaN(d)) return -1;
  const today = new Date();
  let age = today.getFullYear() - y;
  const monthDiff = today.getMonth() + 1 - m;
  const dayDiff = today.getDate() - d;
  if (monthDiff < 0 || (monthDiff === 0 && dayDiff < 0)) age--;
  if (age < 0 || age > 150) return -1;
  return age;
}

export function formatAgeLabel(birthStr?: string): string {
  const age = ageFromBirthDate(birthStr);
  return age >= 0 ? `나이 ${age}세` : "";
}

export function normalizeCupSize(raw?: string): string {
  if (!raw) return "";
  let s = raw.trim().replace(/cup/gi, "").replace(/컵/g, "").trim();
  if (!s) return "";
  const ch = s.charAt(0);
  if (ch >= "a" && ch <= "z") return ch.toUpperCase();
  if (ch >= "A" && ch <= "Z") return ch;
  return "";
}

export function parseGenreTags(genres?: string, limit = 3): string[] {
  if (!genres) return [];
  return genres
    .split(",")
    .map(g => g.trim())
    .filter(Boolean)
    .slice(0, limit);
}

export function formatBodySpec(p: {
  height?: number;
  bust?: number;
  waist?: number;
  hip?: number;
  cup_size?: string;
}): string {
  return [
    p.height ? `${p.height}cm` : "",
    p.bust ? `B${p.bust}` : "",
    p.waist ? `W${p.waist}` : "",
    p.hip ? `H${p.hip}` : "",
    p.cup_size ? `${normalizeCupSize(p.cup_size) || p.cup_size}컵` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}
