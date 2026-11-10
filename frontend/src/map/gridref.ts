/**
 * Grid references for the status readout.
 *
 * WGS84 longitude and latitude are shifted to the local datum with a
 * seven-parameter Helmert transform, then projected with the Ordnance Survey
 * Transverse Mercator series. Great Britain uses OSGB36 on the Airy 1830
 * ellipsoid. The island of Ireland uses the Irish Grid on Airy Modified.
 *
 * The Helmert shift is not exact. Against Ordnance Survey's OSTN15 it is out
 * by two metres on average in Great Britain and by nearly six at worst, in
 * the far south-west. In Ireland it is good to a few centimetres. That is
 * fine for a 100 m reference, and for deciding which kilometre square a
 * point is in almost everywhere, but it is not good enough to print 10 m
 * references: the last digit would often be one square out. The status
 * readout prints six figures for that reason.
 */

export class GridRefError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GridRefError";
  }
}

export type GridSystem = "british" | "irish";

export interface GridPosition {
  grid: GridSystem;
  /** Metres east of the grid's false origin. */
  easting: number;
  /** Metres north of the grid's false origin. */
  northing: number;
}

export interface LonLat {
  lon: number;
  lat: number;
}

interface Ellipsoid {
  a: number;
  b: number;
}

interface Helmert {
  tx: number;
  ty: number;
  tz: number;
  /** Scale change in parts per million. */
  s: number;
  /** Rotations in arc-seconds. */
  rx: number;
  ry: number;
  rz: number;
}

interface Projection {
  ellipsoid: Ellipsoid;
  /** Scale factor on the central meridian. */
  f0: number;
  /** True origin, radians. */
  lat0: number;
  lon0: number;
  /** Grid coordinates of the true origin, metres. */
  e0: number;
  n0: number;
}

interface GridDefinition {
  projection: Projection;
  fromWgs84: Helmert;
  widthM: number;
  heightM: number;
}

const RAD = Math.PI / 180;
const ARC_SECOND = Math.PI / (180 * 3600);

const WGS84: Ellipsoid = { a: 6378137, b: 6356752.314245 };
const AIRY_1830: Ellipsoid = { a: 6377563.396, b: 6356256.909 };
const AIRY_MODIFIED: Ellipsoid = { a: 6377340.189, b: 6356034.447 };

const GRIDS: Record<GridSystem, GridDefinition> = {
  british: {
    projection: {
      ellipsoid: AIRY_1830,
      f0: 0.9996012717,
      lat0: 49 * RAD,
      lon0: -2 * RAD,
      e0: 400000,
      n0: -100000,
    },
    fromWgs84: { tx: -446.448, ty: 125.157, tz: -542.06, s: 20.4894, rx: -0.1502, ry: -0.247, rz: -0.8421 },
    widthM: 700000,
    heightM: 1300000,
  },
  irish: {
    projection: {
      ellipsoid: AIRY_MODIFIED,
      f0: 1.000035,
      lat0: 53.5 * RAD,
      lon0: -8 * RAD,
      e0: 200000,
      n0: 250000,
    },
    fromWgs84: { tx: -482.53, ty: 130.596, tz: -564.557, s: -8.15, rx: 1.042, ry: 0.214, rz: 0.631 },
    widthM: 500000,
    heightM: 500000,
  },
};

/**
 * A coarse outline of the island of Ireland, as [lon, lat] pairs. It runs down
 * the middle of the North Channel and the Irish Sea, so Rathlin is inside and
 * Kintyre, Islay, Galloway, Man and Wales are outside.
 */
const IRELAND_OUTLINE: ReadonlyArray<readonly [number, number]> = [
  [-11.0, 51.2],
  [-5.7, 51.2],
  [-5.7, 53.8],
  [-5.35, 54.3],
  [-5.35, 54.8],
  [-5.6, 55.05],
  [-5.93, 55.26],
  [-6.1, 55.42],
  [-6.6, 55.5],
  [-8.0, 55.6],
  [-11.0, 55.6],
];

