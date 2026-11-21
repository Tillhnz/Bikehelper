// Auswertung der erkannten Körperpunkte. Reine Rechnung, ohne Browser: so lässt sie sich getrennt prüfen.
//
// Wichtig: Die Punkte des Pose-Modells sind je Achse auf 0 bis 1 normiert. Bei einem Bild im Format 16:9
// ist ein x-Schritt also kürzer als ein y-Schritt. Ohne Korrektur mit dem Seitenverhältnis wären alle
// Winkel falsch. Deshalb wird x überall mit aspect = Breite/Höhe multipliziert.

export const JOINTS = { shoulder: [11, 12], elbow: [13, 14], wrist: [15, 16], hip: [23, 24], knee: [25, 26], ankle: [27, 28], heel: [29, 30], toe: [31, 32] };
export const BONES = [[11, 13], [13, 15], [11, 23], [23, 25], [25, 27], [27, 31], [12, 14], [14, 16], [12, 24], [24, 26], [26, 28], [28, 32], [11, 12], [23, 24]];
export const MIN_VIS = 0.5;

const DEG = 180 / Math.PI;
const pt = (lm, i, aspect) => (lm[i] ? { x: lm[i].x * aspect, y: lm[i].y, v: lm[i].visibility ?? 1 } : null);
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/** Winkel bei b, in Grad (0 bis 180). */
export function angle(a, b, c) {
  if (!a || !b || !c) return null;
  const u = { x: a.x - b.x, y: a.y - b.y }, w = { x: c.x - b.x, y: c.y - b.y };
  const n = Math.hypot(u.x, u.y) * Math.hypot(w.x, w.y);
  if (!n) return null;
  return Math.acos(Math.max(-1, Math.min(1, (u.x * w.x + u.y * w.y) / n))) * DEG;
}

/** Neigung der Strecke a-b gegen die Waagerechte, 0 bis 90 Grad. */
export function slope(a, b) {
  if (!a || !b) return null;
  return Math.atan2(Math.abs(a.y - b.y), Math.abs(a.x - b.x)) * DEG;
}

export const median = (xs) => {
  const s = xs.filter((x) => x != null && Number.isFinite(x)).sort((a, b) => a - b);
  if (!s.length) return null;
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
export const quant = (xs, q) => {
  const s = xs.filter((x) => x != null && Number.isFinite(x)).sort((a, b) => a - b);
  if (!s.length) return null;
  return s[Math.min(s.length - 1, Math.max(0, Math.round(q * (s.length - 1))))];
};
const r1 = (x) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 10) / 10);

/** Messwerte eines Einzelbildes für beide Körperseiten. */
export function framePose(lm, aspect = 1) {
  if (!lm || lm.length < 33) return null;
  const g = (i) => pt(lm, i, aspect);
  const out = { sides: {} };
  for (const [key, k] of [["l", 0], ["r", 1]]) {
    const sh = g(JOINTS.shoulder[k]), el = g(JOINTS.elbow[k]), wr = g(JOINTS.wrist[k]);
    const hi = g(JOINTS.hip[k]), kn = g(JOINTS.knee[k]), an = g(JOINTS.ankle[k]), toe = g(JOINTS.toe[k]);
    out.sides[key] = {
      vis: [sh, hi, kn, an].reduce((s, p) => s + (p?.v ?? 0), 0) / 4,
      knee: angle(hi, kn, an), hip: angle(sh, hi, kn), elbow: angle(sh, el, wr), armTorso: angle(hi, sh, el),
      ankle: angle(kn, an, toe), back: slope(sh, hi), ankleY: an?.y ?? null,
      kneeX: kn?.x ?? null, hipX: hi?.x ?? null, ankleX: an?.x ?? null, legLen: hi && an ? dist(hi, an) : null,
    };
  }
  const shL = g(JOINTS.shoulder[0]), shR = g(JOINTS.shoulder[1]), hiL = g(JOINTS.hip[0]), hiR = g(JOINTS.hip[1]);
  out.shoulderSpan = shL && shR ? dist(shL, shR) : null;
  out.torso = shL && hiL ? dist({ x: (shL.x + shR.x) / 2, y: (shL.y + shR.y) / 2 }, { x: (hiL.x + hiR.x) / 2, y: (hiL.y + hiR.y) / 2 }) : null;
  out.pelvisTilt = hiL && hiR ? Math.atan2(hiR.y - hiL.y, hiR.x - hiL.x) * DEG : null;
  out.shoulderTilt = shL && shR ? Math.atan2(shR.y - shL.y, shR.x - shL.x) * DEG : null;
  out.vis = (out.sides.l.vis + out.sides.r.vis) / 2;
  return out;
}

