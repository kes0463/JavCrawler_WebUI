import type { Stats, LibraryItem, Queue } from "./types";

export const mockStats: Stats = {
  total: 1284,
  completed: 847,
  inProgress: 112,
  pending: 325,
  avgRating: 3.7,
  totalSizeTb: 2.3,
};

export const mockActors = [
  { name: "葵つかさ",     score: 92, recentScore: 88 },
  { name: "三上悠亜",     score: 87, recentScore: 91 },
  { name: "明日花キララ", score: 84, recentScore: 79 },
  { name: "天使もえ",     score: 81, recentScore: 83 },
  { name: "星宮一花",     score: 76, recentScore: 80 },
];

export const mockGenres = [
  { name: "単体作品",   score: 95 },
  { name: "美少女",     score: 88 },
  { name: "巨乳",       score: 82 },
  { name: "中出し",     score: 78 },
  { name: "スレンダー", score: 71 },
  { name: "フェラ",     score: 65 },
  { name: "手コキ",     score: 58 },
  { name: "OL",         score: 52 },
];

export const mockRecentActivity = [
  { code: "STARS-001", title: "サンプルタイトル 1", status: "completed",  date: "2024-01-15" },
  { code: "IPX-002",   title: "サンプルタイトル 2", status: "processing", date: "2024-01-14" },
  { code: "MIDE-003",  title: "サンプルタイトル 3", status: "completed",  date: "2024-01-13" },
  { code: "SSIS-004",  title: "サンプルタイトル 4", status: "pending",    date: "2024-01-12" },
  { code: "ABW-005",   title: "サンプルタイトル 5", status: "completed",  date: "2024-01-11" },
];

export const mockLibrary: LibraryItem[] = Array.from({ length: 48 }, (_, i) => ({
  id: i + 1,
  code: `STARS-${String(i + 1).padStart(3, "0")}`,
  titleKo: `샘플 타이틀 ${i + 1}`,
  titleJa: `サンプルタイトル ${i + 1}`,
  actors: ["葵つかさ", "三上悠亜"].slice(0, (i % 2) + 1),
  genres: ["単体作品", "美少女", "巨乳"].slice(0, (i % 3) + 1),
  // deterministic values — avoid Math.random() which changes on every hot reload
  rating: parseFloat((3 + (i % 20) / 10).toFixed(1)),
  duration: 6000 + (i * 317 + 500) % 3600,
  releaseDate: `2024-0${(i % 9) + 1}-${String((i % 28) + 1).padStart(2, "0")}`,
  hasVideo: i % 3 !== 0,
  coverPath: null,
}));

export const mockQueue: Queue[] = [
  {
    id: "q1",
    label: "하이라이트 큐",
    color: "#f59e0b",
    items: [
      { code: "STARS-101", title: "Sample Title A", status: "processing", progress: 62 },
      { code: "IPX-202",   title: "Sample Title B", status: "pending",    progress: 0  },
      { code: "MIDE-303",  title: "Sample Title C", status: "pending",    progress: 0  },
    ],
  },
  {
    id: "q2",
    label: "미리보기 큐",
    color: "#6366f1",
    items: [
      { code: "SSIS-404", title: "Sample Title D", status: "pending", progress: 0 },
      { code: "ABW-505",  title: "Sample Title E", status: "pending", progress: 0 },
    ],
  },
  {
    id: "q3",
    label: "모자이크 제거 큐",
    color: "#10b981",
    items: [
      { code: "STARS-606", title: "Sample Title F", status: "pending", progress: 0 },
    ],
  },
];

export const mockMonthlyGenres = [
  { month: "2023-11", genres: [{ name: "単体作品", count: 12 }, { name: "巨乳", count: 8 }, { name: "美少女", count: 6 }] },
  { month: "2023-12", genres: [{ name: "単体作品", count: 15 }, { name: "スレンダー", count: 9 }, { name: "中出し", count: 7 }] },
  { month: "2024-01", genres: [{ name: "単体作品", count: 11 }, { name: "美少女", count: 10 }, { name: "OL", count: 5 }] },
];
