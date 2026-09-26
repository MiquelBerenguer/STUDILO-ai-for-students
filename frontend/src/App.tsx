import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { ApiError, get } from "./api";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import Activity from "./pages/Activity";
import Auth from "./pages/Auth";
import ExamPackPage from "./pages/ExamPack";
import Exams from "./pages/Exams";
import Courses from "./pages/Courses";
import Feed from "./pages/Feed";
import Onboarding from "./pages/Onboarding";
import Schedule from "./pages/Schedule";
import Settings from "./pages/Settings";
import Subject from "./pages/Subject";
import UploadPage from "./pages/Upload";
import type { Me } from "./types";

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await get<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

export default function App() {
  const { data: me, isLoading } = useMe();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const onUnauthorized = () => {
      qc.setQueryData(["me"], null);
      navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
    };
    window.addEventListener("app:unauthorized", onUnauthorized);
    return () => window.removeEventListener("app:unauthorized", onUnauthorized);
  }, [qc, navigate, location]);

  if (isLoading) {
    return <div className="flex h-screen items-center justify-center"><Spinner /></div>;
  }
  // Landing = onboarding step 1 ("Drop your timetable"): no registration wall (UX.md §8).
  if (!me || me.journey_state === "onboarding") {
    return (
      <Routes>
        <Route path="/login" element={<Auth mode="login" />} />
        <Route path="/register" element={<Auth mode="register" />} />
        <Route path="/" element={<Onboarding me={me ?? null} />} />
        <Route path="*" element={<Navigate to={me ? "/" : `/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<Layout me={me} />}>
        <Route path="/" element={<Feed />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/courses" element={<Courses />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/subjects/:courseId" element={<Subject />} />
        <Route path="/exams" element={<Exams />} />
        <Route path="/packs/:packId" element={<ExamPackPage />} />
        <Route path="/activity" element={<Activity />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/register" element={<Navigate to="/" replace />} />
        <Route path="/onboarding" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export function NotFound() {
  return (
    <div className="card mx-auto mt-10 max-w-md text-center">
      <p className="font-semibold">Not found</p>
      <p className="mt-1 text-sm text-slate-500">This page doesn't exist or isn't yours.</p>
      <a href="/" className="btn-secondary mt-4">Back to the feed</a>
    </div>
  );
}