/** Grobe Prüfung, ob die Kamera wirklich seitlich (oder von vorn) steht. */
export function viewCheck(frames) {
  const ratio = median(frames.map((f) => (f.torso ? f.shoulderSpan / f.torso : null)));
  if (ratio == null) return { ratio: null, looks: null };
  return { ratio: r1(ratio), looks: ratio < 0.42 ? "side" : ratio > 0.62 ? "front" : "angled" };
}

/** Tretzyklen über den tiefsten und höchsten Punkt des Knöchels finden. */
function cycles(ankleY, times) {
  const n = ankleY.length;
  if (n < 20) return [];
  const lo = quant(ankleY, 0.05), hi = quant(ankleY, 0.95);
  if (hi == null || hi - lo < 0.02) return [];           // zu wenig Bewegung im Bild
  const mid = (lo + hi) / 2;
  const tops = [];                                        // oberster Punkt des Fußes = Beginn eines Zyklus
  for (let i = 3; i < n - 3; i++) {
    if (ankleY[i] == null || ankleY[i] > mid) continue;
    let best = true;
    for (let j = i - 3; j <= i + 3; j++) if (ankleY[j] != null && ankleY[j] < ankleY[i]) best = false;
    if (!best) continue;
    if (tops.length && times[i] - times[tops[tops.length - 1]] < 0.35) {
      if (ankleY[i] < ankleY[tops[tops.length - 1]]) tops[tops.length - 1] = i;
      continue;
    }
    tops.push(i);
  }
  const out = [];
  for (let i = 1; i < tops.length; i++) {
    const [a, b] = [tops[i - 1], tops[i]];
    if (times[b] - times[a] > 2.5) continue;              // Lücke, kein sauberer Zyklus
    out.push([a, b]);
  }
  return out;
}

/** Seitenansicht auswerten. frames: [{t, pose}] */
export function analyseSide(frames) {
  const good = frames.filter((f) => f.pose);
  if (good.length < 25) return { error: "Es war zu selten eine Person im Bild. Mehr Licht, und die ganze Person ins Bild nehmen." };
  const key = median(good.map((f) => f.pose.sides.l.vis)) >= median(good.map((f) => f.pose.sides.r.vis)) ? "l" : "r";
  const s = good.map((f) => f.pose.sides[key]);
  const t = good.map((f) => f.t);
  const cyc = cycles(s.map((x) => x.ankleY), t);
  const view = viewCheck(good.map((f) => f.pose));
  if (cyc.length < 2) {
    return { error: "Es war kaum eine ganze Pedalumdrehung zu sehen. Gleichmäßig weitertreten und das ganze Bein im Bild lassen.", view };
  }
  const ext = [], flex = [], hipMin = [], extAt = [];
  for (const [a, b] of cyc) {
    let mx = -1, mn = 999, mi = a, hm = 999;
    for (let i = a; i <= b; i++) {
      const k = s[i].knee;
      if (k == null) continue;
      if (k > mx) { mx = k; mi = i; }
      if (k < mn) mn = k;
      if (s[i].hip != null && s[i].hip < hm) hm = s[i].hip;
    }
    if (mx > 0) { ext.push(mx); flex.push(mn); extAt.push(mi); }
    if (hm < 900) hipMin.push(hm);
  }
  const vis = (f, min = MIN_VIS) => s.filter((x) => x.vis >= min).map(f);
  const dur = t[t.length - 1] - t[0];
  return {
    side: key, view, frames: good.length, seconds: r1(dur), cycles: cyc.length,
    cadence: r1(60 / median(cyc.map(([a, b]) => t[b] - t[a]))),
    knee_bdc: r1(median(ext)), knee_spread: r1((quant(ext, 0.9) ?? 0) - (quant(ext, 0.1) ?? 0)),
    knee_min: r1(median(flex)), hip_min: r1(median(hipMin)),
    back: r1(median(vis((x) => x.back))), elbow: r1(median(vis((x) => x.elbow))),
    arm_torso: r1(median(vis((x) => x.armTorso))), ankle: r1(median(vis((x) => x.ankle))),
    marks: extAt.map((i) => r1(t[i] - t[0])),             // Zeitpunkte der größten Streckung, für den Player
  };
}

