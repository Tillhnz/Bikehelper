/** Einheitliche Symbole für Kleidung und Ausrüstung im Ratgeber: gleiche Größe, gleiche Linienstärke, gleiche Art zu zeichnen. */

const P = {
  jerseyShort: "M8 4 L3.5 7.5 L6 10.5 L8 9 V20 H16 V9 L18 10.5 L20.5 7.5 L16 4 Q12 7.5 8 4 Z",
  jerseyLong: "M8 4 L2.5 11 L4.5 13 L8 9.5 V20 H16 V9.5 L19.5 13 L21.5 11 L16 4 Q12 7.5 8 4 Z",
  base: "M8 3 Q12 9 16 3 L16.5 9 Q18 11 18 13 V21 H6 V13 Q6 11 7.5 9 Z",
  sleeves: "M4 5 H10 L9 19 H5 Z M14 5 H20 L19 19 H15 Z",
  jacket: "M8 4 L2.5 11 L4.5 13 L8 9.5 V20 H16 V9.5 L19.5 13 L21.5 11 L16 4 L12 6.5 Z M12 6.5 V20",
  vest: "M8 4 L9 3 L12 6.5 L15 3 L16 4 L17 9 V20 H7 V9 Z M12 6.5 V20",
  rain: "M7 13 A3.8 3.8 0 0 1 8 5.5 A5 5 0 0 1 17 7.5 A3.2 3.2 0 0 1 17 13 Z M8.5 16 L7.5 19.5 M12.5 16 L11.5 19.5 M16.5 16 L15.5 19.5",
  shortsShort: "M6 4 H18 L19 13 H13.5 L12 9 L10.5 13 H5 Z",
  legsLong: "M8 3 H16 L17.5 21 H13.2 L12 10.5 L10.8 21 H6.5 Z",
  legWarmer: "M8 3 H16 L16.5 21 H7.5 Z M7.9 8 H16.1",
  kneeWarmer: "M8 8 H16 L15.7 17 H8.3 Z",
  gloves: "M8 21 V13 L5.5 10 Q5 9 6 8.5 Q7 8 8 9.5 L9 11 V5 Q9 3.8 10.2 3.8 Q11.4 3.8 11.4 5 V9 V4 Q11.4 2.8 12.6 2.8 Q13.8 2.8 13.8 4 V9 V5 Q13.8 3.8 15 3.8 Q16.2 3.8 16.2 5 V12 L17.5 10.5 Q18.5 9.5 19.3 10.3 L17 17 V21 Z",
  shoeCover: "M9 3 H14 V12 L19.5 15.5 V20 H5.5 V16 L9 12.5 Z M5.5 17.5 H19.5",
  sock: "M9 3 H15 V12 L19.5 16 Q20.5 19.5 17 20 H8.5 Q8 20 8 19 Z M9 7 H15",
  beanie: "M5 15 A7 7 0 0 1 19 15 Z M5 18.5 H19 M12 8 V5.5 M11 4.5 H13",
  scarf: "M6 8 Q12 13 18 8 V12 Q12 18 6 12 Z M10 15.5 V20",
  cap: "M5 14 A7 7 0 0 1 19 14 Z M13 14 H21 M5 14 H3.5",
  sunscreen: "M9 10 H15 V21 H9 Z M10 10 V7 H14 V10 M12 7 V4 H15",
  glasses: "M3 10 H21 M3 10 V13 A3 3 0 0 0 9 13 V10 M15 10 V13 A3 3 0 0 0 21 13 V10 M9 11 Q12 9 15 11",
  bottle: "M10 3 H14 V6 L15.5 8 V21 H8.5 V8 L10 6 Z M8.5 12 H15.5",
  food: "M4 14 L14 4 L20 10 L10 20 Z M9 9 L15 15",
  light: "M12 3 A5 5 0 0 0 9 12 V15 H15 V12 A5 5 0 0 0 12 3 Z M10 18 H14 M10.5 21 H13.5",
  reflect: "M7.5 14.5 A4.5 4.5 0 1 1 16.5 14.5 Z M9.5 18 H14.5 M12 2.5 V4.5 M4.5 6.5 L6 8 M19.5 6.5 L18 8",
  blanket: "M5 5 H19 V19 H5 Z M5 10 L10 5 M5 15 L15 5 M5 19 L19 5 M10 19 L19 10 M15 19 L19 15",
  fender: "M3 15 A9 9 0 0 1 21 15 M7 15 A5 5 0 1 0 17 15",
  spare: "M12 8 A4 4 0 1 0 12.01 8 Z",
};

