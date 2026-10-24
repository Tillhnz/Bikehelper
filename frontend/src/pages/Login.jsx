import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api.js";

export default function Login({ onLoggedIn }) {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [allowRegistration, setAllowRegistration] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/config").then((c) => setAllowRegistration(c.allow_registration)).catch(() => {});
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
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
        <h1>{mode === "login" ? "Anmelden" : "Konto anlegen"}</h1>
        <label>
          E-Mail
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label>
          Passwort
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={mode === "register" ? 8 : undefined}
            required
          />
          {mode === "register" && <span className="hint">Mindestens 8 Zeichen.</span>}
        </label>
        {mode === "register" && !allowRegistration && (
          <label>
            Einladungscode
            <input value={invite} onChange={(e) => setInvite(e.target.value)} maxLength={32} autoComplete="off" />
            <span className="hint">Die Registrierung ist geschlossen. Den Code bekommst du vom Administrator.</span>
          </label>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy}>
          {mode === "login" ? "Anmelden" : "Konto anlegen"}
        </button>
          <button
            type="button"
            className="link"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
          >
            {mode === "login" ? "Noch kein Konto? Konto anlegen" : "Schon ein Konto? Anmelden"}
          </button>
      </form>
    </div>
  );
}