/** Frontansicht auswerten: Kniespur und Schieflagen. */
export function analyseFront(frames) {
  const good = frames.filter((f) => f.pose && f.pose.sides.l.vis >= MIN_VIS && f.pose.sides.r.vis >= MIN_VIS);
  if (good.length < 25) return { error: "Es war zu selten eine Person im Bild. Mehr Licht, und Hüfte bis Füße ins Bild nehmen." };
  const view = viewCheck(good.map((f) => f.pose));
  // Abweichung des Knies von der Linie Hüfte-Knöchel, in Prozent der Beinlänge. Plus heißt zur Körpermitte.
  const dev = (p, k) => {
    const x = p.sides[k];
    if (x.hipX == null || x.ankleX == null || x.kneeX == null || !x.legLen) return null;
    const line = x.hipX + (x.ankleX - x.hipX) * 0.5;      // Knie liegt etwa auf halber Höhe
    const mid = (p.sides.l.hipX + p.sides.r.hipX) / 2;
    const inward = x.hipX >= mid ? -1 : 1;
    return ((x.kneeX - line) / x.legLen) * 100 * inward;
  };
  const dl = good.map((f) => dev(f.pose, "l")), dr = good.map((f) => dev(f.pose, "r"));
  const tilt = good.map((f) => f.pose.pelvisTilt), sh = good.map((f) => f.pose.shoulderTilt);
  return {
    view, frames: good.length,
    knee_dev_l: r1(median(dl)), knee_dev_r: r1(median(dr)),
    knee_sway_l: r1((quant(dl, 0.9) ?? 0) - (quant(dl, 0.1) ?? 0)), knee_sway_r: r1((quant(dr, 0.9) ?? 0) - (quant(dr, 0.1) ?? 0)),
    pelvis_tilt: r1(Math.abs(median(tilt))), pelvis_range: r1((quant(tilt, 0.9) ?? 0) - (quant(tilt, 0.1) ?? 0)),
    shoulder_tilt: r1(Math.abs(median(sh))),
  };
}

// Richtwerte aus der Fachliteratur (siehe README). Sie gelten für Rennrad und Hände am Bremsgriff.
export const RANGES = {
  knee_bdc: { label: "Kniewinkel, größte Streckung", lo: 145, hi: 155, ideal: 150, unit: "°" },
  knee_min: { label: "Kniewinkel, stärkste Beugung", lo: 65, hi: 80, unit: "°" },
  hip_min: { label: "Hüftwinkel, engste Stelle", lo: 70, hi: 85, unit: "°" },
  back: { label: "Rücken zur Waagerechten", lo: 35, hi: 55, unit: "°" },
  elbow: { label: "Ellbogenwinkel", lo: 145, hi: 165, unit: "°" },
  arm_torso: { label: "Arm zu Oberkörper", lo: 78, hi: 95, unit: "°" },
  cadence: { label: "Trittfrequenz", lo: 70, hi: 100, unit: "/min" },
};
export const FRONT_RANGES = {
  knee_dev_l: { label: "Kniespur links", lo: -6, hi: 6, unit: "%" },
  knee_dev_r: { label: "Kniespur rechts", lo: -6, hi: 6, unit: "%" },
  pelvis_range: { label: "Beckenschaukeln", lo: 0, hi: 5, unit: "°" },
  shoulder_tilt: { label: "Schulterschiefe", lo: 0, hi: 4, unit: "°" },
};

// So viel ändert sich der Kniewinkel bei einem Zentimeter Sattelhöhe (aus der Beingeometrie gerechnet,
// etwa 5 Grad). Wir rechnen vorsichtig und begrenzen jeden Vorschlag auf einen Zentimeter.
const DEG_PER_CM = 5.5;
const mm = (cm) => Math.round(Math.max(-10, Math.min(10, cm * 10)) / 5) * 5;
const num = (x) => String(Math.round(x * 10) / 10).replace(".", ",");

