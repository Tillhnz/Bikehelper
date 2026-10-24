import { useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import Search from "./Search.jsx";
import ThemeToggle from "./ThemeToggle.jsx";
import UploadBanner from "./UploadBanner.jsx";

const NAV = [
  { to: "/", label: "Start", end: true, icon: "M4 12 A8 8 0 0 1 20 12 M12 12 L16 8 M6 20 H18" },
  { to: "/garage", label: "Garage", icon: "M3 11 L12 4 L21 11 V20 H3 Z M8 20 V14 H16 V20" },
  { to: "/advisor", label: "Ratgeber", icon: "M4 7 H20 M4 17 H20 M9 4 V10 M15 14 V20" },
  { to: "/rides", label: "Fahrten", icon: "M8 6 H20 M8 12 H20 M8 18 H20 M4 6 H4.01 M4 12 H4.01 M4 18 H4.01" },
  { to: "/heatmap", label: "Heatmap", icon: "M12 21 C7 15 5 12 5 9 A7 7 0 0 1 19 9 C19 12 17 15 12 21 Z M12 11 A2 2 0 1 0 12.01 11" },
  { to: "/stats", label: "Statistik", icon: "M5 20 V12 M12 20 V5 M19 20 V9" },
  { to: "/settings", label: "Einstellungen", short: "Konto", icon: "M12 9 A3 3 0 1 0 12.01 9 M12 3 V5 M12 19 V21 M3 12 H5 M19 12 H21 M5.6 5.6 L7 7 M17 17 L18.4 18.4 M18.4 5.6 L17 7 M7 17 L5.6 18.4" },
];

/** Rahmen der App: Seitenleiste am Computer, schmale Kopfzeile und Tabs am unteren Rand auf dem Handy. */
export default function Shell({ user, onLogout, children }) {
  const { pathname } = useLocation();
  // Seitentitel für Browser-Tab und Screenreader; Fokus springt beim Seitenwechsel zum Inhalt
  useEffect(() => {
    const hit = [...NAV].reverse().find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
    document.title = pathname.startsWith("/admin") ? "Administration · BikeHelper" : hit ? `${hit.label} · BikeHelper` : "BikeHelper";
  }, [pathname]);
  return (
    <div className="shell">
      <a className="skip-link" href="#inhalt">Zum Inhalt springen</a>
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true" />
            BikeHelper
          </div>
          <ThemeToggle />
        </div>
        <Search />
        <nav aria-label="Hauptmenü">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}>
              <svg viewBox="0 0 24 24" className="nav-icon" aria-hidden="true" focusable="false"><path d={n.icon} /></svg>
              <span className="nav-label">{n.label}</span>
              {n.short && <span className="nav-short" aria-hidden="true">{n.short}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="muted small">{user.email}</span>
          {user.role === "admin" && <NavLink className="link" to="/admin">Administration</NavLink>}
          <button className="link" onClick={onLogout}>Abmelden</button>
        </div>
      </aside>
      <main className="main" id="inhalt" tabIndex={-1}>
        <UploadBanner />
        <div className="page" key={pathname}>{children}</div>
      </main>
    </div>
  );
}
