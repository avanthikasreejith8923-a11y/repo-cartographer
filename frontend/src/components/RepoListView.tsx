import React, { useEffect, useState } from "react";
import { Repository } from "../types";
import { ImportRepoModal } from "./ImportRepoModal";

interface RepoListViewProps {
  onSelectRepo: (repo: Repository) => void;
}

export const RepoListView: React.FC<RepoListViewProps> = ({ onSelectRepo }) => {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [resyncingId, setResyncingId] = useState<string | null>(null);

  const fetchRepos = async (showLoading: boolean = false) => {
    if (showLoading) setLoading(true);
    try {
      const res = await fetch("/repos");
      if (res.ok) {
        const data: Repository[] = await res.json();
        setRepos(data);
      } else {
        throw new Error(`Failed to load repositories (${res.status})`);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load repositories");
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepos(true);
  }, []);

  const hasActiveSync = repos.some(
    (r) => r.status === "pending" || r.status === "syncing"
  );

  // Poll while any repo is pending or syncing
  useEffect(() => {
    let interval: any = null;
    if (hasActiveSync) {
      interval = setInterval(() => {
        fetchRepos(false);
      }, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [hasActiveSync]);

  const handleResync = async (e: React.MouseEvent, repoId: string) => {
    e.stopPropagation();
    if (resyncingId) return;
    setResyncingId(repoId);
    try {
      const res = await fetch(`/repos/${repoId}/sync`, { method: "POST" });
      if (res.ok || res.status === 409) {
        // Immediate status update locally
        setRepos((prev) =>
          prev.map((r) => (r.id === repoId ? { ...r, status: "pending", sync_error: null } : r))
        );
      }
    } catch (err) {
      console.error("Failed to trigger re-sync:", err);
    } finally {
      setResyncingId(null);
    }
  };

  const handleDelete = async (e: React.MouseEvent, repo: Repository) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to remove '${repo.full_name}' and its synced data?`)) {
      return;
    }
    try {
      const res = await fetch(`/repos/${repo.id}`, { method: "DELETE" });
      if (res.ok) {
        setRepos((prev) => prev.filter((r) => r.id !== repo.id));
      }
    } catch (err) {
      console.error("Failed to delete repository:", err);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header with Import Button */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 700, letterSpacing: "-0.02em" }}>Tracked Repositories</h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
            Synchronize GitHub commits, pull requests, and issues with local cartography.
          </p>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          disabled={hasActiveSync}
          className="btn btn-primary"
          style={{
            padding: "0.65rem 1.35rem",
            fontSize: "0.9rem",
          }}
          title={hasActiveSync ? "Sync in progress. Please wait until sync finishes to import." : undefined}
        >
          {hasActiveSync ? "Sync in progress..." : "+ Import Repository"}
        </button>
      </div>

      {error && (
        <div
          className="glass-card"
          style={{
            padding: "0.85rem 1.25rem",
            background: "var(--status-err-bg)",
            border: "1px solid var(--status-err-border)",
            color: "var(--status-err-text)",
            fontSize: "0.88rem",
            fontWeight: 500,
          }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ padding: "4rem 2rem", textAlign: "center", color: "var(--text-muted)" }}>
          <div className="spinner" style={{ margin: "0 auto 1.25rem" }} />
          <p style={{ fontSize: "0.92rem" }}>Loading tracked repositories...</p>
        </div>
      ) : repos.length === 0 ? (
        <div
          className="glass-card"
          style={{
            padding: "4rem 2rem",
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "1.25rem",
          }}
        >
          <div
            style={{
              width: "60px",
              height: "60px",
              borderRadius: "50%",
              background: "rgba(124, 92, 255, 0.15)",
              border: "1px solid rgba(124, 92, 255, 0.35)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--aurora-cyan)",
              boxShadow: "0 4px 16px rgba(124, 92, 255, 0.25)",
            }}
          >
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
              <path d="M6 6h10" />
              <path d="M6 10h10" />
            </svg>
          </div>
          <div>
            <h3 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em" }}>No repositories imported yet</h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.92rem", maxWidth: "440px", margin: "0.5rem auto 0", lineHeight: 1.5 }}>
              Import a repository from your GitHub account to begin asynchronous ingestion of commits, pull requests, and issues.
            </p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            disabled={hasActiveSync}
            className="btn btn-primary"
            style={{ marginTop: "0.5rem" }}
          >
            {hasActiveSync ? "Sync in progress..." : "Import your first repository"}
          </button>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "1.5rem" }}>
          {repos.map((repo) => (
            <div
              key={repo.id}
              onClick={() => onSelectRepo(repo)}
              className="glass-card repo-card"
              style={{
                padding: "1.75rem",
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: "1.25rem",
              }}
            >
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", marginBottom: "0.6rem" }}>
                  <h3
                    style={{
                      fontSize: "1.1rem",
                      fontWeight: 700,
                      color: "var(--text-primary)",
                      letterSpacing: "-0.02em",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {repo.full_name}
                  </h3>
                  <div style={{ display: "flex", gap: "0.45rem", alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    {repo.index_status && repo.index_status !== "none" && (
                      <span
                        className={`badge badge-${
                          repo.index_status === "ready"
                            ? "success"
                            : (repo.chunk_count && repo.chunk_count > 0 && repo.index_status === "failed")
                            ? "partial"
                            : repo.index_status === "failed"
                            ? "danger"
                            : "warning"
                        }`}
                        style={{ fontSize: "0.72rem", flexShrink: 0 }}
                      >
                        <span className={`badge-dot ${repo.index_status === "indexing" ? "pulse-dot" : ""}`} />
                        {repo.index_status === "ready"
                          ? "Indexed"
                          : (repo.chunk_count && repo.chunk_count > 0 && repo.index_status === "failed")
                          ? "Partial"
                          : repo.index_status === "indexing"
                          ? "Indexing..."
                          : "Failed"}
                      </span>
                    )}
                    <span
                      className={`badge badge-${
                        repo.status === "ready"
                          ? "success"
                          : repo.status === "failed"
                          ? "danger"
                          : "warning"
                      }`}
                      style={{ fontSize: "0.72rem", flexShrink: 0 }}
                    >
                      <span
                        className={`badge-dot ${
                          repo.status === "syncing" || repo.status === "pending" ? "pulse-dot" : ""
                        }`}
                      />
                      {repo.status}
                    </span>
                  </div>
                </div>

                <p
                  style={{
                    color: "var(--text-secondary)",
                    fontSize: "0.88rem",
                    lineHeight: 1.5,
                    height: "2.8rem",
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}
                >
                  {repo.description || "No description provided."}
                </p>
                {repo.status === "failed" && repo.sync_error && (
                  <p style={{ color: "var(--status-err-text)", fontSize: "0.82rem", marginTop: "0.5rem", lineHeight: 1.4 }}>
                    ⚠️ {repo.sync_error}
                  </p>
                )}
              </div>

              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.8rem",
                    color: "var(--text-muted)",
                    borderTop: "1px solid var(--glass-border)",
                    paddingTop: "0.85rem",
                    marginBottom: "0.85rem",
                  }}
                >
                  <span>Branch: <strong style={{ color: "var(--text-primary)" }}>{repo.default_branch}</strong></span>
                  {repo.language && (
                    <span>Language: <strong style={{ color: "var(--text-primary)" }}>{repo.language}</strong></span>
                  )}
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                    {repo.last_synced_at
                      ? `Synced ${new Date(repo.last_synced_at).toLocaleDateString()}`
                      : "Not synced yet"}
                  </span>

                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      onClick={(e) => handleResync(e, repo.id)}
                      disabled={repo.status === "syncing" || repo.status === "pending" || resyncingId !== null}
                      className="btn btn-outline"
                      style={{ padding: "0.35rem 0.8rem", fontSize: "0.78rem" }}
                      title="Trigger Re-sync"
                    >
                      {repo.status === "syncing" || repo.status === "pending"
                        ? "Syncing..."
                        : resyncingId === repo.id
                        ? "Starting..."
                        : "Re-sync"}
                    </button>
                    <button
                      onClick={(e) => handleDelete(e, repo)}
                      className="btn btn-outline"
                      aria-label="Remove Repository"
                      style={{ padding: "0.35rem 0.8rem", fontSize: "0.78rem", color: "var(--status-err-text)" }}
                      title="Remove Repository"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Import Modal */}
      <ImportRepoModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onImportSuccess={() => fetchRepos(false)}
        isSyncInProgress={hasActiveSync}
      />
    </div>
  );
};