/** Handlungsempfehlungen aus den Messwerten. fit: zuletzt eingetragenes Fitting (optional). */
export function advise(metrics, fit) {
  const out = [];
  const s = metrics.side, f = metrics.front;
  const add = (level, title, text) => out.push({ level, title, text });
  const target = (key, deltaCm) => {
    const base = fit?.optimized?.[key] ?? fit?.initial?.[key];
    return typeof base === "number" ? ` Aus deinem Fitting: ${num(base)} cm, also etwa ${num(base + deltaCm)} cm.` : "";
  };

  if (s && !s.error) {
    const k = s.knee_bdc, R = RANGES.knee_bdc;
    if (k != null && k !== 0 && (k < R.lo || k > R.hi)) {
      const up = k < R.lo;
      const raw = (up ? R.ideal - k : k - R.ideal) / DEG_PER_CM;     // rechnerischer Unterschied in cm
      const step = mm(raw);
      const d = (up ? 1 : -1) * step / 10;
      const capped = raw * 10 > step + 1 ? ` Rechnerisch wären es ${num(raw)} cm. Geh die Strecke in Stufen: erst ${step} mm, dann neu messen.` : "";
      add("act", `Sattel etwa ${step} mm ${up ? "höher" : "tiefer"}`,
        up
          ? `Das Knie bleibt unten mit ${num(k)}° deutlich gebeugt, empfohlen sind ${R.lo} bis ${R.hi}°. Stelle den Sattel in Schritten von 5 mm höher und fahre jede Stufe ein paar Ausfahrten.${capped}${target("saddle_height", d)}`
          : `Das Bein ist unten mit ${num(k)}° fast durchgestreckt, empfohlen sind ${R.lo} bis ${R.hi}°. Ein zu hoher Sattel belastet die Kniekehle und lässt das Becken kippeln.${capped}${target("saddle_height", d)}`);
    } else if (k != null) {
      add("ok", "Sattelhöhe passt", `Der Kniewinkel liegt mit ${num(k)}° im empfohlenen Bereich von ${R.lo} bis ${R.hi}°.`);
    }
    if (s.knee_spread != null && s.knee_spread > 8) {
      add("hint", "Unruhiger Tritt", `Die größte Kniestreckung schwankt von Umdrehung zu Umdrehung um ${num(s.knee_spread)}°. Das kann an der Messung liegen (Licht, Kleidung) oder daran, dass du nicht gleichmäßig getreten hast. Wiederhole die Messung bei ruhiger, gleichmäßiger Trittfrequenz.`);
    }
    if (s.elbow != null && s.elbow > RANGES.elbow.hi + 7) {
      add("act", "Arme werden durchgestreckt",
        `Der Ellbogen ist mit ${num(s.elbow)}° fast gerade. Übliche Werte am Bremsgriff liegen bei ${RANGES.elbow.lo} bis ${RANGES.elbow.hi}°. Durchgestreckte Arme leiten jeden Schlag in Schultern und Handgelenke. Ein um 10 mm kürzerer Vorbau oder ein Spacer mehr schafft Luft.${target("saddle_to_bar", -1)}`);
    } else if (s.elbow != null && s.elbow < RANGES.elbow.lo - 10) {
      add("hint", "Sehr kurze Front", `Der Ellbogen ist mit ${num(s.elbow)}° stark gebeugt. Das ist bequem, kann aber eng werden. Wenn du dich gedrängt fühlst, probiere einen 10 mm längeren Vorbau.`);
    }
    if (s.back != null && s.back < RANGES.back.lo) {
      add("hint", "Sehr gestreckte Haltung",
        `Der Rücken liegt mit ${num(s.back)}° zur Waagerechten flacher als die üblichen ${RANGES.back.lo} bis ${RANGES.back.hi}°. Das ist schnell, verlangt aber Beweglichkeit. Bei Nacken- oder Rückenschmerzen hilft meist, den Lenker mit einem Spacer höher zu setzen.`);
    } else if (s.back != null && s.back > RANGES.back.hi) {
      add("hint", "Aufrechte Haltung", `Mit ${num(s.back)}° sitzt du aufrecht. Das ist bequem und bremst nur über den Luftwiderstand. Wer schneller will, nimmt einen Spacer heraus, aber nur einen auf einmal.`);
    }
    if (s.hip_min != null && s.hip_min < RANGES.hip_min.lo - 5) {
      add("hint", "Enger Hüftwinkel oben", `Am obersten Punkt wird die Hüfte auf ${num(s.hip_min)}° zusammengedrückt (üblich sind ${RANGES.hip_min.lo} bis ${RANGES.hip_min.hi}°). Das kostet Kraft und drückt vorn im Schritt. Sattel etwas weiter nach hinten oder Lenker höher kann helfen.`);
    }
    if (s.cadence != null && (s.cadence < 65 || s.cadence > 105)) {
      add("hint", "Trittfrequenz für die Messung", `Gemessen wurde bei ${num(s.cadence)} Umdrehungen pro Minute. Zwischen 80 und 90 sind die Winkel am aussagekräftigsten. Wiederhole die Messung in diesem Bereich.`);
    }
    if (s.view?.looks && s.view.looks !== "side") {
      add("hint", "Kamera stand nicht genau seitlich", "Das Bild sieht nicht nach einer reinen Seitenansicht aus. Stelle die Kamera im rechten Winkel zum Rad, auf Hüfthöhe, 2 bis 3 m entfernt. Schräg gemessene Winkel fallen zu klein aus.");
    }
  }

  if (f && !f.error) {
    const asym = f.knee_dev_l != null && f.knee_dev_r != null ? Math.abs(f.knee_dev_l - f.knee_dev_r) : null;
    for (const [k, label] of [["knee_dev_l", "links"], ["knee_dev_r", "rechts"]]) {
      const d = f[k];
      if (d != null && Math.abs(d) > 6) {
        add("hint", `Knie wandert ${label} ${d > 0 ? "nach innen" : "nach außen"}`,
          `Das Knie ${label} weicht um ${num(Math.abs(d))} % der Beinlänge von der Linie Hüfte–Knöchel ab. Übliche Ursachen sind die Cleat-Stellung, die Pedalachse oder eine Einlegesohle. Für diesen Wert gibt es keinen belastbaren Richtwert, nimm ihn als Hinweis, nicht als Befund.`);
      }
    }
    if (asym != null && asym > 5) {
      add("hint", "Beide Seiten treten unterschiedlich", `Links und rechts unterscheiden sich um ${num(asym)} Punkte. Wenn du dazu einseitig Beschwerden hast, ist das einen Termin beim Fitter oder Physiotherapeuten wert.`);
    }
    if (f.pelvis_range != null && f.pelvis_range > FRONT_RANGES.pelvis_range.hi) {
      const also = s && !s.error && s.knee_bdc > RANGES.knee_bdc.hi ? " Zusammen mit dem stark gestreckten Knie spricht das für einen zu hohen Sattel." : "";
      add("act", "Becken schaukelt", `Das Becken kippt über die Umdrehung um ${num(f.pelvis_range)}° hin und her (bis ${FRONT_RANGES.pelvis_range.hi}° ist normal). Das deutet auf einen zu hohen Sattel oder eine ungleiche Beinlänge hin.${also}`);
    }
    if (f.shoulder_tilt != null && f.shoulder_tilt > FRONT_RANGES.shoulder_tilt.hi) {
      add("hint", "Schultern stehen schief", `Die Schulterlinie steht um ${num(f.shoulder_tilt)}° schief. Oft ist das nur die Haltung im Moment der Aufnahme. Bleibt es über mehrere Messungen, lohnt ein Blick auf Sattelstellung und Beweglichkeit.`);
    }
    if (f.view?.looks && f.view.looks !== "front") {
      add("hint", "Kamera stand nicht genau vorn", "Das Bild sieht nicht nach einer reinen Frontansicht aus. Stelle die Kamera mittig vor das Rad, auf Hüfthöhe.");
    }
  }
  if (!out.length) add("ok", "Keine Auffälligkeiten", "Aus den gemessenen Winkeln ergibt sich kein Änderungsvorschlag.");
  return out;
}
