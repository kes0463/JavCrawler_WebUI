import { useCallback, useEffect, useRef, useState } from "react";
import { Award, RefreshCw, Tag, TrendingUp } from "lucide-react";
import {
  fetchInsightCollection,
  fetchInsightOverview,
  fetchInsightRecommend,
  fetchInsightTrends,
  refreshInsight,
  type InsightCollection,
  type InsightOverview,
  type InsightRecommend,
  type InsightTrends,
} from "@/api/insight";
import { ActorCollectionCard } from "@/components/insight/ActorCollectionCard";
import { DistributionChart } from "@/components/insight/DistributionChart";
import { InsightKpiGrid } from "@/components/insight/InsightKpiGrid";
import { InsightRankingList } from "@/components/insight/InsightRankingList";
import { InsightTabBar, type InsightTabId } from "@/components/insight/InsightTabBar";
import { MonthlyAdditionsChart } from "@/components/insight/MonthlyAdditionsChart";
import { MonthlyGenreTrendChart } from "@/components/insight/MonthlyGenreTrendChart";
import { PipelineReportCard } from "@/components/insight/PipelineReportCard";
import { RecommendSection } from "@/components/insight/RecommendSection";
import { WatchTasteSummary } from "@/components/insight/WatchTasteSummary";
import { WeeklyDigestBanner } from "@/components/insight/WeeklyDigestBanner";
import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { useNavigation } from "@/contexts/NavigationContext";
import { usePlayer } from "@/contexts/PlayerContext";
import { useToast } from "@/contexts/ToastContext";

function mergeDistributionCounts(
  tasteItems: { name: string; score?: number }[],
  distItems: { name: string; count: number }[],
): { name: string; score?: number; count?: number }[] {
  if (!tasteItems.length) {
    return distItems.slice(0, 8).map(d => ({ name: d.name, count: d.count }));
  }
  const countMap = new Map(distItems.map(d => [d.name, d.count]));
  return tasteItems.map(t => ({
    ...t,
    count: countMap.get(t.name),
  }));
}

function trendSummary(trend: { actors?: { name: string; recent_score?: number }[]; genres?: { name: string; recent_score?: number }[] }) {
  const parts: string[] = [];
  const a = trend.actors?.[0];
  const g = trend.genres?.[0];
  if (a?.name) parts.push(`배우 ${a.name} (${a.recent_score ?? 0}점)`);
  if (g?.name) parts.push(`장르 ${g.name} (${g.recent_score ?? 0}점)`);
  return parts.length ? `최근 7일: ${parts.join(" · ")}` : "최근 7일 시청 데이터 없음";
}

