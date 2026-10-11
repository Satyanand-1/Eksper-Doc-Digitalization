"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "./AuthContext";

interface NotificationContextType {
  unreadCount: number;
  refreshUnreadCount: () => Promise<void>;
  decrementUnreadCount: () => void;
}

const NotificationContext = createContext<NotificationContextType>({
  unreadCount: 0,
  refreshUnreadCount: async () => {},
  decrementUnreadCount: () => {},
});

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const { user, token } = useAuth();
  const [unreadCount, setUnreadCount] = useState<number>(0);

  const refreshUnreadCount = useCallback(async () => {
    if (!token || !user) {
      setUnreadCount(0);
      return;
    }
    try {
      const res = await api.getUnreadCount();
      setUnreadCount(res.unread_count);
    } catch {
      // Graceful fallback on network or session error
    }
  }, [token, user]);

  useEffect(() => {
    if (token && user) {
      refreshUnreadCount();
    } else {
      setUnreadCount(0);
    }
  }, [token, user, refreshUnreadCount]);

  const decrementUnreadCount = () => {
    setUnreadCount((prev) => Math.max(0, prev - 1));
  };

  return (
    <NotificationContext.Provider
      value={{
        unreadCount,
        refreshUnreadCount,
        decrementUnreadCount,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotificationContext() {
  return useContext(NotificationContext);
}
