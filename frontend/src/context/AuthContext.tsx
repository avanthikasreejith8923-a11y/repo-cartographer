import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { User } from "../types";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCurrentUser = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch("/auth/me", {
        credentials: "include",
        headers: {
          Accept: "application/json",
        },
      });

      if (response.ok) {
        const data: User = await response.json();
        setUser(data);
      } else if (response.status === 401) {
        setUser(null);
      } else {
        setError(`Failed to fetch user state (${response.status})`);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Network error checking session";
      setError(message);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  const login = () => {
    // Initiate GitHub OAuth flow via backend redirect
    window.location.href = "/auth/github/login";
  };

  const logout = async () => {
    try {
      setLoading(true);
      await fetch("/auth/logout", {
        method: "POST",
        credentials: "include",
      });
      setUser(null);
      // Clean query params if any
      if (window.location.search) {
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    } catch (err: unknown) {
      console.error("Logout error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        login,
        logout,
        refreshUser: fetchCurrentUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