export default function InsightView() {
  const { openLibraryDetail } = useNavigation();
  const { openPlayer } = usePlayer();
  const { showToast } = useToast();

  const [tab, setTab] = useState<InsightTabId>("overview");
  const [overview, setOverview] = useState<InsightOverview | null>(null);
  const [trends, setTrends] = useState<InsightTrends | null>(null);
  const [recommend, setRecommend] = useState<InsightRecommend | null>(null);
  const [collection, setCollection] = useState<InsightCollection | null>(null);
  const [loadingOverview, setLoadingOverview] = useState(true);
  const [loadingTab, setLoadingTab] = useState<InsightTabId | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedTabs, setLoadedTabs] = useState<Set<InsightTabId>>(() => new Set(["overview"]));
  const recommendFetchRef = useRef<Promise<InsightRecommend | null> | null>(null);
  const recommendReadyRef = useRef(false);
  const recommendPrefetchStartedRef = useRef(false);

  const loadOverview = useCallback(async (force = false) => {
    setLoadingOverview(true);
    setError(null);
    try {
      const data = force ? await refreshInsight() : await fetchInsightOverview(force);
      setOverview(data);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "인사이트를 불러오지 못했습니다";
      setError(msg);
      setOverview(null);
    } finally {
      setLoadingOverview(false);
    }
  }, []);

  const loadRecommend = useCallback(async (showLoading: boolean, force = false) => {
    if (!force && recommendReadyRef.current) return null;
    if (!force && recommendFetchRef.current) {
      if (showLoading) setLoadingTab("recommend");
      try {
        return await recommendFetchRef.current;
      } finally {
        if (showLoading) setLoadingTab(null);
      }
    }
    if (showLoading) setLoadingTab("recommend");
    const task = (async () => {
      try {
        const data = await fetchInsightRecommend(force);
        setRecommend(data);
        recommendReadyRef.current = true;
        setLoadedTabs(prev => new Set(prev).add("recommend"));
        setError(null);
        return data;
      } catch (e) {
        if (showLoading) {
          setError(e instanceof Error ? e.message : "추천 데이터 로드 실패");
        }
        return null;
      } finally {
        recommendFetchRef.current = null;
        if (showLoading) setLoadingTab(null);
      }
    })();
    recommendFetchRef.current = task;
    return task;
  }, []);

  const loadTab = useCallback(async (tabId: InsightTabId, force = false) => {
    if (tabId === "overview") return;
    if (tabId === "recommend") {
      await loadRecommend(true, force);
      return;
    }
    setLoadingTab(tabId);
    try {
      if (tabId === "trends") {
        setTrends(await fetchInsightTrends());
      } else if (tabId === "collection") {
        setCollection(await fetchInsightCollection(force));
      }
      setLoadedTabs(prev => new Set(prev).add(tabId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "탭 데이터 로드 실패");
    } finally {
      setLoadingTab(null);
    }
  }, [loadRecommend]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (recommendPrefetchStartedRef.current) return;
    recommendPrefetchStartedRef.current = true;
    void loadRecommend(false);
  }, [loadRecommend]);

  useEffect(() => {
    if (tab !== "overview" && tab !== "recommend" && !loadedTabs.has(tab)) {
      void loadTab(tab);
    }
    if (tab === "recommend" && !recommendReadyRef.current) {
      void loadRecommend(true);
    }
  }, [tab, loadedTabs, loadTab, loadRecommend]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const data = await refreshInsight();
      setOverview(data);
      setLoadedTabs(new Set(["overview"]));
      setTrends(null);
      setRecommend(null);
      setCollection(null);
      recommendFetchRef.current = null;
      recommendReadyRef.current = false;
      recommendPrefetchStartedRef.current = false;
      setError(null);
      if (tab !== "overview") {
        await loadTab(tab, true);
      } else {
        recommendPrefetchStartedRef.current = true;
        void loadRecommend(false, true);
      }
      showToast("인사이트 데이터를 갱신했습니다.", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "갱신 실패", "error");
    } finally {
      setRefreshing(false);
    }
  };

  const handleOpen = (code: string) => openLibraryDetail(code.trim().toUpperCase());
  const handlePlay = (code: string) => void openPlayer(code.trim().toUpperCase());

  const dist = overview?.distribution;
  const genreRows = mergeDistributionCounts(overview?.top_genres ?? [], dist?.genres ?? []);
  const hasTasteActors = (overview?.top_actors ?? []).length > 0;
  const actorRows = hasTasteActors
    ? (overview?.top_actors ?? []).map(a => ({ name: a.name, score: a.score }))
    : (dist?.actors ?? []).slice(0, 5).map(a => ({ name: a.name, count: a.count }));
  const makerRows = mergeDistributionCounts(overview?.top_makers ?? [], dist?.makers ?? []);
  const hasTasteGenres = (overview?.top_genres ?? []).length > 0;
  const hasTasteMakers = (overview?.top_makers ?? []).length > 0;

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">인사이트</h1>
          <p className="text-base text-muted-foreground mt-0.5">라이브러리 분석 · 취향 · 추천</p>
        </div>
        <button
          type="button"
          disabled={refreshing || loadingOverview}
          onClick={() => void handleRefresh()}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-white/10 text-sm text-slate-300 hover:bg-white/[0.04] disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          새로고침
        </button>
      </div>

      <InsightTabBar active={tab} onChange={setTab} />

      {error && (
        <GlassCard className="border-rose-500/30 space-y-3">
          <p className="text-sm text-rose-300">{error}</p>
          <button
            type="button"
            onClick={() => void (tab === "overview" ? loadOverview() : loadTab(tab))}
            className="text-sm text-rose-200 underline underline-offset-2"
          >
            다시 시도
          </button>
        </GlassCard>
      )}

      {tab === "overview" && (
        loadingOverview && !overview ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-28 rounded-xl" />)}
          </div>
        ) : overview ? (
          <div className="space-y-4">
            <WeeklyDigestBanner digest={overview.weekly_digest ?? {}} />
            <InsightKpiGrid stats={overview.stats ?? { total: 0 }} distribution={overview.distribution} />
            {overview.recent_trend && (
              <p className="text-sm text-slate-400 px-1">{trendSummary(overview.recent_trend)}</p>
            )}
            <MonthlyAdditionsChart items={overview.monthly_additions ?? []} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <InsightRankingList
                title={hasTasteGenres ? "장르 TOP (취향)" : "장르 TOP (보유)"}
                icon={<Tag className="w-5 h-5 text-muted-foreground" />}
                items={genreRows}
                showCount={!hasTasteGenres}
              />
              <InsightRankingList
                title={hasTasteActors ? "배우 TOP (취향)" : "배우 TOP (보유)"}
                icon={<Award className="w-5 h-5 text-muted-foreground" />}
                items={actorRows}
                showCount={!hasTasteActors}
              />
            </div>
            <InsightRankingList
              title="제작사 TOP"
              icon={<TrendingUp className="w-5 h-5 text-muted-foreground" />}
              items={makerRows}
              showCount={!hasTasteMakers}
              maxItems={5}
            />
            <PipelineReportCard report={overview.pipeline ?? {}} />
          </div>
        ) : !loadingOverview && !error ? (
          <GlassCard>
            <p className="text-sm text-slate-500 text-center py-8">데이터를 불러오지 못했습니다.</p>
          </GlassCard>
        ) : null
      )}

      {tab === "trends" && (
        loadingTab === "trends" && !trends ? (
          <Skeleton className="h-64 rounded-xl" />
        ) : trends ? (
          <div className="space-y-4">
            <p className="text-sm text-slate-400">{trendSummary(trends.recent_trend ?? {})}</p>
            <WatchTasteSummary summary={trends.watch_summary ?? { has_data: false }} />
            <MonthlyGenreTrendChart items={trends.monthly_genre_trend ?? []} />
          </div>
        ) : null
      )}

      {tab === "recommend" && (
        loadingTab === "recommend" && !recommend ? (
          <div className="grid grid-cols-3 gap-4">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="aspect-square rounded-xl" />
            ))}
          </div>
        ) : recommend ? (
          <RecommendSection
            next_watch={recommend.next_watch}
            hidden_gems={recommend.hidden_gems}
            today_recs={recommend.today_recs}
            favorite_actor_picks={recommend.favorite_actor_picks}
            onOpen={handleOpen}
            onPlay={handlePlay}
          />
        ) : null
      )}

      {tab === "collection" && (
        loadingTab === "collection" && !collection ? (
          <Skeleton className="h-64 rounded-xl" />
        ) : collection ? (
          <div className="space-y-4">
            <DistributionChart distribution={collection.distribution} />
            <ActorCollectionCard data={collection.actor_collections} />
            <PipelineReportCard report={collection.pipeline} />
          </div>
        ) : null
      )}
    </div>
  );
}