// Reihenfolge zählt: der erste Treffer gewinnt. `farbe` ordnet die Kachel einer Kategorie zu.
const RULES = [
  [/reflektier/i, "reflect", "Reflektoren", "see"],
  [/kurzes.*trikot|helles trikot/i, "jerseyShort", "Trikot kurz", "top"],
  [/langarm|thermotrikot|softshell/i, "jerseyLong", "Trikot lang", "top"],
  [/unterhemd/i, "base", "Unterhemd", "top"],
  [/armling/i, "sleeves", "Armlinge", "top"],
  [/knieling/i, "kneeWarmer", "Knielinge", "legs"],
  [/beinling|dünne lange hose/i, "legWarmer", "Beinlinge", "legs"],
  [/kurze radhose/i, "shortsShort", "Hose kurz", "legs"],
  [/radhose|thermo-radhose|hose/i, "legsLong", "Hose lang", "legs"],
  [/regenjacke/i, "rain", "Regenjacke", "rain"],
  [/weste/i, "vest", "Weste", "top"],
  [/jacke/i, "jacket", "Jacke", "top"],
  [/handschuh|lobster|lenkerstulpen/i, "gloves", "Handschuhe", "hands"],
  [/überschuh/i, "shoeCover", "Überschuhe", "feet"],
  [/socken|zehenwärmer|wärmepads/i, "sock", "Socken", "feet"],
  [/mütze|stirnband|sturmhaube/i, "beanie", "Mütze", "head"],
  [/halstuch|schlauchtuch/i, "scarf", "Halstuch", "head"],
  [/kappe/i, "cap", "Kappe", "head"],
  [/sonnencreme/i, "sunscreen", "Sonnencreme", "sun"],
  [/sonnenbrille|radbrille/i, "glasses", "Brille", "sun"],
  [/flasche/i, "bottle", "Flaschen", "carry"],
  [/verpflegung/i, "food", "Essen", "carry"],
  [/licht/i, "light", "Licht", "see"],
  [/rettungsdecke/i, "blanket", "Rettungsdecke", "carry"],
  [/schutzblech/i, "fender", "Schutzbleche", "rain"],
];

export function gearFor(text) {
  for (const [re, icon, label, tone] of RULES) if (re.test(text)) return { icon: P[icon], label, tone };
  return { icon: P.spare, label: text.split(/[ ,(]/)[0], tone: "carry" };
}

export function GearGlyph({ d }) {
  return (
    <svg viewBox="0 0 24 24" className="gear-glyph" aria-hidden="true" focusable="false">
      <path d={d} />
    </svg>
  );
}

/** Eine Kachel je Kleidungsstück. Doppelte Teile (z. B. Winterhandschuhe und Zweitpaar) erscheinen nur einmal. */
export function GearTiles({ items }) {
  const seen = new Set();
  const tiles = [];
  for (const text of items) {
    const g = gearFor(text);
    if (seen.has(g.label)) continue;
    seen.add(g.label);
    tiles.push({ ...g, text, optional: /optional|bei bedarf|zweites paar/i.test(text) });
  }
  return (
    <ul className="gear-tiles">
      {tiles.map((t) => (
        <li key={t.label} className={`gear-tile tone-${t.tone} ${t.optional ? "optional" : ""}`} title={t.text}>
          <span className="gear-badge"><GearGlyph d={t.icon} /></span>
          <span className="gear-label">{t.label}{t.optional ? " (optional)" : ""}</span>
          <span className="sr-only">{t.text}</span>
        </li>
      ))}
    </ul>
  );
}
