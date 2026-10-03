import React, { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { HealthStatus, Repository } from "../types";
import { RepoListView } from "./RepoListView";
import { RepoDetailView } from "./RepoDetailView";

export const DashboardView: React.FC = () => {
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch("/health");
        if (res.ok) {
          const data: HealthStatus = await res.json();
          setHealth(data);
        }
      } catch (err) {
        console.error("Health fetch error:", err);
      } finally {
        setHealthLoading(false);
      }
    };
    fetchHealth();
  }, []);

  const handleResyncRepo = async (repoId: string) => {
    try {
      const res = await fetch(`/repos/${repoId}/sync`, { method: "POST" });
      if (res.ok) {
        if (selectedRepo && selectedRepo.id === repoId) {
          setSelectedRepo({ ...selectedRepo, status: "pending", sync_error: null });
        }
      }
    } catch (err) {
      console.error("Failed to trigger re-sync:", err);
    }
  };

  if (!user) {
    return null;
  }

  const defaultAvatar = `https://ui-avatars.com/api/?name=${encodeURIComponent(user.login)}&background=6366f1&color=fff`;

  return (
    <div style={{ maxWidth: "1180px", margin: "2rem auto", padding: "0 1.5rem", width: "100%", display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Top Banner / Welcome */}
      <div
        className="glass-card"
        style={{
          padding: "1.5rem 2rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1.5rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1.25rem" }}>
          <img
            src={user.avatar_url || defaultAvatar}
            alt={user.login}
            style={{
              width: "60px",
              height: "60px",
              borderRadius: "50%",
              border: "3px solid rgba(99, 102, 241, 0.4)",
              boxShadow: "var(--shadow-md)",
            }}
          />
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.2rem" }}>
              <h1 style={{ fontSize: "1.35rem", fontWeight: 700 }}>
                {user.name || user.login}
              </h1>
              <span className="badge badge-success">
                <span className="badge-dot pulse-dot" />
                Active Session
              </span>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem" }}>
              @{user.login} &bull; {user.email || "No public email"}
            </p>
          </div>
        </div>

        <div>
          <button
            onClick={logout}
            id="dashboard-logout-button"
            className="btn btn-outline btn-logout"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Sign Out
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {selectedRepo ? (
        <RepoDetailView
          repo={selectedRepo}
          onBack={() => setSelectedRepo(null)}
          onResync={handleResyncRepo}
        />
      ) : (
        <>
          {/* Repository List Section */}
          <RepoListView onSelectRepo={(repo) => setSelectedRepo(repo)} />

          {/* Infrastructure Health Summary (Phase 1 + 2) */}
          <div className="grid-2" style={{ marginTop: "1rem" }}>
            <div className="glass-card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                Identity &amp; Security
              </h2>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.85rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>GitHub ID</span>
                  <span style={{ fontFamily: "var(--font-mono)" }}>{user.github_id}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>Token Security</span>
                  <span style={{ color: "var(--success)" }}>Fernet AES-128-CBC Encrypted</span>
                </div>
              </div>
            </div>

            <div className="glass-card" style={{ padding: "1.5rem" }}>
              <h2 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2">
                  <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
                  <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
                  <line x1="6" y1="6" x2="6.01" y2="6" />
                  <line x1="6" y1="18" x2="6.01" y2="18" />
                </svg>
                Backend Services Health
              </h2>
              {healthLoading ? (
                <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Checking services...</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.85rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-muted)" }}>PostgreSQL + pgvector</span>
                    <span style={{ color: health?.database === "connected" ? "var(--success)" : "var(--danger)" }}>
                      {health?.database === "connected" ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-muted)" }}>Redis / ARQ Worker Queue</span>
                    <span style={{ color: health?.redis === "connected" ? "var(--success)" : "var(--danger)" }}>
                      {health?.redis === "connected" ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

