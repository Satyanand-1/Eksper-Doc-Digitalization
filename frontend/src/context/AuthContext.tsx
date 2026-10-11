"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { UserProfile } from "@/types/notification";
import { api, getStoredToken, setStoredToken, clearStoredToken } from "@/lib/api";

interface AuthContextType {
  user: UserProfile | null;
  token: string | null;
  loading: boolean;
  login: (token: string) => Promise<void>;
  loginWithCredentials: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  loading: true,
  login: async () => {},
  loginWithCredentials: async () => {},
  logout: () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchProfile = useCallback(async () => {
    try {
      const profile = await api.getCurrentUser();
      setUser(profile);
    } catch {
      setUser(null);
      clearStoredToken();
      setToken(null);
    }
  }, []);

  useEffect(() => {
    const stored = getStoredToken();
    if (stored) {
      setToken(stored);
      fetchProfile().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [fetchProfile]);

  const login = async (newToken: string) => {
    setStoredToken(newToken);
    setToken(newToken);
    setLoading(true);
    await fetchProfile();
    setLoading(false);
  };

  const loginWithCredentials = async (email: string, password: string) => {
    setLoading(true);
    const res = await api.loginWithCredentials(email, password);
    setStoredToken(res.access_token);
    setToken(res.access_token);
    await fetchProfile();
    setLoading(false);
  };

  const logout = () => {
    clearStoredToken();
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        login,
        loginWithCredentials,
        logout,
        refreshUser: fetchProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
