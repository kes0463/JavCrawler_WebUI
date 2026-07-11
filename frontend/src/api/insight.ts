import { get, post } from "./client";

/** 집계·추천 재계산은 라이브러리 규모에 따라 30초 이상 걸릴 수 있음 */
const INSIGHT_TIMEOUT_MS = 120_000;

export interface InsightStats {
  total: number;
  completed: number;
  completion_rate: number;
  avg_rating: number;
  rated_count: number;
  watched_count: number;
  total_watch_hours: number;
}

export interface InsightRankItem {
  name: string;
  score?: number;
  recent_score?: number;
  last_watched_at?: string;
}

export interface DistributionItem {
  name: string;
  count: number;
}

export interface DistributionBlock {
  actors: DistributionItem[];
  genres: DistributionItem[];
  makers: DistributionItem[];
}

export interface MonthlyAddition {
  month: string;
  label: string;
  count: number;
}

export interface WeeklyDigest {
  has_data?: boolean;
  week_label?: string;
  lines?: string[];
  empty_message?: string;
}

export interface WatchSummary {
  watched_count?: number;
  has_data?: boolean;
  top_genres?: { name: string; count: number; share_pct?: number }[];
  top_actors?: { name: string; count: number; share_pct?: number }[];
  scene_tags?: { tag?: string; count?: number }[];
  empty_message?: string;
}

export interface InsightTrends {
  watch_summary: WatchSummary;
  monthly_genre_trend: { month: string; genres: { name: string; count: number }[] }[];
  recent_trend: { actors?: InsightRankItem[]; genres?: InsightRankItem[] };
}

export interface RecommendItem {
  product_code: string;
  title_ko?: string;
  cover_path?: string;
  actors_ko?: string;
  rec_score?: number;
  source?: string;
  match_reasons?: string[];
  gem_type?: string;
  gap_score?: number;
}

export interface ActorCollectionRow {
  name: string;
  total: number;
  watched: number;
  remaining?: number;
  completion_rate?: number;
  unwatched?: number;
}

export interface ActorCollections {
  has_data?: boolean;
  actors?: ActorCollectionRow[];
}

export interface PipelineReport {
  total_events?: number;
  days?: number;
  error_events?: number;
  error_json_files?: number;
  by_event?: Record<string, number>;
  harvest_count?: number;
  analysis_count?: number;
  error_count?: number;
  avg_duration_min?: number;
}

export interface InsightOverview {
  stats: InsightStats;
  top_actors: InsightRankItem[];
  top_genres: InsightRankItem[];
  top_makers: InsightRankItem[];
  recent_trend: { actors?: InsightRankItem[]; genres?: InsightRankItem[] };
  weekly_digest: WeeklyDigest;
  pipeline: PipelineReport;
  monthly_genre_trend: { month: string; genres: { name: string; count: number }[] }[];
  monthly_additions: MonthlyAddition[];
  distribution: DistributionBlock;
}

export interface InsightRecommend {
  today_recs: RecommendItem[];
  next_watch: RecommendItem[];
  hidden_gems: RecommendItem[];
  favorite_actor_picks: RecommendItem[];
}

export interface InsightCollection {
  distribution: DistributionBlock;
  actor_collections: ActorCollections;
  pipeline: PipelineReport;
}

export const fetchInsightOverview = (force = false): Promise<InsightOverview> =>
  get(`/api/insight/overview${force ? "?force=true" : ""}`, INSIGHT_TIMEOUT_MS);

export const fetchInsightTrends = (): Promise<InsightTrends> =>
  get("/api/insight/trends", INSIGHT_TIMEOUT_MS);

export const fetchInsightRecommend = (force = false): Promise<InsightRecommend> =>
  get(`/api/insight/recommend${force ? "?force=true" : ""}`, INSIGHT_TIMEOUT_MS);

export const fetchInsightCollection = (force = false): Promise<InsightCollection> =>
  get(`/api/insight/collection${force ? "?force=true" : ""}`, INSIGHT_TIMEOUT_MS);

export const refreshInsight = (): Promise<InsightOverview> =>
  post("/api/insight/refresh", undefined, INSIGHT_TIMEOUT_MS);