/** True when the point lies on the island of Ireland or its inshore islands. */
export function isOnIslandOfIreland(lon: number, lat: number): boolean {
  let inside = false;
  const n = IRELAND_OUTLINE.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const [xi, yi] = IRELAND_OUTLINE[i] as readonly [number, number];
    const [xj, yj] = IRELAND_OUTLINE[j] as readonly [number, number];
    const crosses = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

function toCartesian(lat: number, lon: number, ellipsoid: Ellipsoid): [number, number, number] {
  const { a, b } = ellipsoid;
  const e2 = 1 - (b * b) / (a * a);
  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const nu = a / Math.sqrt(1 - e2 * sinLat * sinLat);
  return [nu * cosLat * Math.cos(lon), nu * cosLat * Math.sin(lon), nu * (1 - e2) * sinLat];
}

function fromCartesian(x: number, y: number, z: number, ellipsoid: Ellipsoid): { lat: number; lon: number } {
  const { a, b } = ellipsoid;
  const e2 = 1 - (b * b) / (a * a);
  const p = Math.hypot(x, y);
  let lat = Math.atan2(z, p * (1 - e2));
  for (let i = 0; i < 10; i++) {
    const sinLat = Math.sin(lat);
    const nu = a / Math.sqrt(1 - e2 * sinLat * sinLat);
    const next = Math.atan2(z + e2 * nu * sinLat, p);
    const settled = Math.abs(next - lat) < 1e-12;
    lat = next;
    if (settled) break;
  }
  return { lat, lon: Math.atan2(y, x) };
}

function applyHelmert(point: [number, number, number], t: Helmert, direction: 1 | -1): [number, number, number] {
  const [x, y, z] = point;
  const s = 1 + (direction * t.s) / 1e6;
  const rx = direction * t.rx * ARC_SECOND;
  const ry = direction * t.ry * ARC_SECOND;
  const rz = direction * t.rz * ARC_SECOND;
  return [
    direction * t.tx + x * s - y * rz + z * ry,
    direction * t.ty + x * rz + y * s - z * rx,
    direction * t.tz - x * ry + y * rx + z * s,
  ];
}

/** Meridional arc from the true origin, from the Ordnance Survey guide. */
function meridionalArc(lat: number, p: Projection): number {
  const { a, b } = p.ellipsoid;
  const n = (a - b) / (a + b);
  const n2 = n * n;
  const n3 = n2 * n;
  const dLat = lat - p.lat0;
  const sLat = lat + p.lat0;
  return (
    b *
    p.f0 *
    ((1 + n + (5 / 4) * n2 + (5 / 4) * n3) * dLat -
      (3 * n + 3 * n2 + (21 / 8) * n3) * Math.sin(dLat) * Math.cos(sLat) +
      ((15 / 8) * n2 + (15 / 8) * n3) * Math.sin(2 * dLat) * Math.cos(2 * sLat) -
      (35 / 24) * n3 * Math.sin(3 * dLat) * Math.cos(3 * sLat))
  );
}

/** Project latitude and longitude (radians, on the projection's own datum). */
export function projectTransverseMercator(
  lat: number,
  lon: number,
  grid: GridSystem,
): { easting: number; northing: number } {
  const p = GRIDS[grid].projection;
  const { a, b } = p.ellipsoid;
  const e2 = 1 - (b * b) / (a * a);
  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const tanLat = Math.tan(lat);
  const tan2 = tanLat * tanLat;
  const nu = (a * p.f0) / Math.sqrt(1 - e2 * sinLat * sinLat);
  const rho = (a * p.f0 * (1 - e2)) / (1 - e2 * sinLat * sinLat) ** 1.5;
  const eta2 = nu / rho - 1;
  const m = meridionalArc(lat, p);

  const i = m + p.n0;
  const ii = (nu / 2) * sinLat * cosLat;
  const iii = (nu / 24) * sinLat * cosLat ** 3 * (5 - tan2 + 9 * eta2);
  const iiia = (nu / 720) * sinLat * cosLat ** 5 * (61 - 58 * tan2 + tan2 * tan2);
  const iv = nu * cosLat;
  const v = (nu / 6) * cosLat ** 3 * (nu / rho - tan2);
  const vi = (nu / 120) * cosLat ** 5 * (5 - 18 * tan2 + tan2 * tan2 + 14 * eta2 - 58 * tan2 * eta2);
  const dLon = lon - p.lon0;

  return {
    northing: i + ii * dLon ** 2 + iii * dLon ** 4 + iiia * dLon ** 6,
    easting: p.e0 + iv * dLon + v * dLon ** 3 + vi * dLon ** 5,
  };
}

/** Inverse of {@link projectTransverseMercator}. Returns radians. */
export function unprojectTransverseMercator(
  easting: number,
  northing: number,
  grid: GridSystem,
): { lat: number; lon: number } {
  const p = GRIDS[grid].projection;
  const { a, b } = p.ellipsoid;
  const e2 = 1 - (b * b) / (a * a);

  let lat = p.lat0;
  let m = 0;
  for (let i = 0; i < 20; i++) {
    lat += (northing - p.n0 - m) / (a * p.f0);
    m = meridionalArc(lat, p);
    if (Math.abs(northing - p.n0 - m) < 1e-5) break;
  }

  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const tanLat = Math.tan(lat);
  const tan2 = tanLat * tanLat;
  const nu = (a * p.f0) / Math.sqrt(1 - e2 * sinLat * sinLat);
  const rho = (a * p.f0 * (1 - e2)) / (1 - e2 * sinLat * sinLat) ** 1.5;
  const eta2 = nu / rho - 1;

  const vii = tanLat / (2 * rho * nu);
  const viii = (tanLat / (24 * rho * nu ** 3)) * (5 + 3 * tan2 + eta2 - 9 * tan2 * eta2);
  const ix = (tanLat / (720 * rho * nu ** 5)) * (61 + 90 * tan2 + 45 * tan2 * tan2);
  const x = 1 / (cosLat * nu);
  const xi = (1 / (cosLat * 6 * nu ** 3)) * (nu / rho + 2 * tan2);
  const xii = (1 / (cosLat * 120 * nu ** 5)) * (5 + 28 * tan2 + 24 * tan2 * tan2);
  const xiia = (1 / (cosLat * 5040 * nu ** 7)) * (61 + 662 * tan2 + 1320 * tan2 * tan2 + 720 * tan2 ** 3);
  const dE = easting - p.e0;

  return {
    lat: lat - vii * dE ** 2 + viii * dE ** 4 - ix * dE ** 6,
    lon: p.lon0 + x * dE - xi * dE ** 3 + xii * dE ** 5 - xiia * dE ** 7,
  };
}

function assertLonLat(lon: number, lat: number): void {
  if (!Number.isFinite(lon) || !Number.isFinite(lat) || lat < -90 || lat > 90) {
    throw new GridRefError(`Not a valid position: longitude ${lon}, latitude ${lat}`);
  }
}

/** Convert a WGS84 position to grid metres on the named grid. */
export function wgs84ToGridMetres(lon: number, lat: number, grid: GridSystem): GridPosition {
  assertLonLat(lon, lat);
  const def = GRIDS[grid];
  const shifted = applyHelmert(toCartesian(lat * RAD, lon * RAD, WGS84), def.fromWgs84, 1);
  const local = fromCartesian(shifted[0], shifted[1], shifted[2], def.projection.ellipsoid);
  const { easting, northing } = projectTransverseMercator(local.lat, local.lon, grid);
  return { grid, easting, northing };
}

/** Convert grid metres back to WGS84 degrees. */
export function gridMetresToWgs84(position: GridPosition): LonLat {
  const def = GRIDS[position.grid];
  const local = unprojectTransverseMercator(position.easting, position.northing, position.grid);
  const cartesian = toCartesian(local.lat, local.lon, def.projection.ellipsoid);
  // Reversing the signs inverts the transform to well under a centimetre here.
  const shifted = applyHelmert(cartesian, def.fromWgs84, -1);
  const wgs = fromCartesian(shifted[0], shifted[1], shifted[2], WGS84);
  return { lon: wgs.lon / RAD, lat: wgs.lat / RAD };
}

function isWithinGrid(position: GridPosition): boolean {
  const def = GRIDS[position.grid];
  return (
    position.easting >= 0 && position.easting < def.widthM && position.northing >= 0 && position.northing < def.heightM
  );
}

/**
 * The grid position to show for a WGS84 point: Irish Grid on the island of
 * Ireland, British National Grid elsewhere, or null when the point is outside
 * both grids.
 */
export function wgs84ToGrid(lon: number, lat: number): GridPosition | null {
  assertLonLat(lon, lat);
  // Both series are only good near their own central meridian, so points far
  // from these islands are rejected before projecting.
  if (lon < -12 || lon > 4 || lat < 49 || lat > 61.5) return null;
  const grid: GridSystem = isOnIslandOfIreland(lon, lat) ? "irish" : "british";
  const position = wgs84ToGridMetres(lon, lat, grid);
  return isWithinGrid(position) ? position : null;
}

const IRISH_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ";

/** The letter prefix of the 100 km square that holds the position. */
export function gridLetters(position: GridPosition): string {
  if (!isWithinGrid(position)) {
    throw new GridRefError(
      `Position ${Math.round(position.easting)}, ${Math.round(position.northing)} is outside the ${position.grid} grid`,
    );
  }
  const e100k = Math.floor(position.easting / 100000);
  const n100k = Math.floor(position.northing / 100000);
  if (position.grid === "irish") {
    return IRISH_LETTERS.charAt((4 - n100k) * 5 + e100k);
  }
  let first = 19 - n100k - ((19 - n100k) % 5) + Math.floor((e100k + 10) / 5);
  let second = (((19 - n100k) * 5) % 25) + (e100k % 5);
  // The lettering skips I.
  if (first > 7) first += 1;
  if (second > 7) second += 1;
  return String.fromCharCode(first + 65, second + 65);
}

export type GridFigures = 4 | 6 | 8 | 10;

/**
 * Format a position as a grid reference, for example "SU 1025 6996". The
 * digits are truncated, not rounded, because a reference names the square
 * whose south-west corner it gives.
 */
export function formatGridRef(position: GridPosition, figures: GridFigures = 8): string {
  const letters = gridLetters(position);
  const digits = figures / 2;
  const divisor = 10 ** (5 - digits);
  const e = Math.floor((position.easting % 100000) / divisor);
  const n = Math.floor((position.northing % 100000) / divisor);
  return `${letters} ${String(e).padStart(digits, "0")} ${String(n).padStart(digits, "0")}`;
}

/**
 * The one-kilometre grid square that holds a WGS84 point, as a closed ring of
 * [lon, lat] corners with its reference (for example "SU1069"). Null outside
 * both grids.
 */
export function kmSquareAt(lon: number, lat: number): { ref: string; ring: Array<[number, number]> } | null {
  const position = wgs84ToGrid(lon, lat);
  if (!position) return null;
  const e = Math.floor(position.easting / 1000) * 1000;
  const n = Math.floor(position.northing / 1000) * 1000;
  const corners: Array<[number, number]> = [
    [e, n],
    [e + 1000, n],
    [e + 1000, n + 1000],
    [e, n + 1000],
    [e, n],
  ];
  const ring = corners.map(([easting, northing]): [number, number] => {
    const ll = gridMetresToWgs84({ grid: position.grid, easting, northing });
    return [ll.lon, ll.lat];
  });
  const ref = formatGridRef({ grid: position.grid, easting: e, northing: n }, 4).replaceAll(" ", "");
  return { ref, ring };
}
