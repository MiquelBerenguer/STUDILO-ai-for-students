import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { post } from "../api";
import { ErrorBox } from "../components/ui";
import type { Me } from "../types";
import { BRAND } from "../brand";

export default function Auth({ mode }: { mode: "login" | "register" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = mode === "login"
        ? await post<Me>("/auth/login", { email, password })
        : await post<Me>("/auth/register", { email, password, display_name: name });
      qc.clear();
      qc.setQueryData(["me"], me);
      navigate(me.journey_state === "onboarding" ? "/onboarding" : params.get("next") || "/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-indigo-700">{BRAND.name}</h1>
          <p className="text-sm text-slate-500">
            {mode === "login" ? "Welcome back." : "Your second student for every course."}
          </p>
        </div>
        {mode === "register" && (
          <div>
            <label className="label" htmlFor="name">Name</label>
            <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        )}
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" required className="input" value={email}
            onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" type="password" required minLength={mode === "register" ? 8 : 1} className="input"
            value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"} />
          {mode === "register" && <p className="mt-1 text-xs text-slate-400">At least 8 characters.</p>}
        </div>
        <ErrorBox error={error} />
        <button className="btn-primary w-full" disabled={busy}>
          {mode === "login" ? "Log in" : "Create account"}
        </button>
        <p className="text-center text-sm text-slate-500">
          {mode === "login" ? (
            <>No account? <Link className="text-indigo-600" to="/register">Register</Link></>
          ) : (
            <>Already registered? <Link className="text-indigo-600" to="/login">Log in</Link></>
          )}
        </p>
      </form>
    </div>
  );
}
