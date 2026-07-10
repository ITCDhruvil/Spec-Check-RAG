"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import * as authApi from "@/lib/api/auth";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "@/lib/auth-storage";
import type { AuthUser, LoginResponse } from "@/lib/types/auth";

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  applySession: (data: LoginResponse) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setUser(null);
      return;
    }
    const me = await authApi.fetchCurrentUser();
    setUser(me);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const access = getAccessToken();
      const refresh = getRefreshToken();

      if (!access && !refresh) {
        if (!cancelled) {
          setUser(null);
          setLoading(false);
        }
        return;
      }

      try {
        if (access) {
          await refreshUser();
        } else if (refresh) {
          const { access: newAccess } = await authApi.refreshAccessToken(refresh);
          setTokens(newAccess, refresh);
          await refreshUser();
        }
      } catch {
        clearTokens();
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [refreshUser]);

  const applySession = useCallback((data: LoginResponse) => {
    setTokens(data.access, data.refresh);
    setUser(data.user);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await authApi.login(email, password);
    applySession(data);
  }, [applySession]);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, applySession, logout, refreshUser }),
    [user, loading, login, applySession, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
