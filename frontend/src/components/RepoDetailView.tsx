import React, { useEffect, useState } from "react";
import { Commit, Issue, PullRequest, Repository, SyncJob } from "../types";

interface RepoDetailViewProps {
  repo: Repository;
  onBack: () => void;
  onResync: (repoId: string) => void;
}

type TabType = "commits" | "pulls" | "issues";

export const RepoDetailView: React.FC<RepoDetailViewProps> = ({
  repo,
  onBack,
  onResync,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>("commits");
  const [syncJob, setSyncJob] = useState<SyncJob | null>(null);

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
            <span
              className={`badge badge-${
                repo.status === "ready"
                  ? "success"
                  : repo.status === "failed"
                  ? "danger"
                  : "warning"
              }`}
            >
              <span
                className={`badge-dot ${
                  repo.status === "syncing" || repo.status === "pending" ? "pulse-dot" : ""
                }`}
              />
              {repo.status.toUpperCase()}
            </span>
          </div>

          {repo.description && (
            <p style={{ color: "var(--text-secondary)", fontSize: "0.92rem", marginTop: "0.4rem" }}>
              {repo.description}
            </p>
          )}

          <div style={{ display: "flex", gap: "1.25rem", marginTop: "0.75rem", fontSize: "0.82rem", color: "var(--text-muted)" }}>
            <span>Default branch: <strong style={{ color: "var(--text-primary)" }}>{repo.default_branch}</strong></span>
            {repo.language && (
              <span>Language: <strong style={{ color: "var(--text-primary)" }}>{repo.language}</strong></span>
            )}
            <span>
              Last synced:{" "}
              <strong style={{ color: "var(--text-primary)" }}>
                {repo.last_synced_at ? new Date(repo.last_synced_at).toLocaleString() : "Never"}
              </strong>
            </span>
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            onClick={() => onResync(repo.id)}
            disabled={repo.status === "syncing" || repo.status === "pending"}
            className="btn btn-primary"
            style={{ padding: "0.55rem 1.2rem", fontSize: "0.85rem" }}
          >
            {repo.status === "syncing" ? "Syncing..." : "Re-sync Repository"}
          </button>
        </div>
      </div>

      {/* Sync Status Banner */}
      {(repo.status === "syncing" || repo.status === "pending" || (syncJob && syncJob.status === "running")) && (
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

      {/* Sync Error Banner */}
      {repo.status === "failed" && repo.sync_error && (
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
          <strong>Sync Failed:</strong> {repo.sync_error}
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
    </div>
  );
};
