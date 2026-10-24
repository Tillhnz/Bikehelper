import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api.js";

export default function Login({ onLoggedIn }) {
  const navigate = useNavigate();
  const query = new URLSearchParams(window.location.search);
  const inviteParam = query.get("invite") || "";
  const resetToken = query.get("reset") || "";
  const [mode, setMode] = useState(resetToken ? "reset" : inviteParam ? "register" : "login"); // login | register | forgot | reset
  const [resetAvailable, setResetAvailable] = useState(false);
  const [info, setInfo] = useState("");
  const [allowRegistration, setAllowRegistration] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState(inviteParam);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/config").then((c) => { setAllowRegistration(c.allow_registration); setResetAvailable(!!c.password_reset); }).catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    setInfo("");
    try {
      if (mode === "forgot") {
        const r = await api.post("/auth/forgot", { email });
        setInfo(r.message);
        return;
      }
      if (mode === "reset") {
        await api.post("/auth/reset", { token: resetToken, password });
        window.history.replaceState(null, "", "/login");
        setMode("login");
        setPassword("");
        setInfo("Dein Passwort ist geändert. Melde dich jetzt an.");
        return;
      }
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const { access_token } = await api.post(path, mode === "login" ? { email, password } : { email, password, invite: invite.trim() || null });
      setToken(access_token);
      await onLoggedIn();
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-art" aria-hidden="true">
        <div className="login-km">
          <span>0</span><span>0</span><span>0</span><span>0</span><span>0</span>
        </div>
        <p>Kilometer, Verschleiß und Wartung für jedes Rad in deiner Garage.</p>
      </div>
      <form className="login-form" onSubmit={submit}>
        <h1>{{ login: "Anmelden", register: "Konto anlegen", forgot: "Passwort vergessen", reset: "Neues Passwort" }[mode]}</h1>
        {mode !== "reset" && (
          <label>
            E-Mail
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus autoComplete="email" />
          </label>
        )}
        {mode === "forgot" && <p className="muted small">Wir schicken dir einen Link, mit dem du ein neues Passwort vergibst. Er gilt eine Stunde.</p>}
        {mode !== "forgot" && (
          <label>
            {mode === "reset" ? "Neues Passwort" : "Passwort"}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={mode === "register" || mode === "reset" ? 8 : undefined}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              autoFocus={mode === "reset"}
              required
            />
            {(mode === "register" || mode === "reset") && <span className="hint">Mindestens 8 Zeichen.</span>}
          </label>
        )}
        {mode === "register" && !allowRegistration && (
          <label>
            Einladungscode
            <input value={invite} onChange={(e) => setInvite(e.target.value)} maxLength={32} autoComplete="off" />
            <span className="hint">Die Registrierung ist geschlossen. Den Code bekommst du vom Administrator.</span>
          </label>
        )}
        {info && <p className="ok" role="status">{info}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy}>
          {{ login: "Anmelden", register: "Konto anlegen", forgot: "Link senden", reset: "Passwort speichern" }[mode]}
        </button>
        {mode === "login" && resetAvailable && (
          <button type="button" className="link" onClick={() => { setMode("forgot"); setError(""); setInfo(""); }}>Passwort vergessen?</button>
        )}
        {mode !== "reset" && (
          <button
            type="button"
            className="link"
            onClick={() => { setMode(mode === "register" ? "login" : mode === "forgot" ? "login" : "register"); setError(""); setInfo(""); }}
          >
            {mode === "login" ? "Noch kein Konto? Konto anlegen" : mode === "forgot" ? "Zurück zur Anmeldung" : "Schon ein Konto? Anmelden"}
          </button>
        )}
      </form>
    </div>
  );
}
