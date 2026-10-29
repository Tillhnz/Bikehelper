import { createContext, useContext } from "react";

/** "simple" oder "expert": im einfachen Modus fehlen die tiefen Analysen (Belastung, Leistung, Muster, Duell und Ähnliches). */
export const UiModeContext = createContext("expert");
export const useUiMode = () => useContext(UiModeContext);
export const isExpert = (mode) => mode === "expert";
