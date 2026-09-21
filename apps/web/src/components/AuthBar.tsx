"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthProvider";

export default function AuthBar() {
  const { configured, loading, user, points, signInWithGoogle, signOut } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const name = user?.user_metadata?.full_name ?? user?.user_metadata?.name ?? user?.email ?? "AllerNav diner";

  const run = async (action: () => Promise<void>) => {
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Login is temporarily unavailable.");
    }
  };

  return (
    <section className="auth-bar" aria-label="AllerNav account">
      {user ? (
        <>
          <div className="auth-user-copy">
            <strong>{name}</strong>
            <span>{points} point{points === 1 ? "" : "s"}</span>
          </div>
          <button type="button" onClick={() => void run(signOut)}>
            Sign out
          </button>
        </>
      ) : (
        <>
          <div className="auth-user-copy">
            <strong>{loading ? "Checking account…" : "Earn review points"}</strong>
            <span>Browsing stays open to everyone.</span>
          </div>
          <button type="button" disabled={loading || !configured} onClick={() => void run(signInWithGoogle)}>
            Continue with Google
          </button>
        </>
      )}
      {error && <p>{error}</p>}
    </section>
  );
}
