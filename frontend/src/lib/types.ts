export interface Stats {
  total: number;
  completed: number;
  inProgress: number;
  pending: number;
  avgRating: number;
  totalSizeTb: number;
}

export interface LibraryItem {
  id: number;
  code: string;
  titleKo: string;
  titleJa: string;
  actors: string[];
  genres: string[];
  rating: number;
  duration: number;
  releaseDate: string;
  hasVideo: boolean;
  coverPath: string | null;
}

export type QueueStatus = "processing" | "pending" | "completed";

export interface QueueItem {
  code: string;
  title: string;
  status: QueueStatus;
  progress: number;
}

export interface Queue {
  id: string;
  label: string;
  color: string;
  items: QueueItem[];
}
