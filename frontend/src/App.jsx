import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, clearToken, getToken, setUnauthorizedHandler } from "./api.js";
import Login from "./pages/Login.jsx";
import Garage from "./pages/Garage.jsx";
import BikeDetail from "./pages/BikeDetail.jsx";
import Rides from "./pages/Rides.jsx";
import Settings from "./pages/Settings.jsx";

function Shell({ user, onLogout, children }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          BikeHelper
        </div>
        <nav>
          <NavLink to="/" end>Garage</NavLink>
          <NavLink to="/rides">Fahrten</NavLink>
          <NavLink to="/settings">Einstellungen</NavLink>
        </nav>
        <div className="sidebar-foot">
          <span className="muted small">{user.email}</span>
          <button className="link" onClick={onLogout}>Abmelden</button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

export default function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!getToken());

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    navigate("/login");
  }, [navigate]);

  const loadUser = useCallback(async () => {
    try {
      setUser(await api.get("/me"));
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
        <Route path="/" element={<Garage />} />
        <Route path="/bikes/:id" element={<BikeDetail />} />
        <Route path="/rides" element={<Rides />} />
        <Route path="/settings" element={<Settings user={user} onChange={setUser} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
