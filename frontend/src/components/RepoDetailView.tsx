import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  AnalysisJob,
  Commit,
  DuplicateIssuePair,
  IndexJob,
  Issue,
  IssueAnalysis,
  PRAnalysis,
  PullRequest,
  Repository,
  SearchMode,
  SearchResultItem,
  SyncJob,
} from "../types";

import { AskTab } from "./AskTab";
import { DocsTab } from "./DocsTab";
import { TestsTab } from "./TestsTab";

const isTerminalStatus = (status?: string | null, stage?: string | null): boolean => {
  if (!status && !stage) return false;
  const s = status ? status.toLowerCase() : "";
  const st = stage ? stage.toLowerCase() : "";
  return (
    ["completed", "ready", "done", "failed"].includes(s) ||
    ["completed", "failed"].includes(st)
  );
};

interface RepoDetailViewProps {
  repo: Repository;
  onBack: () => void;
  onResync: (repoId: string) => void;
}

type TabType = "commits" | "pulls" | "issues" | "search" | "ask" | "docs" | "tests";

export const RepoDetailView: React.FC<RepoDetailViewProps> = ({
  repo,
  onBack,
  onResync,
}) => {
  const [currentRepo, setCurrentRepo] = useState<Repository>(repo);
  const [activeTab, setActiveTab] = useState<TabType>("commits");
  const [syncJob, setSyncJob] = useState<SyncJob | null>(null);
  const [isTriggeringSync, setIsTriggeringSync] = useState<boolean>(false);

  // Indexing State
  const [indexJob, setIndexJob] = useState<IndexJob | null>(null);
  const [isTriggeringIndex, setIsTriggeringIndex] = useState<boolean>(false);
  const [indexError, setIndexError] = useState<string | null>(null);

  // Search State
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchMode] = useState<SearchMode>("hybrid");
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searchLoading, setSearchLoading] = useState<boolean>(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState<boolean>(false);

  // Commits State
  const [commits, setCommits] = useState<Commit[]>([]);
  const [commitsLoading, setCommitsLoading] = useState<boolean>(false);
  const [commitAuthorFilter, setCommitAuthorFilter] = useState<string>("");

  // PRs State
  const [prs, setPrs] = useState<PullRequest[]>([]);
  const [prsLoading, setPrsLoading] = useState<boolean>(false);
  const [prStateFilter, setPrStateFilter] = useState<string>("all");
  const [prAuthorFilter, setPrAuthorFilter] = useState<string>("");
  const [prAnalyses, setPrAnalyses] = useState<Record<number, PRAnalysis>>({});
  const [prAnalyzing, setPrAnalyzing] = useState<Record<number, boolean>>({});
  const [prErrors, setPrErrors] = useState<Record<number, string | null>>({});
  const [expandedPrs, setExpandedPrs] = useState<Record<number, boolean>>({});
  const [prRiskFilter, setPrRiskFilter] = useState<string>("all");

  // Issues State
  const [issues, setIssues] = useState<Issue[]>([]);
  const [issuesLoading, setIssuesLoading] = useState<boolean>(false);
  const [issueStateFilter, setIssueStateFilter] = useState<string>("all");
  const [issueAuthorFilter, setIssueAuthorFilter] = useState<string>("");
  const [issueAnalyses, setIssueAnalyses] = useState<Record<number, IssueAnalysis>>({});
  const [issueTypeFilter, setIssueTypeFilter] = useState<string>("all");
  const [duplicates, setDuplicates] = useState<DuplicateIssuePair[]>([]);
  const [duplicatesLoading, setDuplicatesLoading] = useState<boolean>(false);
  const [issueJob, setIssueJob] = useState<AnalysisJob | null>(null);
  const [isTriggeringIssueAnalysis, setIsTriggeringIssueAnalysis] = useState<boolean>(false);
  const [issueAnalysisError, setIssueAnalysisError] = useState<string | null>(null);

  useEffect(() => {
    setCurrentRepo(repo);
  }, [repo]);

  const refetchRepo = async () => {
    try {
      const res = await fetch(`/repos/${repo.id}`);
      if (res.ok) {
        const data: Repository = await res.json();
        setCurrentRepo(data);
      }
    } catch (err) {
      console.error("Failed to refetch repository:", err);
    }
  };

  // Fetch sync status if repo is pending or syncing, and stop on terminal state
  useEffect(() => {
    let timer: any = null;
    let isCancelled = false;

    const fetchStatus = async () => {
      try {
        const res = await fetch(`/repos/${repo.id}/sync-status`);
        if (res.ok && !isCancelled) {
          const data: SyncJob = await res.json();
          setSyncJob(data);

          if (isTerminalStatus(data.status, data.stage)) {
            if (timer) clearInterval(timer);
            await refetchRepo();
          }
        }
      } catch (err) {
        console.error("Failed to load sync status:", err);
      }
    };

    fetchStatus();

    const isSyncActive =
      (currentRepo.status === "syncing" || currentRepo.status === "pending" || syncJob?.status === "running") &&
      !isTerminalStatus(syncJob?.status, syncJob?.stage) &&
      currentRepo.status !== "failed" &&
      syncJob?.status !== "failed";

    if (isSyncActive) {
      timer = setInterval(fetchStatus, 2500);
    }

    return () => {
      isCancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [repo.id, currentRepo.status, syncJob?.status, syncJob?.stage]);

  // Fetch and poll index status if indexing is active
  useEffect(() => {
    let timer: any = null;
    let isCancelled = false;

    const fetchIndexStatus = async () => {
      try {
        const res = await fetch(`/repos/${currentRepo.id}/index-status`);
        if (res.ok && !isCancelled) {
          const data: IndexJob = await res.json();
          setIndexJob(data);
          if (data.status === "completed") {
            if (timer) clearInterval(timer);
            setCurrentRepo((prev) => ({
              ...prev,
              index_status: "ready",
              chunk_count: data.stats?.total_chunks ?? prev.chunk_count,
            }));
            await refetchRepo();
          } else if (data.status === "failed") {
            if (timer) clearInterval(timer);
            setCurrentRepo((prev) => ({
              ...prev,
              index_status: "failed",
            }));
            setIndexError(data.error || "Indexing failed");
            await refetchRepo();
          }
        }
      } catch (err) {
        console.error("Failed to load index status:", err);
      }
    };

    fetchIndexStatus();

    const isIndexActive =
      (currentRepo.index_status === "indexing" || (indexJob && indexJob.status === "running")) &&
      !isTerminalStatus(indexJob?.status, indexJob?.stage) &&
      currentRepo.index_status !== "failed" &&
      indexJob?.status !== "failed";

    if (isIndexActive) {
      timer = setInterval(fetchIndexStatus, 2000);
    }

    return () => {
      isCancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [currentRepo.id, currentRepo.index_status, indexJob?.status, indexJob?.stage]);

  const handleTriggerSync = async () => {
    if (isTriggeringSync) return;
    setIsTriggeringSync(true);
    try {
      const res = await fetch(`/repos/${currentRepo.id}/sync`, { method: "POST" });
      if (res.ok) {
        const data: SyncJob = await res.json();
        setSyncJob(data);
        setCurrentRepo((prev) => ({ ...prev, status: "pending", sync_error: null }));
        onResync(currentRepo.id);
      } else if (res.status === 409) {
        setCurrentRepo((prev) => ({ ...prev, status: "pending" }));
      } else {
        const errData = await res.json().catch(() => ({}));
        console.error("Failed to trigger re-sync:", errData.detail || res.statusText);
      }
    } catch (err) {
      console.error("Failed to trigger re-sync:", err);
    } finally {
      setIsTriggeringSync(false);
    }
  };

  const handleTriggerIndex = async () => {
    setIsTriggeringIndex(true);
    setIndexError(null);
    try {
      const res = await fetch(`/repos/${currentRepo.id}/index`, { method: "POST" });
      if (res.ok) {
        const data: IndexJob = await res.json();
        setIndexJob(data);
        setCurrentRepo((prev) => ({ ...prev, index_status: "indexing" }));
      } else if (res.status === 409) {
        setCurrentRepo((prev) => ({ ...prev, index_status: "indexing" }));
      } else {
        const errData = await res.json().catch(() => ({}));
        setIndexError(errData.detail || `Failed to trigger indexing (${res.status})`);
      }
    } catch (err: any) {
      setIndexError(err.message || "Failed to trigger indexing");
    } finally {
      setIsTriggeringIndex(false);
    }
  };

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;

    setSearchLoading(true);
    setSearchError(null);
    setHasSearched(true);
    try {
      const res = await fetch(`/repos/${currentRepo.id}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, mode: searchMode, limit: 15 }),
      });
      if (res.ok) {
        const data: SearchResultItem[] = await res.json();
        setSearchResults(data);
      } else if (res.status === 409) {
        setSearchError("Codebase has not been indexed yet. Please index before searching.");
      } else {
        const errData = await res.json().catch(() => ({}));
        setSearchError(errData.detail || `Search failed (${res.status})`);
      }
    } catch (err: any) {
      setSearchError(err.message || "Failed to execute search");
    } finally {
      setSearchLoading(false);
    }
  };

  // Load Commits
  useEffect(() => {
    if (activeTab !== "commits") return;

    const fetchCommits = async () => {
      setCommitsLoading(true);
      try {
        let url = `/repos/${repo.id}/commits?limit=50`;
        if (commitAuthorFilter) {
          url += `&author=${encodeURIComponent(commitAuthorFilter)}`;
        }
        const res = await fetch(url);
        if (res.ok) {
          const data: Commit[] = await res.json();
          setCommits(data);
        }
      } catch (err) {
        console.error("Failed to fetch commits:", err);
      } finally {
        setCommitsLoading(false);
      }
    };

    fetchCommits();
  }, [repo.id, activeTab, commitAuthorFilter, currentRepo.last_synced_at]);

  // Load Pull Requests
  useEffect(() => {
    if (activeTab !== "pulls") return;

    const fetchPrs = async () => {
      setPrsLoading(true);
      try {
        let url = `/repos/${repo.id}/pulls?limit=50&state=${prStateFilter}`;
        if (prAuthorFilter) {
          url += `&author=${encodeURIComponent(prAuthorFilter)}`;
        }
        const res = await fetch(url);
        if (res.ok) {
          const data: PullRequest[] = await res.json();
          setPrs(data);
        }
      } catch (err) {
        console.error("Failed to fetch PRs:", err);
      } finally {
        setPrsLoading(false);
      }
    };

    fetchPrs();
  }, [repo.id, activeTab, prStateFilter, prAuthorFilter, currentRepo.last_synced_at]);

  // Fetch PR analyses for cached risk & summary reviews
  const fetchPrAnalyses = async () => {
    try {
      const res = await fetch(`/repos/${repo.id}/pulls/analyses`);
      if (res.ok) {
        const data: PRAnalysis[] = await res.json();
        const map: Record<number, PRAnalysis> = {};
        for (const item of data) {
          map[item.pr_number] = item;
        }
        setPrAnalyses(map);
      }
    } catch (err) {
      console.error("Failed to load PR analyses:", err);
    }
  };

  useEffect(() => {
    if (activeTab === "pulls") {
      fetchPrAnalyses();
    }
  }, [repo.id, activeTab]);

  const handleAnalyzePr = async (prNumber: number, refresh: boolean = false) => {
    setPrAnalyzing((prev) => ({ ...prev, [prNumber]: true }));
    setPrErrors((prev) => ({ ...prev, [prNumber]: null }));
    try {
      const res = await fetch(`/repos/${repo.id}/pulls/${prNumber}/analyze?refresh=${refresh}`, {
        method: "POST",
      });
      if (res.status === 429) {
        setPrErrors((prev) => ({
          ...prev,
          [prNumber]: "Rate limit exceeded. Please wait a moment before analyzing again.",
        }));
        return;
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        setPrErrors((prev) => ({
          ...prev,
          [prNumber]: errData.detail || `Analysis failed (${res.status})`,
        }));
        return;
      }
      const data: PRAnalysis = await res.json();
      setPrAnalyses((prev) => ({ ...prev, [prNumber]: data }));
      setExpandedPrs((prev) => ({ ...prev, [prNumber]: true }));
    } catch (err: any) {
      setPrErrors((prev) => ({
        ...prev,
        [prNumber]: err.message || "Failed to analyze PR",
      }));
    } finally {
      setPrAnalyzing((prev) => ({ ...prev, [prNumber]: false }));
    }
  };

  const toggleExpandPr = (prNumber: number) => {
    setExpandedPrs((prev) => ({ ...prev, [prNumber]: !prev[prNumber] }));
  };

  // Load Issues
  useEffect(() => {
    if (activeTab !== "issues") return;

    const fetchIssues = async () => {
      setIssuesLoading(true);
      try {
        let url = `/repos/${repo.id}/issues?limit=50&state=${issueStateFilter}`;
        if (issueAuthorFilter) {
          url += `&author=${encodeURIComponent(issueAuthorFilter)}`;
        }
        const res = await fetch(url);
        if (res.ok) {
          const data: Issue[] = await res.json();
          setIssues(data);
        }
      } catch (err) {
        console.error("Failed to fetch issues:", err);
      } finally {
        setIssuesLoading(false);
      }
    };

    fetchIssues();
  }, [repo.id, activeTab, issueStateFilter, issueAuthorFilter, currentRepo.last_synced_at]);

  // Fetch Issue Analyses & Duplicates
  const fetchIssueAnalyses = async () => {
    try {
      let url = `/repos/${repo.id}/issues/analysis`;
      if (issueTypeFilter !== "all") {
        url += `?issue_type=${encodeURIComponent(issueTypeFilter)}`;
      }
      const res = await fetch(url);
      if (res.ok) {
        const data: IssueAnalysis[] = await res.json();
        const map: Record<number, IssueAnalysis> = {};
        for (const item of data) {
          map[item.issue_number] = item;
        }
        setIssueAnalyses(map);
      }
    } catch (err) {
      console.error("Failed to load issue analyses:", err);
    }
  };

  const fetchDuplicates = async () => {
    setDuplicatesLoading(true);
    try {
      const res = await fetch(`/repos/${repo.id}/issues/duplicates?limit=50`);
      if (res.ok) {
        const data: DuplicateIssuePair[] = await res.json();
        setDuplicates(data);
      }
    } catch (err) {
      console.error("Failed to load duplicate issues:", err);
    } finally {
      setDuplicatesLoading(false);
    }
  };

  const checkIssueJobStatus = async () => {
    try {
      const res = await fetch(`/repos/${repo.id}/issues/analysis-status`);
      if (res.ok) {
        const data: AnalysisJob = await res.json();
        setIssueJob(data);
        return data;
      }
    } catch (err) {
      console.error("Failed to check issue analysis status:", err);
    }
    return null;
  };

  useEffect(() => {
    if (activeTab === "issues") {
      fetchIssueAnalyses();
      fetchDuplicates();
      checkIssueJobStatus();
    }
  }, [repo.id, activeTab, issueTypeFilter]);

  // Polling for issue analysis job
  useEffect(() => {
    let timer: any = null;
    let isCancelled = false;

    const isRunning =
      (issueJob?.status === "running" || issueJob?.status === "pending") &&
      !isTerminalStatus(issueJob?.status, issueJob?.stage);

    if (isRunning) {
      timer = setInterval(async () => {
        try {
          const res = await fetch(`/repos/${repo.id}/issues/analysis-status`);
          if (res.ok && !isCancelled) {
            const data: AnalysisJob = await res.json();
            setIssueJob(data);
            if (data.status === "ready" || data.status === "failed") {
              if (timer) clearInterval(timer);
              if (data.status === "failed") {
                setIssueAnalysisError(data.error || "Issue analysis job failed.");
              } else {
                setIssueAnalysisError(null);
                await fetchIssueAnalyses();
                await fetchDuplicates();
              }
            }
          }
        } catch (err) {
          console.error("Polling issue analysis status failed:", err);
        }
      }, 2000);
    }

    return () => {
      isCancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [repo.id, issueJob?.status, issueJob?.stage]);

  const handleTriggerIssueAnalysis = async () => {
    setIsTriggeringIssueAnalysis(true);
    setIssueAnalysisError(null);
    try {
      const res = await fetch(`/repos/${repo.id}/issues/analyze`, { method: "POST" });
      if (res.status === 409) {
        const errData = await res.json().catch(() => ({}));
        setIssueAnalysisError(errData.detail || "Analysis already in progress or no synced issues.");
        await checkIssueJobStatus();
        return;
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        setIssueAnalysisError(errData.detail || `Failed to start issue analysis (${res.status})`);
        return;
      }
      const data = await res.json();
      setIssueJob({
        id: data.job_id,
        repo_id: repo.id,
        kind: "issues",
        status: "pending",
        stage: "queued",
        progress: 0,
        error: null,
        started_at: null,
        finished_at: null,
      });
    } catch (err: any) {
      setIssueAnalysisError(err.message || "Failed to trigger issue analysis");
    } finally {
      setIsTriggeringIssueAnalysis(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      {/* Top Header Bar */}
      <div
        className="glass-card"
        style={{
          padding: "1.75rem 2rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "1.25rem",
        }}
      >
        <div>
          <button
            onClick={onBack}
            className="btn btn-outline"
            style={{
              padding: "0.35rem 0.75rem",
              fontSize: "0.8rem",
              marginBottom: "0.85rem",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.4rem",
            }}
          >
            ← Back to Repositories
          </button>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>{repo.full_name}</h1>
            {repo.is_private ? (
              <span className="badge badge-warning">Private</span>
            ) : (
              <span className="badge badge-success">Public</span>
            )}
            {/* Sync Status Badge */}
            {(() => {
              const isSyncActive =
                (currentRepo.status === "syncing" ||
                  currentRepo.status === "pending" ||
                  syncJob?.status === "running" ||
                  syncJob?.status === "pending") &&
                syncJob?.status !== "failed" &&
                currentRepo.status !== "failed";
              const isSyncFailed = (currentRepo.status === "failed" || syncJob?.status === "failed") && !isSyncActive;
              const syncDisplay = isSyncFailed ? "FAILED" : isSyncActive ? "SYNCING" : currentRepo.status.toUpperCase();
              const badgeType = isSyncFailed ? "danger" : syncDisplay === "READY" ? "success" : "warning";
              return (
                <span className={`badge badge-${badgeType}`} id="sync-status-badge">
                  <span className={`badge-dot ${isSyncActive ? "pulse-dot" : ""}`} />
                  SYNC: {syncDisplay}
                </span>
              );
            })()}

            {/* Index Status Badge */}
            {(() => {
              const isIndexActive =
                (currentRepo.index_status === "indexing" ||
                  indexJob?.status === "running" ||
                  indexJob?.status === "pending") &&
                indexJob?.status !== "failed" &&
                currentRepo.index_status !== "failed";
              const isIndexFailed = (currentRepo.index_status === "failed" || indexJob?.status === "failed") && !isIndexActive;
              const isPartial = Boolean(
                indexJob?.stats?.partial ||
                (currentRepo.chunk_count && currentRepo.chunk_count > 0 && isIndexFailed)
              );
              const badgeType = isPartial
                ? "warning"
                : currentRepo.index_status === "ready"
                ? "success"
                : isIndexFailed
                ? "danger"
                : isIndexActive
                ? "warning"
                : "outline";
              const label = isPartial
                ? `PARTIAL (${currentRepo.chunk_count || 0})`
                : currentRepo.index_status === "ready"
                ? `INDEXED (${currentRepo.chunk_count || 0})`
                : isIndexActive
                ? "INDEXING..."
                : isIndexFailed
                ? "INDEX FAILED"
                : "NOT INDEXED";
              return (
                <span
                  className={`badge badge-${badgeType}`}
                  id="index-status-badge"
                  style={
                    !currentRepo.index_status || currentRepo.index_status === "none"
                      ? { background: "rgba(255, 255, 255, 0.06)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }
                      : {}
                  }
                >
                  <span className={`badge-dot ${isIndexActive ? "pulse-dot" : ""}`} />
                  {label}
                </span>
              );
            })()}
          </div>

          {currentRepo.description && (
            <p style={{ color: "var(--text-secondary)", fontSize: "0.92rem", marginTop: "0.4rem" }}>
              {currentRepo.description}
            </p>
          )}

          <div style={{ display: "flex", gap: "1.25rem", marginTop: "0.75rem", fontSize: "0.82rem", color: "var(--text-muted)", flexWrap: "wrap" }}>
            <span>Default branch: <strong style={{ color: "var(--text-primary)" }}>{currentRepo.default_branch}</strong></span>
            {currentRepo.language && (
              <span>Language: <strong style={{ color: "var(--text-primary)" }}>{currentRepo.language}</strong></span>
            )}
            <span>
              Last synced:{" "}
              <strong style={{ color: "var(--text-primary)" }}>
                {currentRepo.last_synced_at ? new Date(currentRepo.last_synced_at).toLocaleString() : "Never"}
              </strong>
            </span>
            {currentRepo.indexed_at && (
              <span>
                Last indexed:{" "}
                <strong style={{ color: "var(--text-primary)" }}>
                  {new Date(currentRepo.indexed_at).toLocaleString()}
                </strong>
              </span>
            )}
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <button
            onClick={handleTriggerIndex}
            disabled={
              (currentRepo.index_status === "indexing" && indexJob?.status !== "failed") ||
              isTriggeringIndex
            }
            className="btn btn-outline"
            style={{ padding: "0.55rem 1.2rem", fontSize: "0.85rem", display: "inline-flex", alignItems: "center", gap: "0.45rem" }}
          >
            {currentRepo.index_status === "indexing" && indexJob?.status !== "failed" ? (
              <>
                <div className="spinner" style={{ width: "13px", height: "13px", borderWidth: "2px" }} />
                Indexing...
              </>
            ) : currentRepo.index_status === "ready" ? (
              "Re-index Codebase"
            ) : (
              "Index Codebase"
            )}
          </button>
          <button
            onClick={handleTriggerSync}
            disabled={
              (currentRepo.status === "syncing" && syncJob?.status !== "failed") ||
              (currentRepo.status === "pending" && syncJob?.status !== "failed") ||
              isTriggeringSync ||
              (syncJob ? !isTerminalStatus(syncJob.status, syncJob.stage) && syncJob.status !== "failed" && (syncJob.status === "running" || syncJob.status === "pending") : false)
            }
            className="btn btn-primary"
            style={{ padding: "0.55rem 1.2rem", fontSize: "0.85rem" }}
          >
            {(currentRepo.status === "syncing" || (syncJob && syncJob.status === "running" && !isTerminalStatus(syncJob.status, syncJob.stage))) && syncJob?.status !== "failed" && currentRepo.status !== "failed"
              ? "Syncing..."
              : isTriggeringSync
              ? "Starting Sync..."
              : "Re-sync Repository"}
          </button>
        </div>
      </div>

      {/* Sync Status Banner */}
      {!isTerminalStatus(syncJob?.status, syncJob?.stage) &&
        syncJob?.status !== "failed" &&
        currentRepo.status !== "failed" &&
        (currentRepo.status === "syncing" ||
          currentRepo.status === "pending" ||
          syncJob?.status === "running" ||
          syncJob?.status === "pending") && (
        <div
          className="glass-card"
          style={{
            padding: "1.25rem 1.75rem",
            background: "rgba(99, 102, 241, 0.08)",
            borderColor: "rgba(99, 102, 241, 0.3)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
            <span style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--accent-primary)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <div className="spinner" style={{ width: "16px", height: "16px", borderWidth: "2px" }} />
              Ingestion Pipeline Active: Stage [{syncJob?.stage || "queued"}]
            </span>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
              {syncJob?.progress || 0}%
            </span>
          </div>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{
                width: `${syncJob?.progress || 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Index Status Banner */}
      {!isTerminalStatus(indexJob?.status, indexJob?.stage) &&
        indexJob?.status !== "failed" &&
        currentRepo.index_status !== "failed" &&
        (currentRepo.index_status === "indexing" || (indexJob && indexJob.status === "running")) && (
        <div
          className="glass-card"
          style={{
            padding: "1.25rem 1.75rem",
            background: "rgba(139, 92, 246, 0.08)",
            borderColor: "rgba(139, 92, 246, 0.3)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
            <span style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--accent-secondary)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <div className="spinner" style={{ width: "16px", height: "16px", borderWidth: "2px" }} />
              Codebase Indexing Active: Stage [{indexJob?.stage || "queued"}]
            </span>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
              {indexJob?.progress || 0}%
            </span>
          </div>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{
                width: `${indexJob?.progress || 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Sync Error Banner */}
      {!((currentRepo.status === "syncing" || currentRepo.status === "pending" || syncJob?.status === "running" || syncJob?.status === "pending") && syncJob?.status !== "failed" && currentRepo.status !== "failed") &&
        (currentRepo.status === "failed" || syncJob?.status === "failed") &&
        (currentRepo.sync_error || syncJob?.error) && (
        <div
          id="sync-error-banner"
          className="glass-card"
          style={{
            padding: "1rem 1.5rem",
            background: "rgba(239, 68, 68, 0.12)",
            border: "1px solid var(--danger)",
            borderRadius: "var(--radius-md)",
            color: "var(--danger)",
            fontSize: "0.88rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div>
              <strong>Sync Failed:</strong> {currentRepo.sync_error || syncJob?.error}
            </div>
          </div>
          <button
            onClick={handleTriggerSync}
            disabled={isTriggeringSync}
            id="retry-sync-button"
            className="btn btn-outline"
            style={{
              padding: "0.4rem 0.9rem",
              fontSize: "0.82rem",
              borderColor: "var(--danger)",
              color: "var(--danger)",
              cursor: "pointer",
            }}
          >
            {isTriggeringSync ? "Retrying..." : "Retry Sync"}
          </button>
        </div>
      )}

      {/* Partial Index Banner */}
      {Boolean(
        indexJob?.stats?.partial ||
        (currentRepo.chunk_count && currentRepo.chunk_count > 0 && (currentRepo.index_status === "failed" || indexJob?.status === "failed"))
      ) && (
        <div
          id="partial-index-banner"
          className="glass-card"
          style={{
            padding: "1rem 1.5rem",
            background: "rgba(245, 158, 11, 0.12)",
            border: "1px solid var(--warning)",
            borderRadius: "var(--radius-md)",
            color: "var(--warning)",
            fontSize: "0.88rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div>
              <strong>Partial index ({currentRepo.chunk_count || indexJob?.stats?.saved_chunks || 0} of {indexJob?.stats?.total_chunks || currentRepo.chunk_count || 0}):</strong> click Index to continue
            </div>
          </div>
          <button
            onClick={handleTriggerIndex}
            disabled={isTriggeringIndex}
            id="continue-index-button"
            className="btn btn-outline"
            style={{
              padding: "0.4rem 0.9rem",
              fontSize: "0.82rem",
              borderColor: "var(--warning)",
              color: "var(--warning)",
              cursor: "pointer",
            }}
          >
            {isTriggeringIndex ? "Indexing..." : "Index"}
          </button>
        </div>
      )}

      {/* Index Error Banner */}
      {!Boolean(indexJob?.stats?.partial || (currentRepo.chunk_count && currentRepo.chunk_count > 0 && (currentRepo.index_status === "failed" || indexJob?.status === "failed"))) &&
        !((currentRepo.index_status === "indexing" || indexJob?.status === "running" || indexJob?.status === "pending") && indexJob?.status !== "failed" && currentRepo.index_status !== "failed") &&
        (currentRepo.index_status === "failed" || indexJob?.status === "failed") &&
        (indexError || indexJob?.error) && (
        <div
          id="index-error-banner"
          className="glass-card"
          style={{
            padding: "1rem 1.5rem",
            background: "rgba(239, 68, 68, 0.12)",
            border: "1px solid var(--danger)",
            borderRadius: "var(--radius-md)",
            color: "var(--danger)",
            fontSize: "0.88rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div>
              <strong>Indexing Failed:</strong> {indexError || indexJob?.error}
            </div>
          </div>
          <button
            onClick={handleTriggerIndex}
            disabled={isTriggeringIndex}
            id="retry-index-button"
            className="btn btn-outline"
            style={{
              padding: "0.4rem 0.9rem",
              fontSize: "0.82rem",
              borderColor: "var(--danger)",
              color: "var(--danger)",
              cursor: "pointer",
            }}
          >
            {isTriggeringIndex ? "Retrying..." : "Retry Index"}
          </button>
        </div>
      )}

      {/* Tabs Navigation */}
      <div className="tab-container">
        <button
          className={`tab-btn ${activeTab === "commits" ? "active" : ""}`}
          onClick={() => setActiveTab("commits")}
        >
          Commits
        </button>
        <button
          className={`tab-btn ${activeTab === "pulls" ? "active" : ""}`}
          onClick={() => setActiveTab("pulls")}
        >
          Pull Requests
        </button>
        <button
          className={`tab-btn ${activeTab === "issues" ? "active" : ""}`}
          onClick={() => setActiveTab("issues")}
        >
          Issues
        </button>
        <button
          className={`tab-btn ${activeTab === "search" ? "active" : ""}`}
          onClick={() => setActiveTab("search")}
        >
          Code Search
        </button>
        <button
          className={`tab-btn ${activeTab === "ask" ? "active" : ""}`}
          onClick={() => setActiveTab("ask")}
        >
          💬 Ask Q&A
        </button>
        <button
          className={`tab-btn ${activeTab === "docs" ? "active" : ""}`}
          onClick={() => setActiveTab("docs")}
        >
          📚 Documentation
        </button>
        <button
          className={`tab-btn ${activeTab === "tests" ? "active" : ""}`}
          onClick={() => setActiveTab("tests")}
        >
          🧪 Tests
        </button>
      </div>

      {/* Tab 1: Commits */}
      {activeTab === "commits" && (
        <div className="glass-card" style={{ padding: "1.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 600 }}>Ingested Commits ({commits.length})</h2>
            <input
              type="text"
              placeholder="Filter by author..."
              value={commitAuthorFilter}
              onChange={(e) => setCommitAuthorFilter(e.target.value)}
              className="search-input"
              style={{ maxWidth: "260px" }}
            />
          </div>

          {commitsLoading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              <div className="spinner" style={{ margin: "0 auto 1rem" }} />
              Loading commits...
            </div>
          ) : commits.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.9rem" }}>
              {repo.status === "pending" || repo.status === "syncing"
                ? "Sync in progress. Commits will appear here once ingested."
                : "No commits found for this repository."}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>SHA</th>
                    <th>Message</th>
                    <th>Author</th>
                    <th>Committed At</th>
                    <th style={{ textAlign: "right" }}>Changes</th>
                  </tr>
                </thead>
                <tbody>
                  {commits.map((c) => (
                    <tr key={c.id}>
                      <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.82rem", color: "#a5b4fc" }}>
                        {c.sha.slice(0, 7)}
                      </td>
                      <td style={{ fontWeight: 500, maxWidth: "380px" }}>
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {c.message.split("\n")[0]}
                        </div>
                      </td>
                      <td style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                        {c.author_login ? `@${c.author_login}` : c.author_name || "Unknown"}
                      </td>
                      <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                        {new Date(c.committed_at).toLocaleDateString()}
                      </td>
                      <td style={{ textAlign: "right", fontSize: "0.82rem", fontFamily: "var(--font-mono)" }}>
                        {c.additions !== null && (
                          <span style={{ color: "var(--success)", marginRight: "0.5rem" }}>
                            +{c.additions}
                          </span>
                        )}
                        {c.deletions !== null && (
                          <span style={{ color: "var(--danger)" }}>
                            -{c.deletions}
                          </span>
                        )}
                        {c.additions === null && c.deletions === null && (
                          <span style={{ color: "var(--text-muted)" }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Pull Requests */}
      {activeTab === "pulls" && (() => {
        const filteredPrs = prs.filter((p) => {
          const analysis = prAnalyses[p.number];
          if (prRiskFilter === "risky") {
            return analysis && (analysis.risk_level === "medium" || analysis.risk_level === "high");
          }
          if (prRiskFilter === "high") {
            return analysis && analysis.risk_level === "high";
          }
          if (prRiskFilter === "analyzed") {
            return !!analysis;
          }
          return true;
        });

        return (
          <div className="glass-card" style={{ padding: "1.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <h2 style={{ fontSize: "1.15rem", fontWeight: 600 }}>Pull Requests ({filteredPrs.length})</h2>
                <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                  Automated deterministic risk scoring and LLM change summaries.
                </p>
              </div>

              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
                {/* Risk Filter */}
                <select
                  value={prRiskFilter}
                  onChange={(e) => setPrRiskFilter(e.target.value)}
                  className="search-input"
                  style={{ padding: "0.45rem 0.75rem", cursor: "pointer", fontSize: "0.82rem" }}
                >
                  <option value="all">All Risk Levels</option>
                  <option value="risky">⚠️ Risky (Medium & High)</option>
                  <option value="high">🚨 High Risk Only</option>
                  <option value="analyzed">Analyzed Only</option>
                </select>

                <select
                  value={prStateFilter}
                  onChange={(e) => setPrStateFilter(e.target.value)}
                  className="search-input"
                  style={{ padding: "0.45rem 0.75rem", cursor: "pointer", fontSize: "0.82rem" }}
                >
                  <option value="all">All States</option>
                  <option value="open">Open</option>
                  <option value="closed">Closed</option>
                </select>

                <input
                  type="text"
                  placeholder="Filter by author..."
                  value={prAuthorFilter}
                  onChange={(e) => setPrAuthorFilter(e.target.value)}
                  className="search-input"
                  style={{ maxWidth: "160px", fontSize: "0.82rem" }}
                />
              </div>
            </div>

            {prsLoading ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
                <div className="spinner" style={{ margin: "0 auto 1rem" }} />
                Loading pull requests...
              </div>
            ) : filteredPrs.length === 0 ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.9rem" }}>
                {repo.status === "pending" || repo.status === "syncing"
                  ? "Sync in progress. Pull requests will appear here once ingested."
                  : prRiskFilter !== "all"
                  ? "No pull requests match the selected risk filter."
                  : "No pull requests found."}
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Title</th>
                      <th>State</th>
                      <th>Risk Level</th>
                      <th>Author</th>
                      <th>Branches</th>
                      <th>Created</th>
                      <th style={{ textAlign: "right" }}>Review</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPrs.map((p) => {
                      const analysis = prAnalyses[p.number];
                      const isExpanded = !!expandedPrs[p.number];
                      const isAnalyzing = !!prAnalyzing[p.number];
                      const err = prErrors[p.number];

                      return (
                        <React.Fragment key={p.id}>
                          <tr>
                            <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                              #{p.number}
                            </td>
                            <td style={{ fontWeight: 500, maxWidth: "260px" }}>
                              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {p.title}
                              </div>
                            </td>
                            <td>
                              <span
                                className={`badge badge-${
                                  p.merged_at ? "success" : p.state === "open" ? "success" : "danger"
                                }`}
                                style={{ fontSize: "0.72rem" }}
                              >
                                {p.merged_at ? "merged" : p.state}
                              </span>
                            </td>
                            <td>
                              {analysis ? (
                                <span
                                  className={`badge badge-${
                                    analysis.risk_level === "high"
                                      ? "danger"
                                      : analysis.risk_level === "medium"
                                      ? "warning"
                                      : "success"
                                  }`}
                                  style={{ fontSize: "0.72rem", cursor: "pointer" }}
                                  onClick={() => toggleExpandPr(p.number)}
                                  title={`Risk score: ${analysis.risk_score} points`}
                                >
                                  {analysis.risk_level.toUpperCase()} ({analysis.risk_score})
                                </span>
                              ) : (
                                <span
                                  className="badge badge-outline"
                                  style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}
                                >
                                  Not Analyzed
                                </span>
                              )}
                            </td>
                            <td style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                              {p.author_login ? `@${p.author_login}` : "Unknown"}
                            </td>
                            <td style={{ fontSize: "0.78rem", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                              {p.head_ref || "?"} → {p.base_ref || "main"}
                            </td>
                            <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                              {new Date(p.created_at).toLocaleDateString()}
                            </td>
                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                              <div style={{ display: "inline-flex", gap: "0.4rem", alignItems: "center" }}>
                                {analysis ? (
                                  <>
                                    <button
                                      onClick={() => toggleExpandPr(p.number)}
                                      className="btn btn-outline"
                                      style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                                    >
                                      {isExpanded ? "Hide ▲" : "Review ▼"}
                                    </button>
                                    <button
                                      onClick={() => handleAnalyzePr(p.number, true)}
                                      disabled={isAnalyzing}
                                      className="btn btn-outline"
                                      style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                                      title="Re-run analysis"
                                    >
                                      {isAnalyzing ? (
                                        <div className="spinner" style={{ width: "12px", height: "12px", borderWidth: "2px" }} />
                                      ) : (
                                        "↻"
                                      )}
                                    </button>
                                  </>
                                ) : (
                                  <button
                                    onClick={() => handleAnalyzePr(p.number, false)}
                                    disabled={isAnalyzing}
                                    className="btn btn-primary"
                                    style={{ padding: "0.3rem 0.75rem", fontSize: "0.78rem" }}
                                  >
                                    {isAnalyzing ? (
                                      <>
                                        <div className="spinner" style={{ width: "12px", height: "12px", borderWidth: "2px", marginRight: "4px" }} />
                                        Analyzing...
                                      </>
                                    ) : (
                                      "Analyze"
                                    )}
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>

                          {/* Rate limit or general error notification */}
                          {err && (
                            <tr>
                              <td colSpan={8} style={{ padding: "0.6rem 1rem", background: "rgba(239, 68, 68, 0.08)", borderBottom: "1px solid rgba(239, 68, 68, 0.2)" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--danger)", fontSize: "0.82rem" }}>
                                  <span>⚠️</span>
                                  <span>{err}</span>
                                </div>
                              </td>
                            </tr>
                          )}

                          {/* Expandable Review Drawer */}
                          {isExpanded && analysis && (
                            <tr>
                              <td
                                colSpan={8}
                                style={{
                                  padding: "1.25rem 1.5rem",
                                  background: "rgba(17, 24, 39, 0.65)",
                                  borderBottom: "1px solid var(--border-color)",
                                }}
                              >
                                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                                  {/* Drawer Top Meta */}
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                                      <span
                                        className={`badge badge-${
                                          analysis.risk_level === "high"
                                            ? "danger"
                                            : analysis.risk_level === "medium"
                                            ? "warning"
                                            : "success"
                                        }`}
                                        style={{ fontSize: "0.78rem", fontWeight: 700 }}
                                      >
                                        {analysis.risk_level.toUpperCase()} RISK (Score: {analysis.risk_score})
                                      </span>
                                      <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                                        Files analyzed: {analysis.files_analyzed}
                                        {analysis.truncated && " (patch truncated to limit)"}
                                      </span>
                                      {analysis.model && (
                                        <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                                          Model: {analysis.model}
                                        </span>
                                      )}
                                    </div>

                                    <button
                                      onClick={() => handleAnalyzePr(p.number, true)}
                                      disabled={isAnalyzing}
                                      className="btn btn-outline"
                                      style={{ padding: "0.25rem 0.65rem", fontSize: "0.75rem" }}
                                    >
                                      {isAnalyzing ? "Refreshing..." : "↻ Re-analyze PR"}
                                    </button>
                                  </div>

                                  {/* Risk Reasons */}
                                  {analysis.risk_reasons && analysis.risk_reasons.length > 0 && (
                                    <div
                                      style={{
                                        padding: "0.85rem 1rem",
                                        borderRadius: "var(--radius-md)",
                                        background:
                                          analysis.risk_level === "high"
                                            ? "rgba(239, 68, 68, 0.1)"
                                            : analysis.risk_level === "medium"
                                            ? "rgba(245, 158, 11, 0.1)"
                                            : "rgba(16, 185, 129, 0.08)",
                                        border: `1px solid ${
                                          analysis.risk_level === "high"
                                            ? "rgba(239, 68, 68, 0.3)"
                                            : analysis.risk_level === "medium"
                                            ? "rgba(245, 158, 11, 0.3)"
                                            : "rgba(16, 185, 129, 0.25)"
                                        }`,
                                      }}
                                    >
                                      <div style={{ fontSize: "0.82rem", fontWeight: 700, marginBottom: "0.4rem", color: "var(--text-primary)" }}>
                                        Deterministic Risk Factors Triggered:
                                      </div>
                                      <ul style={{ margin: 0, paddingLeft: "1.25rem", fontSize: "0.82rem", lineHeight: "1.5" }}>
                                        {analysis.risk_reasons.map((reason, idx) => (
                                          <li
                                            key={idx}
                                            style={{
                                              color:
                                                analysis.risk_level === "high"
                                                  ? "#fca5a5"
                                                  : analysis.risk_level === "medium"
                                                  ? "#fcd34d"
                                                  : "#86efac",
                                            }}
                                          >
                                            {reason}
                                          </li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}

                                  {/* Markdown Summary */}
                                  {analysis.summary_markdown ? (
                                    <div
                                      className="glass-card"
                                      style={{
                                        padding: "1rem 1.25rem",
                                        background: "rgba(0, 0, 0, 0.25)",
                                        fontSize: "0.88rem",
                                        lineHeight: "1.6",
                                      }}
                                    >
                                      <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--accent-primary)", marginBottom: "0.5rem" }}>
                                        PR Summary & Reviewer Guidance:
                                      </div>
                                      <div className="markdown-content">
                                        <ReactMarkdown>{analysis.summary_markdown}</ReactMarkdown>
                                      </div>
                                    </div>
                                  ) : (
                                    <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                                      No AI summary generated for this pull request.
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })()}

      {/* Tab 3: Issues */}
      {activeTab === "issues" && (() => {
        const filteredIssues = issues.filter((i) => {
          if (issueTypeFilter !== "all") {
            const analysis = issueAnalyses[i.number];
            return analysis && analysis.issue_type === issueTypeFilter;
          }
          return true;
        });

        const isAnalyzing =
          (issueJob?.status === "running" || issueJob?.status === "pending") &&
          !isTerminalStatus(issueJob?.status, issueJob?.stage);

        return (
          <div className="glass-card" style={{ padding: "1.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <h2 style={{ fontSize: "1.15rem", fontWeight: 600 }}>Issues ({filteredIssues.length})</h2>
                <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                  Classified with Gemini and indexed for duplicate detection via pgvector embeddings.
                </p>
              </div>

              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
                {/* Analyze Issues Button */}
                <button
                  onClick={handleTriggerIssueAnalysis}
                  disabled={isTriggeringIssueAnalysis || isAnalyzing}
                  className="btn btn-primary"
                  style={{ padding: "0.45rem 1rem", fontSize: "0.82rem", display: "inline-flex", alignItems: "center", gap: "0.45rem" }}
                >
                  {isAnalyzing ? (
                    <>
                      <div className="spinner" style={{ width: "13px", height: "13px", borderWidth: "2px" }} />
                      Analyzing ({issueJob?.stage || "queued"})...
                    </>
                  ) : isTriggeringIssueAnalysis ? (
                    "Starting Analysis..."
                  ) : (
                    "⚡ Analyze Issues"
                  )}
                </button>

                {/* Type Filter */}
                <select
                  value={issueTypeFilter}
                  onChange={(e) => setIssueTypeFilter(e.target.value)}
                  className="search-input"
                  style={{ padding: "0.45rem 0.75rem", cursor: "pointer", fontSize: "0.82rem" }}
                >
                  <option value="all">All Types</option>
                  <option value="bug">🐛 Bug</option>
                  <option value="feature">✨ Feature</option>
                  <option value="question">❓ Question</option>
                  <option value="documentation">📚 Docs</option>
                  <option value="chore">🔧 Chore</option>
                  <option value="unclassified">Unclassified</option>
                </select>

                <select
                  value={issueStateFilter}
                  onChange={(e) => setIssueStateFilter(e.target.value)}
                  className="search-input"
                  style={{ padding: "0.45rem 0.75rem", cursor: "pointer", fontSize: "0.82rem" }}
                >
                  <option value="all">All States</option>
                  <option value="open">Open</option>
                  <option value="closed">Closed</option>
                </select>

                <input
                  type="text"
                  placeholder="Filter by author..."
                  value={issueAuthorFilter}
                  onChange={(e) => setIssueAuthorFilter(e.target.value)}
                  className="search-input"
                  style={{ maxWidth: "160px", fontSize: "0.82rem" }}
                />
              </div>
            </div>

            {/* Analysis Active Progress Banner */}
            {isAnalyzing && (
              <div
                className="glass-card"
                style={{
                  padding: "1.25rem 1.75rem",
                  marginBottom: "1.25rem",
                  background: "rgba(99, 102, 241, 0.08)",
                  borderColor: "rgba(99, 102, 241, 0.3)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
                  <span style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--accent-primary)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <div className="spinner" style={{ width: "16px", height: "16px", borderWidth: "2px" }} />
                    Issue Intelligence Pipeline Active: Stage [{issueJob?.stage || "queued"}]
                  </span>
                  <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    {issueJob?.progress || 0}%
                  </span>
                </div>
                <div style={{ width: "100%", height: "6px", background: "rgba(255, 255, 255, 0.1)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${issueJob?.progress || 0}%`,
                      height: "100%",
                      background: "var(--accent-gradient)",
                      transition: "width 0.4s ease",
                    }}
                  />
                </div>
              </div>
            )}

            {/* Error Banner */}
            {issueAnalysisError && (
              <div
                style={{
                  padding: "0.85rem 1.25rem",
                  marginBottom: "1.25rem",
                  background: "rgba(239, 68, 68, 0.12)",
                  border: "1px solid var(--danger)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--danger)",
                  fontSize: "0.88rem",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "0.75rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span>⚠️</span>
                  <span>{issueAnalysisError}</span>
                </div>
                <button
                  onClick={handleTriggerIssueAnalysis}
                  className="btn btn-outline"
                  style={{ padding: "0.3rem 0.75rem", fontSize: "0.8rem", borderColor: "var(--danger)", color: "var(--danger)" }}
                >
                  Retry Analysis
                </button>
              </div>
            )}

            {issuesLoading ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
                <div className="spinner" style={{ margin: "0 auto 1rem" }} />
                Loading issues...
              </div>
            ) : filteredIssues.length === 0 ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.9rem" }}>
                {repo.status === "pending" || repo.status === "syncing"
                  ? "Sync in progress. Issues will appear here once ingested."
                  : issueTypeFilter !== "all"
                  ? "No issues match the selected type filter."
                  : "No issues found."}
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Title & Labels</th>
                      <th>Classification</th>
                      <th>State</th>
                      <th>Author</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredIssues.map((i) => {
                      const ia = issueAnalyses[i.number];

                      return (
                        <tr key={i.id}>
                          <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                            #{i.number}
                          </td>
                          <td style={{ maxWidth: "380px" }}>
                            <div style={{ fontWeight: 500, marginBottom: "0.25rem" }}>{i.title}</div>
                            {i.labels && i.labels.length > 0 && (
                              <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                                {i.labels.map((lbl, idx) => {
                                  const bg = lbl.color ? `#${lbl.color}` : "rgba(255, 255, 255, 0.15)";
                                  return (
                                    <span
                                      key={idx}
                                      style={{
                                        fontSize: "0.68rem",
                                        padding: "0.1rem 0.45rem",
                                        borderRadius: "var(--radius-full)",
                                        background: bg,
                                        color: "#fff",
                                        fontWeight: 600,
                                        textShadow: "0 1px 2px rgba(0,0,0,0.6)",
                                      }}
                                    >
                                      {lbl.name}
                                    </span>
                                  );
                                })}
                              </div>
                            )}
                          </td>
                          <td>
                            {ia ? (
                              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                <span
                                  className={`badge badge-${
                                    ia.issue_type === "bug"
                                      ? "danger"
                                      : ia.issue_type === "feature"
                                      ? "primary"
                                      : ia.issue_type === "documentation"
                                      ? "success"
                                      : ia.issue_type === "question"
                                      ? "warning"
                                      : "outline"
                                  }`}
                                  style={{
                                    fontSize: "0.72rem",
                                    fontWeight: 600,
                                    background:
                                      ia.issue_type === "feature"
                                        ? "rgba(14, 165, 233, 0.2)"
                                        : ia.issue_type === "question"
                                        ? "rgba(168, 85, 247, 0.2)"
                                        : undefined,
                                    color:
                                      ia.issue_type === "feature"
                                        ? "#38bdf8"
                                        : ia.issue_type === "question"
                                        ? "#c084fc"
                                        : undefined,
                                    borderColor:
                                      ia.issue_type === "feature"
                                        ? "rgba(14, 165, 233, 0.4)"
                                        : ia.issue_type === "question"
                                        ? "rgba(168, 85, 247, 0.4)"
                                        : undefined,
                                  }}
                                  title={ia.reason || undefined}
                                >
                                  {ia.issue_type.toUpperCase()}
                                </span>
                                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                  {Math.round(ia.confidence * 100)}%
                                </span>
                              </div>
                            ) : (
                              <span className="badge badge-outline" style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                Pending
                              </span>
                            )}
                          </td>
                          <td>
                            <span
                              className={`badge badge-${i.state === "open" ? "success" : "danger"}`}
                              style={{ fontSize: "0.72rem" }}
                            >
                              {i.state}
                            </span>
                          </td>
                          <td style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                            {i.author_login ? `@${i.author_login}` : "Unknown"}
                          </td>
                          <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                            {new Date(i.created_at).toLocaleDateString()}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Duplicate Issues Section */}
            <div style={{ marginTop: "2.5rem", borderTop: "1px solid var(--border-color)", paddingTop: "1.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.75rem" }}>
                <div>
                  <h3 style={{ fontSize: "1.05rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span>⚡ Possible Duplicate Issues</span>
                    <span className="badge badge-outline" style={{ fontSize: "0.72rem" }}>
                      {duplicates.length} pairs (≥85% similarity)
                    </span>
                  </h3>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.82rem", marginTop: "0.2rem" }}>
                    Cosine similarity computed with pgvector embeddings.
                  </p>
                </div>
                <button
                  onClick={fetchDuplicates}
                  disabled={duplicatesLoading}
                  className="btn btn-outline"
                  style={{ padding: "0.3rem 0.75rem", fontSize: "0.78rem" }}
                >
                  {duplicatesLoading ? "Refreshing..." : "↻ Refresh Duplicates"}
                </button>
              </div>

              {duplicatesLoading ? (
                <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  <div className="spinner" style={{ margin: "0 auto 0.5rem", width: "20px", height: "20px" }} />
                  Checking duplicate vector pairs...
                </div>
              ) : duplicates.length === 0 ? (
                <div
                  style={{
                    padding: "1.5rem",
                    textAlign: "center",
                    color: "var(--text-muted)",
                    fontSize: "0.85rem",
                    background: "rgba(255, 255, 255, 0.02)",
                    borderRadius: "var(--radius-md)",
                    border: "1px dashed var(--border-color)",
                  }}
                >
                  No duplicate issue pairs found with similarity ≥ 85%. Run &quot;Analyze Issues&quot; to compute embeddings.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {duplicates.map((pair, idx) => (
                    <div
                      key={idx}
                      className="glass-card"
                      style={{
                        padding: "1rem 1.25rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: "1rem",
                        borderLeft: "3px solid var(--accent-primary)",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", flex: 1, minWidth: "300px", flexWrap: "wrap" }}>
                        {/* Issue A */}
                        <div style={{ flex: 1, minWidth: "180px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "#a5b4fc", fontWeight: 600 }}>
                              #{pair.issue_a}
                            </span>
                            <span style={{ fontSize: "0.88rem", fontWeight: 500, color: "var(--text-primary)" }}>
                              {pair.title_a}
                            </span>
                          </div>
                          <a
                            href={pair.link_a}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: "0.75rem", color: "var(--accent-primary)", textDecoration: "none", marginTop: "0.2rem", display: "inline-block" }}
                          >
                            View on GitHub ↗
                          </a>
                        </div>

                        {/* Similarity Badge */}
                        <div style={{ textAlign: "center", flexShrink: 0 }}>
                          <span
                            className="badge badge-warning"
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              padding: "0.25rem 0.65rem",
                              letterSpacing: "0.02em",
                            }}
                          >
                            {(pair.similarity * 100).toFixed(1)}% MATCH
                          </span>
                        </div>

                        {/* Issue B */}
                        <div style={{ flex: 1, minWidth: "180px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "#a5b4fc", fontWeight: 600 }}>
                              #{pair.issue_b}
                            </span>
                            <span style={{ fontSize: "0.88rem", fontWeight: 500, color: "var(--text-primary)" }}>
                              {pair.title_b}
                            </span>
                          </div>
                          <a
                            href={pair.link_b}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: "0.75rem", color: "var(--accent-primary)", textDecoration: "none", marginTop: "0.2rem", display: "inline-block" }}
                          >
                            View on GitHub ↗
                          </a>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })()}

      {/* Tab 4: Code Search */}
      {activeTab === "search" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* If repo is not indexed or failed */}
          {currentRepo.index_status !== "ready" && currentRepo.index_status !== "indexing" && (
            <div
              className="glass-card"
              style={{
                padding: "2.5rem 2rem",
                textAlign: "center",
                background: "rgba(99, 102, 241, 0.05)",
                borderColor: "rgba(99, 102, 241, 0.2)",
              }}
            >
              <div
                style={{
                  width: "56px",
                  height: "56px",
                  borderRadius: "var(--radius-full)",
                  background: "rgba(99, 102, 241, 0.15)",
                  color: "var(--accent-primary)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "1.75rem",
                  margin: "0 auto 1.25rem",
                }}
              >
                ⚡
              </div>
              <h3 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Codebase Not Indexed
              </h3>
              <p
                style={{
                  color: "var(--text-secondary)",
                  maxWidth: "520px",
                  margin: "0 auto 1.5rem",
                  fontSize: "0.92rem",
                }}
              >
                Semantic and hybrid code search require indexing the repository files and generating vector embeddings with Gemini.
              </p>
              <button
                onClick={handleTriggerIndex}
                disabled={isTriggeringIndex}
                className="btn btn-primary"
                style={{ padding: "0.75rem 1.75rem", fontSize: "0.95rem" }}
              >
                {isTriggeringIndex ? "Starting Indexing..." : "Index Codebase Now"}
              </button>
            </div>
          )}

          {/* If repo is currently indexing */}
          {currentRepo.index_status === "indexing" && (
            <div
              className="glass-card"
              style={{
                padding: "2.5rem 2rem",
                textAlign: "center",
                background: "rgba(139, 92, 246, 0.05)",
                borderColor: "rgba(139, 92, 246, 0.2)",
              }}
            >
              <div className="spinner" style={{ width: "36px", height: "36px", margin: "0 auto 1.25rem" }} />
              <h3 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Indexing in Progress...
              </h3>
              <p
                style={{
                  color: "var(--text-secondary)",
                  maxWidth: "500px",
                  margin: "0 auto",
                  fontSize: "0.92rem",
                }}
              >
                We are streaming files, chunking code ASTs, and computing Gemini vector embeddings.
                Search will be enabled as soon as indexing finishes.
              </p>
            </div>
          )}

          {/* Search Controls (Available whenever ready, or to test queries) */}
          <div className="glass-card" style={{ padding: "1.75rem" }}>
            <form onSubmit={handleSearch} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: "260px", position: "relative" }}>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search code by keywords or natural language intent (e.g. 'JWT token verification' or 'fetch_pull_requests')..."
                    className="search-input"
                    style={{ width: "100%", padding: "0.75rem 1rem", fontSize: "0.95rem" }}
                  />
                </div>
                <button
                  type="submit"
                  disabled={searchLoading || !searchQuery.trim()}
                  className="btn btn-primary"
                  style={{ padding: "0.75rem 1.5rem", minWidth: "120px" }}
                >
                  {searchLoading ? (
                    <>
                      <div className="spinner" style={{ width: "14px", height: "14px", borderWidth: "2px" }} />
                      Searching...
                    </>
                  ) : (
                    "Search Code"
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Search Error */}
          {searchError && (
            <div
              style={{
                padding: "1rem 1.5rem",
                background: "var(--danger-bg)",
                border: "1px solid var(--danger)",
                borderRadius: "var(--radius-md)",
                color: "var(--danger)",
                fontSize: "0.88rem",
              }}
            >
              <strong>Search Error:</strong> {searchError}
            </div>
          )}

          {/* Loading Indicator */}
          {searchLoading && (
            <div className="glass-card" style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              <div className="spinner" style={{ margin: "0 auto 1rem" }} />
              Searching codebase...
            </div>
          )}

          {/* Empty Results */}
          {!searchLoading && hasSearched && searchResults.length === 0 && !searchError && (
            <div className="glass-card" style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              <p style={{ fontSize: "1rem", marginBottom: "0.5rem", color: "var(--text-primary)" }}>
                No code results found
              </p>
              <p style={{ fontSize: "0.85rem" }}>
                Try tweaking your search terms or re-indexing.
              </p>
            </div>
          )}

          {/* Search Results List */}
          {!searchLoading && searchResults.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 0.25rem" }}>
                <span style={{ fontSize: "0.9rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                  Found <strong style={{ color: "var(--text-primary)" }}>{searchResults.length}</strong> matching snippets:
                </span>
              </div>

              {searchResults.map((item, idx) => (
                <div
                  key={idx}
                  className="glass-card"
                  style={{
                    padding: "1.25rem 1.5rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.75rem",
                    overflow: "hidden",
                  }}
                >
                  {/* Result Header */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "0.75rem",
                      borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
                      paddingBottom: "0.6rem",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.9rem",
                          fontWeight: 600,
                          color: "var(--accent-primary)",
                        }}
                      >
                        {item.path}
                      </span>
                      <span
                        className="badge badge-outline"
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.75rem",
                          padding: "0.15rem 0.5rem",
                        }}
                      >
                        L{item.start_line} - L{item.end_line}
                      </span>
                      {item.language && (
                        <span className="badge badge-outline" style={{ fontSize: "0.72rem" }}>
                          {item.language}
                        </span>
                      )}
                      {item.symbol && (
                        <span
                          style={{
                            fontSize: "0.78rem",
                            fontFamily: "var(--font-mono)",
                            color: "var(--accent-secondary)",
                            background: "rgba(236, 72, 153, 0.1)",
                            padding: "0.15rem 0.5rem",
                            borderRadius: "var(--radius-sm)",
                          }}
                        >
                          {item.kind ? `${item.kind}: ` : ""}{item.symbol}
                        </span>
                      )}
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          fontFamily: "var(--font-mono)",
                          color: "var(--text-muted)",
                        }}
                      >
                        Score: {item.score.toFixed(4)}
                      </span>
                      <a
                        href={item.permalink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-outline"
                        style={{
                          padding: "0.25rem 0.65rem",
                          fontSize: "0.75rem",
                          textDecoration: "none",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.35rem",
                        }}
                      >
                        View on GitHub ↗
                      </a>
                    </div>
                  </div>

                  {/* Code Snippet Box */}
                  <div
                    style={{
                      background: "rgba(0, 0, 0, 0.4)",
                      borderRadius: "var(--radius-md)",
                      padding: "0.85rem 1rem",
                      overflowX: "auto",
                      border: "1px solid rgba(255, 255, 255, 0.04)",
                    }}
                  >
                    <pre
                      style={{
                        margin: 0,
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.82rem",
                        lineHeight: "1.45",
                        color: "#e2e8f0",
                        whiteSpace: "pre",
                      }}
                    >
                      {item.snippet}
                    </pre>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 5: Codebase Q&A */}
      {activeTab === "ask" && (
        <AskTab repo={currentRepo} onNavigateToIndex={() => setActiveTab("search")} />
      )}

      {/* Tab 6: Architecture & README Documentation */}
      {activeTab === "docs" && (
        <DocsTab repo={currentRepo} onNavigateToIndex={() => setActiveTab("search")} />
      )}

      {/* Tab 7: AI Test Generation */}
      {activeTab === "tests" && (
        <TestsTab repo={currentRepo} onNavigateToIndex={() => setActiveTab("search")} />
      )}
    </div>
  );
};
