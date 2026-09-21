"use client";

import type { Session, User } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabaseBrowser";

interface AuthContextValue {
  configured: boolean;
  loading: boolean;
  session: Session | null;
  user: User | null;
  points: number;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  refreshPoints: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export default function AuthProvider({ children }: { children: ReactNode }) {
  const client = useMemo(() => getSupabaseBrowserClient(), []);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(Boolean(client));
  const [points, setPoints] = useState(0);

  const refreshPoints = useCallback(async () => {
    const accessToken = session?.access_token;
    if (!accessToken) {
      setPoints(0);
      return;
    }
    const response = await fetch("/api/community/profile", {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    });
    if (!response.ok) {
      return;
    }
    const body = (await response.json()) as { total_points?: number };
    setPoints(typeof body.total_points === "number" ? body.total_points : 0);
  }, [session?.access_token]);

  useEffect(() => {
    if (!client) {
      setLoading(false);
      return;
    }

    let active = true;
    void client.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session);
        setLoading(false);
      }
    });
    const { data: listener } = client.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, [client]);

  useEffect(() => {
    void refreshPoints();
  }, [refreshPoints]);

  const signInWithGoogle = useCallback(async () => {
    if (!client) {
      throw new Error("Google login is not configured yet.");
    }
    const { error } = await client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (error) {
      throw error;
    }
  }, [client]);

  const signOut = useCallback(async () => {
    if (!client) {
      return;
    }
    const { error } = await client.auth.signOut();
    if (error) {
      throw error;
    }
    setPoints(0);
  }, [client]);

  const value = useMemo<AuthContextValue>(() => ({
    configured: Boolean(client),
    loading,
    session,
    user: session?.user ?? null,
    points,
    signInWithGoogle,
    signOut,
    refreshPoints,
  }), [client, loading, points, refreshPoints, session, signInWithGoogle, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return value;
}
