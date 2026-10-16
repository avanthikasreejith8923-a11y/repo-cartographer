import React, { useEffect, useState } from "react";
import {
  Commit,
  IndexJob,
  Issue,
  PullRequest,
  Repository,
  SearchMode,
  SearchResultItem,
  SyncJob,
} from "../types";

import { AskTab } from "./AskTab";
import { DocsTab } from "./DocsTab";

interface RepoDetailViewProps {
  repo: Repository;
  onBack: () => void;
  onResync: (repoId: string) => void;
}

type TabType = "commits" | "pulls" | "issues" | "search" | "ask" | "docs";

export const RepoDetailView: React.FC<RepoDetailViewProps> = ({
  repo,
  onBack,
  onResync,
}) => {
  const [currentRepo, setCurrentRepo] = useState<Repository>(repo);
  const [activeTab, setActiveTab] = useState<TabType>("commits");
  const [syncJob, setSyncJob] = useState<SyncJob | null>(null);

  // Indexing State
  const [indexJob, setIndexJob] = useState<IndexJob | null>(null);
  const [isTriggeringIndex, setIsTriggeringIndex] = useState<boolean>(false);
  const [indexError, setIndexError] = useState<string | null>(null);

  // Search State
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [searchMode, setSearchMode] = useState<SearchMode>("hybrid");
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

  // Issues State
  const [issues, setIssues] = useState<Issue[]>([]);
  const [issuesLoading, setIssuesLoading] = useState<boolean>(false);
  const [issueStateFilter, setIssueStateFilter] = useState<string>("all");
  const [issueAuthorFilter, setIssueAuthorFilter] = useState<string>("");

  useEffect(() => {
    setCurrentRepo(repo);
  }, [repo]);

  // Fetch sync status if repo is pending or syncing
  useEffect(() => {
    let timer: any = null;
    const fetchStatus = async () => {
      try {
        const res = await fetch(`/repos/${repo.id}/sync-status`);
        if (res.ok) {
          const data: SyncJob = await res.json();
          setSyncJob(data);
        }
      } catch (err) {
        console.error("Failed to load sync status:", err);
      }
    };

    fetchStatus();
    if (repo.status === "syncing" || repo.status === "pending") {
      timer = setInterval(fetchStatus, 2500);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [repo.id, repo.status]);

  // Fetch and poll index status if indexing is active
  useEffect(() => {
    let timer: any = null;
    const fetchIndexStatus = async () => {
      try {
        const res = await fetch(`/repos/${currentRepo.id}/index-status`);
        if (res.ok) {
          const data: IndexJob = await res.json();
          setIndexJob(data);
          if (data.status === "completed") {
            setCurrentRepo((prev) => ({
              ...prev,
              index_status: "ready",
              chunk_count: data.stats?.total_chunks ?? prev.chunk_count,
            }));
          } else if (data.status === "failed") {
            setCurrentRepo((prev) => ({
              ...prev,
              index_status: "failed",
            }));
            setIndexError(data.error || "Indexing failed");
          }
        }
      } catch (err) {
        console.error("Failed to load index status:", err);
      }
    };

    fetchIndexStatus();
    if (currentRepo.index_status === "indexing" || (indexJob && indexJob.status === "running")) {
      timer = setInterval(fetchIndexStatus, 2000);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [currentRepo.id, currentRepo.index_status, indexJob?.status]);

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
  }, [repo.id, activeTab, commitAuthorFilter]);

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
  }, [repo.id, activeTab, prStateFilter, prAuthorFilter]);

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
  }, [repo.id, activeTab, issueStateFilter, issueAuthorFilter]);

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
            <span
              className={`badge badge-${
                currentRepo.status === "ready"
                  ? "success"
                  : currentRepo.status === "failed"
                  ? "danger"
                  : "warning"
              }`}
            >
              <span
                className={`badge-dot ${
                  currentRepo.status === "syncing" || currentRepo.status === "pending" ? "pulse-dot" : ""
                }`}
              />
              SYNC: {currentRepo.status.toUpperCase()}
            </span>

            {/* Index Status Badge */}
            <span
              className={`badge badge-${
                currentRepo.index_status === "ready"
                  ? "success"
                  : currentRepo.index_status === "failed"
                  ? "danger"
                  : currentRepo.index_status === "indexing"
                  ? "warning"
                  : "outline"
              }`}
              style={
                !currentRepo.index_status || currentRepo.index_status === "none"
                  ? { background: "rgba(255, 255, 255, 0.06)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }
                  : {}
              }
            >
              <span
                className={`badge-dot ${
                  currentRepo.index_status === "indexing" ? "pulse-dot" : ""
                }`}
              />
              {currentRepo.index_status === "ready"
                ? `INDEXED (${currentRepo.chunk_count || 0})`
                : currentRepo.index_status === "indexing"
                ? "INDEXING..."
                : currentRepo.index_status === "failed"
                ? "INDEX FAILED"
                : "NOT INDEXED"}
            </span>
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
            disabled={currentRepo.index_status === "indexing" || isTriggeringIndex}
            className="btn btn-outline"
            style={{ padding: "0.55rem 1.2rem", fontSize: "0.85rem", display: "inline-flex", alignItems: "center", gap: "0.45rem" }}
          >
            {currentRepo.index_status === "indexing" ? (
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
            onClick={() => onResync(currentRepo.id)}
            disabled={currentRepo.status === "syncing" || currentRepo.status === "pending"}
            className="btn btn-primary"
            style={{ padding: "0.55rem 1.2rem", fontSize: "0.85rem" }}
          >
            {currentRepo.status === "syncing" ? "Syncing..." : "Re-sync Repository"}
          </button>
        </div>
      </div>

      {/* Sync Status Banner */}
      {(currentRepo.status === "syncing" || currentRepo.status === "pending" || (syncJob && syncJob.status === "running")) && (
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
          <div style={{ width: "100%", height: "6px", background: "rgba(255, 255, 255, 0.1)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
            <div
              style={{
                width: `${syncJob?.progress || 0}%`,
                height: "100%",
                background: "var(--accent-gradient)",
                transition: "width 0.4s ease",
              }}
            />
          </div>
        </div>
      )}

      {/* Index Status Banner */}
      {(currentRepo.index_status === "indexing" || (indexJob && indexJob.status === "running")) && (
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
          <div style={{ width: "100%", height: "6px", background: "rgba(255, 255, 255, 0.1)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
            <div
              style={{
                width: `${indexJob?.progress || 0}%`,
                height: "100%",
                background: "var(--accent-gradient)",
                transition: "width 0.4s ease",
              }}
            />
          </div>
        </div>
      )}

      {/* Sync Error Banner */}
      {currentRepo.status === "failed" && currentRepo.sync_error && (
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
          <strong>Sync Failed:</strong> {currentRepo.sync_error}
        </div>
      )}

      {/* Index Error Banner */}
      {currentRepo.index_status === "failed" && (indexError || indexJob?.error) && (
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
          <strong>Indexing Failed:</strong> {indexError || indexJob?.error}
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
      {activeTab === "pulls" && (
        <div className="glass-card" style={{ padding: "1.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 600 }}>Pull Requests ({prs.length})</h2>
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <select
                value={prStateFilter}
                onChange={(e) => setPrStateFilter(e.target.value)}
                className="search-input"
                style={{ padding: "0.45rem 0.75rem", cursor: "pointer" }}
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
                style={{ maxWidth: "200px" }}
              />
            </div>
          </div>

          {prsLoading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              <div className="spinner" style={{ margin: "0 auto 1rem" }} />
              Loading pull requests...
            </div>
          ) : prs.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.9rem" }}>
              {repo.status === "pending" || repo.status === "syncing"
                ? "Sync in progress. Pull requests will appear here once ingested."
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
                    <th>Author</th>
                    <th>Branches</th>
                    <th>Created</th>
                    <th style={{ textAlign: "right" }}>Changes</th>
                  </tr>
                </thead>
                <tbody>
                  {prs.map((p) => (
                    <tr key={p.id}>
                      <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                        #{p.number}
                      </td>
                      <td style={{ fontWeight: 500, maxWidth: "340px" }}>
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
                      <td style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                        {p.author_login ? `@${p.author_login}` : "Unknown"}
                      </td>
                      <td style={{ fontSize: "0.78rem", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                        {p.head_ref || "?"} → {p.base_ref || "main"}
                      </td>
                      <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                        {new Date(p.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ textAlign: "right", fontSize: "0.82rem", fontFamily: "var(--font-mono)" }}>
                        {p.additions !== null && (
                          <span style={{ color: "var(--success)", marginRight: "0.4rem" }}>
                            +{p.additions}
                          </span>
                        )}
                        {p.deletions !== null && (
                          <span style={{ color: "var(--danger)" }}>
                            -{p.deletions}
                          </span>
                        )}
                        {p.additions === null && p.deletions === null && (
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

      {/* Tab 3: Issues */}
      {activeTab === "issues" && (
        <div className="glass-card" style={{ padding: "1.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 600 }}>Issues (Excluding PRs) ({issues.length})</h2>
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <select
                value={issueStateFilter}
                onChange={(e) => setIssueStateFilter(e.target.value)}
                className="search-input"
                style={{ padding: "0.45rem 0.75rem", cursor: "pointer" }}
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
                style={{ maxWidth: "200px" }}
              />
            </div>
          </div>

          {issuesLoading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              <div className="spinner" style={{ margin: "0 auto 1rem" }} />
              Loading issues...
            </div>
          ) : issues.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.9rem" }}>
              {repo.status === "pending" || repo.status === "syncing"
                ? "Sync in progress. Issues will appear here once ingested."
                : "No issues found."}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Title & Labels</th>
                    <th>State</th>
                    <th>Author</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.map((i) => (
                    <tr key={i.id}>
                      <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                        #{i.number}
                      </td>
                      <td style={{ maxWidth: "420px" }}>
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
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

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

              {/* Mode Toggle Pills */}
              <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap", fontSize: "0.88rem" }}>
                <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>Search Mode:</span>
                <div style={{ display: "flex", background: "rgba(255, 255, 255, 0.04)", padding: "0.25rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-color)", gap: "0.25rem" }}>
                  <button
                    type="button"
                    onClick={() => setSearchMode("hybrid")}
                    style={{
                      background: searchMode === "hybrid" ? "var(--accent-primary)" : "transparent",
                      color: searchMode === "hybrid" ? "#fff" : "var(--text-secondary)",
                      border: "none",
                      padding: "0.35rem 0.85rem",
                      borderRadius: "var(--radius-sm)",
                      cursor: "pointer",
                      fontSize: "0.82rem",
                      fontWeight: 600,
                      transition: "all var(--transition-fast)",
                    }}
                  >
                    Hybrid (Semantic + Keyword)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSearchMode("semantic")}
                    style={{
                      background: searchMode === "semantic" ? "var(--accent-primary)" : "transparent",
                      color: searchMode === "semantic" ? "#fff" : "var(--text-secondary)",
                      border: "none",
                      padding: "0.35rem 0.85rem",
                      borderRadius: "var(--radius-sm)",
                      cursor: "pointer",
                      fontSize: "0.82rem",
                      fontWeight: 600,
                      transition: "all var(--transition-fast)",
                    }}
                  >
                    Semantic (Vector Cosine)
                  </button>
                  <button
                    type="button"
                    onClick={() => setSearchMode("keyword")}
                    style={{
                      background: searchMode === "keyword" ? "var(--accent-primary)" : "transparent",
                      color: searchMode === "keyword" ? "#fff" : "var(--text-secondary)",
                      border: "none",
                      padding: "0.35rem 0.85rem",
                      borderRadius: "var(--radius-sm)",
                      cursor: "pointer",
                      fontSize: "0.82rem",
                      fontWeight: 600,
                      transition: "all var(--transition-fast)",
                    }}
                  >
                    Keyword (Full-Text)
                  </button>
                </div>
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
              Searching codebase across {searchMode} index...
            </div>
          )}

          {/* Empty Results */}
          {!searchLoading && hasSearched && searchResults.length === 0 && !searchError && (
            <div className="glass-card" style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              <p style={{ fontSize: "1rem", marginBottom: "0.5rem", color: "var(--text-primary)" }}>
                No code results found
              </p>
              <p style={{ fontSize: "0.85rem" }}>
                Try tweaking your search terms, choosing another mode (e.g. Keyword vs Semantic), or re-indexing.
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
    </div>
  );
};
