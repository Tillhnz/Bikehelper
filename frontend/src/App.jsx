import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, clearToken, getToken, setUnauthorizedHandler } from "./api.js";
import { resetMapConfig } from "./geo.js";
import WhatsNew from "./components/WhatsNew.jsx";
import Tour from "./components/Tour.jsx";
import Shell from "./components/Shell.jsx";
import { ErrorBoundary, FeedbackHost } from "./components/feedback.jsx";
import { resetUploads, resumeActive } from "./uploads.js";
import Admin from "./pages/Admin.jsx";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Garage from "./pages/Garage.jsx";
import BikeDetail from "./pages/BikeDetail.jsx";
import Inventory from "./pages/Inventory.jsx";
import Rides from "./pages/Rides.jsx";
import Advisor from "./pages/Advisor.jsx";
import RideDetail from "./pages/RideDetail.jsx";
import Stats from "./pages/Stats.jsx";
import Settings from "./pages/Settings.jsx";
import Groups, { GroupDetail, GroupJoin, pendingGroupToken } from "./pages/Groups.jsx";

/** Einladungslink ohne Anmeldung: Schlüssel merken, anmelden lassen, danach weiter zur Einladung. */
function RememberInvite() {
  const { token } = useParams();
  pendingGroupToken.set(token);
  return <Navigate to="/login" replace />;
}

export default function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!getToken());

  const logout = useCallback(() => {
    clearToken();
    resetMapConfig();
    resetUploads();
    setUser(null);
    navigate("/login");
  }, [navigate]);

  const loadUser = useCallback(async () => {
    try {
      setUser(await api.get("/me"));
      resumeActive();
      const pending = pendingGroupToken.get();
      if (pending) navigate(`/groups/join/${pending}`);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      navigate("/login");
    });
    if (getToken()) loadUser();
  }, [loadUser, navigate]);

  if (loading) return <div className="center muted">Lade …</div>;

  if (!user) {
    return (
      <>
      <FeedbackHost />
      <Routes>
        <Route path="/login" element={<Login onLoggedIn={loadUser} />} />
        <Route path="/groups/join/:token" element={<RememberInvite />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      </>
    );
  }

  return (
    <Shell user={user} onLogout={logout}>
      <FeedbackHost />
      {user.tour && <Tour onClose={() => setUser((u) => ({ ...u, tour: false }))} />}
      <WhatsNew user={user} onClose={() => setUser((u) => ({ ...u, whatsnew: null }))} />
      <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/garage" element={<Garage user={user} />} />
        <Route path="/mechanic" element={<Navigate to="/garage" replace />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/bikes/:id" element={<BikeDetail />} />
        <Route path="/advisor" element={<Advisor />} />
        <Route path="/rides" element={<Rides />} />
        <Route path="/rides/:id" element={<RideDetail />} />
        <Route path="/heatmap" element={<Navigate to="/stats?tab=heatmap" replace />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/groups" element={<Groups />} />
        <Route path="/groups/join/:token" element={<GroupJoin />} />
        <Route path="/groups/:id" element={<GroupDetail />} />
        {user.role === "admin" && <Route path="/admin" element={<Admin user={user} />} />}
        <Route path="/settings" element={<Settings user={user} onChange={setUser} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </ErrorBoundary>
    </Shell>
  );
}
