// Gemeinsame Geometrie für die Fitting-Zeichnungen (Seitenansicht und 3D-Modell).
// Alles in Zentimetern. Ursprung ist die Tretlagermitte, x zeigt nach vorn, y nach oben, z nach rechts.
// Rahmen und Räder sind Richtwerte nach üblicher Rennradgeometrie; Sattel, Lenker und Vorbau folgen den Maßen aus dem Fitting.

export const WHEEL_R = 33.5;      // Laufrad mit 28 mm Reifen
export const RIM_R = 30.6;
export const BB_DROP = 7;         // Tretlager liegt so weit unter den Achsen
export const CHAINSTAY = 41;
export const SEAT_ANGLE = 73.5;
export const HEAD_ANGLE = 73;
export const FORK_OFFSET = 4.5;
export const CHAINRING_R = 10.1;  // 50 Zähne
export const COG_R = 5.0;
export const HUB_HALF = 5.4;      // halbe Nabenbreite
export const CRANK_Q = 7.3;       // halber Q-Faktor: Abstand Pedal zur Mitte
export const SADDLE_LEN = 27;

const rad = (d) => (d * Math.PI) / 180;
export const v = (x, y, z = 0) => ({ x, y, z });
export const along = (a, deg, len) => v(a.x + Math.cos(rad(deg)) * len, a.y + Math.sin(rad(deg)) * len, a.z || 0);
export const mix = (a, b, t) => v(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, (a.z || 0) + ((b.z || 0) - (a.z || 0)) * t);

// Stack und Reach üblicher Rennräder, nach Rahmengröße in cm
const SIZES = [[49, 51.5, 36.9], [52, 53.8, 37.6], [54, 55.6, 38.3], [57, 58.3, 39.2], [60, 61.2, 40.1]];

function interp(size) {
  const s = Math.min(62, Math.max(46, size));
  for (let i = 1; i < SIZES.length; i++) {
    const [s1, st1, re1] = SIZES[i - 1], [s2, st2, re2] = SIZES[i];
    if (s <= s2 || i === SIZES.length - 1) {
      const t = (s - s1) / (s2 - s1);
      return { stack: st1 + (st2 - st1) * t, reach: re1 + (re2 - re1) * t };
    }
  }
  return { stack: 58.3, reach: 39.2 };
}

/** Rahmen, Räder und Gabel für eine Rahmengröße (cm). */
export function frame(sizeCm) {
  const size = Number.isFinite(sizeCm) && sizeCm > 30 ? sizeCm : 57;
  const { stack, reach } = interp(size);
  const rearAxle = v(-Math.sqrt(CHAINSTAY ** 2 - BB_DROP ** 2), BB_DROP);
  const seatTop = along(v(0, 0), 180 - SEAT_ANGLE, size * 0.96);       // oberes Ende des Sitzrohrs
  const headTop = v(reach, stack);
  const headLen = 11 + (size - 49) * 0.9;
  const headBottom = along(headTop, -HEAD_ANGLE, headLen);             // Steuerrohr neigt sich nach vorn unten
  const axisAt = (y) => along(headTop, -HEAD_ANGLE, (headTop.y - y) / Math.sin(rad(HEAD_ANGLE)));
  const onAxis = axisAt(BB_DROP);
  const frontAxle = v(onAxis.x + FORK_OFFSET / Math.sin(rad(HEAD_ANGLE)), BB_DROP);
  const forkBend = mix(headBottom, frontAxle, 0.55);
  return {
    ttFront: along(headTop, -HEAD_ANGLE, 1.6),                         // Oberrohr setzt etwas unter dem Steuersatz an
    size, stack, reach, rearAxle, frontAxle, seatTop, headTop, headBottom, headLen, axisAt,
    fork: v(forkBend.x + 1.2, forkBend.y + 0.6),                        // leichter Bogen der Gabel
    ground: BB_DROP - WHEEL_R,
  };
}

