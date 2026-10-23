import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, clearToken, getToken, setUnauthorizedHandler } from "./api.js";
import { resetMapConfig } from "./geo.js";
import Shell from "./components/Shell.jsx";
import { resetUploads, resumeActive } from "./uploads.js";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Garage from "./pages/Garage.jsx";
import BikeDetail from "./pages/BikeDetail.jsx";
import Rides from "./pages/Rides.jsx";
import Advisor from "./pages/Advisor.jsx";
import RideDetail from "./pages/RideDetail.jsx";
import Heatmap from "./pages/Heatmap.jsx";
import Stats from "./pages/Stats.jsx";
import Settings from "./pages/Settings.jsx";

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
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

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
      <Routes>
        <Route path="/login" element={<Login onLoggedIn={loadUser} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Shell user={user} onLogout={logout}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/garage" element={<Garage />} />
        <Route path="/bikes/:id" element={<BikeDetail />} />
        <Route path="/advisor" element={<Advisor />} />
        <Route path="/rides" element={<Rides />} />
        <Route path="/rides/:id" element={<RideDetail />} />
        <Route path="/heatmap" element={<Heatmap />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/settings" element={<Settings user={user} onChange={setUser} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
