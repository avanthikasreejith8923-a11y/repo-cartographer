import React, { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { HealthStatus } from "../types";

export const DashboardView: React.FC = () => {
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);

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

  if (!user) {
    return null;
  }

  const defaultAvatar = `https://ui-avatars.com/api/?name=${encodeURIComponent(user.login)}&background=6366f1&color=fff`;

  return (
    <div style={{ maxWidth: "1100px", margin: "2rem auto", padding: "0 1.5rem", width: "100%" }}>
      {/* Top Banner / Welcome */}
      <div
        className="glass-card"
        style={{
          padding: "2rem",
          marginBottom: "2rem",
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
              width: "72px",
              height: "72px",
              borderRadius: "50%",
              border: "3px solid rgba(99, 102, 241, 0.4)",
              boxShadow: "var(--shadow-md)",
            }}
          />
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.25rem" }}>
              <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>
                {user.name || user.login}
              </h1>
              <span className="badge badge-success">
                <span className="badge-dot pulse-dot" />
                Active Session
              </span>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
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

      {/* Grid of Status & Information Cards */}
      <div className="grid-2">
        {/* User Identity Card */}
        <div className="glass-card" style={{ padding: "1.75rem" }}>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: "1.25rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            Authenticated Identity
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", fontSize: "0.9rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
              <span style={{ color: "var(--text-muted)" }}>GitHub ID</span>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>{user.github_id}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
              <span style={{ color: "var(--text-muted)" }}>Internal UUID</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: "var(--text-primary)" }}>{user.id}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
              <span style={{ color: "var(--text-muted)" }}>Token Encryption</span>
              <span style={{ color: "var(--success)", fontWeight: 500 }}>Fernet (AES-128-CBC)</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
              <span style={{ color: "var(--text-muted)" }}>Session Storage</span>
              <span style={{ color: "#a5b4fc" }}>httpOnly, SameSite=Lax Cookie</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-muted)" }}>First Authenticated</span>
              <span style={{ color: "var(--text-secondary)" }}>{new Date(user.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        </div>

        {/* Infrastructure & Phase 1 Health Card */}
        <div className="glass-card" style={{ padding: "1.75rem" }}>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: "1.25rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2">
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
              <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
              <line x1="6" y1="6" x2="6.01" y2="6" />
              <line x1="6" y1="18" x2="6.01" y2="18" />
            </svg>
            Phase 1 Services Health
          </h2>
          {healthLoading ? (
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", color: "var(--text-muted)" }}>
              <div className="spinner" style={{ width: "20px", height: "20px", borderWidth: "2px" }} />
              Checking infrastructure connectivity...
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", fontSize: "0.9rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
                <span style={{ color: "var(--text-muted)" }}>PostgreSQL + pgvector</span>
                <span style={{ color: health?.database === "connected" ? "var(--success)" : "var(--danger)", fontWeight: 600 }}>
                  {health?.database === "connected" ? "Connected (pg16 + vector)" : "Disconnected"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
                <span style={{ color: "var(--text-muted)" }}>Redis Cache / Queue</span>
                <span style={{ color: health?.redis === "connected" ? "var(--success)" : "var(--danger)", fontWeight: 600 }}>
                  {health?.redis === "connected" ? "Connected (Redis 7)" : "Disconnected"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
                <span style={{ color: "var(--text-muted)" }}>Alembic Migrations</span>
                <span style={{ color: "var(--success)", fontWeight: 500 }}>0001_initial_schema (Applied)</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Next Milestone</span>
                <span style={{ color: "#ec4899", fontWeight: 600 }}>Phase 2: Repository Ingestion</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
