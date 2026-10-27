/** Kopiert Text in die Zwischenablage. Liefert false, wenn weder die moderne noch die alte Methode erlaubt ist
 *  (zum Beispiel in einer eingebetteten Seite ohne Berechtigung oder über http). */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* blockiert: alte Methode versuchen */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