/**
 * Sattel-, Lenker- und Vorbauposition aus den Fittingwerten.
 * Gemessen wird: Sattelhöhe entlang des Sitzrohrs, Sattelversatz waagerecht zur Sattelspitze
 * (negativ = hinter dem Tretlager), Sattelspitze bis Armauflage waagerecht, Überhöhung = Sattel minus Auflage.
 */
export function pose(values, fr) {
  if (!values) return null;
  const { saddle_height: h, saddle_setback: back, saddle_to_bar: reach, drop } = values;
  if ([h, back, reach, drop].some((n) => typeof n !== "number")) return null;
  const top = along(v(0, 0), 180 - SEAT_ANGLE, h);                      // Sattelmitte oben, auf Höhe der Sattelhöhe
  const tip = v(back, top.y);
  const tilt = typeof values.saddle_tilt === "number" ? values.saddle_tilt : 0;
  const rear = along(tip, 180 - tilt, SADDLE_LEN);                      // positiver Wert: Spitze zeigt nach unten
  const shell = saddleShape(tip, tilt);
  const post = v(shell[3].x, shell[3].y - 1.7);                         // Sattelstütze greift etwa in der Mitte an
  const hood = v(tip.x + reach, top.y - drop);                          // Handauflage: hier wird gemessen
  const clamp = v(hood.x - 7, hood.y + 0.5);                            // Lenkermitte liegt hinter der Auflage
  const halfBar = (typeof values.bar_width === "number" ? values.bar_width : 420) / 20;

  // Vorbau: Anfang liegt auf der Lenkachse. Mit bekannter Länge wird der passende Punkt gesucht,
  // sonst beginnt der Vorbau oben am Steuerrohr.
  let stemStart = fr.headTop;
  const len = typeof values.stem_length === "number" ? values.stem_length / 10 : null;
  if (len) {
    const d = { x: Math.cos(rad(-HEAD_ANGLE)), y: Math.sin(rad(-HEAD_ANGLE)) };
    const o = { x: fr.headTop.x - clamp.x, y: fr.headTop.y - clamp.y };
    const b = 2 * (o.x * d.x + o.y * d.y);
    const c = o.x ** 2 + o.y ** 2 - len ** 2;
    const disc = b * b - 4 * c;
    if (disc >= 0) {
      const s = Math.min((-b + Math.sqrt(disc)) / 2, (-b - Math.sqrt(disc)) / 2); // kleinster Wert: am höchsten Punkt
      if (s > -9 && s < 4) stemStart = along(fr.headTop, -HEAD_ANGLE, s);
    }
  }
  const steerTop = stemStart.y > fr.headTop.y ? stemStart : along(fr.headTop, 180 - HEAD_ANGLE, 1.2);
  return { top, tip, rear, shell, post, hood, clamp, halfBar, stemStart, steerTop, tilt, h, back, reach, drop };
}

/** Umriss des Sattels von der Seite, von der Spitze nach hinten, mit der Neigung gedreht. */
export function saddleShape(tip, tilt) {
  const a = rad(180 - tilt), c = Math.cos(a), si = Math.sin(a);
  return [[0, 0], [3, 0.25], [8, 0.7], [14, 1.3], [20, 1.9], [25, 2.6], [27, 3.4]]
    .map(([d, up]) => v(tip.x + c * d - si * up, tip.y + si * d + c * up));
}

/** Seitenriss des Lenkerbügels, relativ zur Lenkermitte: Oberlenker, Griffe, Unterlenker. */
export const BAR_PROFILE = [
  v(0, 0), v(3.4, 0.6), v(6.2, 0.4), v(7, -0.5), v(8.6, -2.2), v(9.4, -4.6),
  v(9.0, -7.2), v(7.6, -9.2), v(5.4, -10.3), v(3.2, -10.6),
];

/** Punkte eines Kreises in der x-y-Ebene, für Räder und Kettenblatt. */
export function circlePts(c, r, n = 56) {
  return Array.from({ length: n + 1 }, (_, i) => {
    const a = (i / n) * Math.PI * 2;
    return v(c.x + Math.cos(a) * r, c.y + Math.sin(a) * r, c.z || 0);
  });
}
