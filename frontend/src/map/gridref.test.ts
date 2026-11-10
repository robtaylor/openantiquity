// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  formatGridRef,
  GridRefError,
  gridLetters,
  gridMetresToWgs84,
  isOnIslandOfIreland,
  kmSquareAt,
  projectTransverseMercator,
  unprojectTransverseMercator,
  wgs84ToGrid,
  wgs84ToGridMetres,
} from "./gridref.js";

const RAD = Math.PI / 180;

/**
 * Published grid references with the WGS84 position of the south-west corner
 * of each ten-metre square. The latitudes and longitudes were computed
 * independently with PROJ (EPSG:27700 and EPSG:29902 to EPSG:4326).
 */
const PUBLISHED = [
  { name: "Avebury", ref: "SU 1025 6996", grid: "british", e: 410250, n: 169960, lat: 51.4285545, lon: -1.8539567 },
  { name: "Stonehenge", ref: "SU 1224 4219", grid: "british", e: 412240, n: 142190, lat: 51.1788152, lon: -1.8262771 },
  { name: "Ben Nevis", ref: "NN 1667 7128", grid: "british", e: 216670, n: 771280, lat: 56.7968335, lon: -5.0036249 },
  {
    name: "Belfast City Hall",
    ref: "J 3380 7400",
    grid: "irish",
    e: 333800,
    n: 374000,
    lat: 54.5965219,
    lon: -5.9305779,
  },
] as const;

describe("wgs84ToGrid", () => {
  for (const p of PUBLISHED) {
    it(`puts ${p.name} within 20 m of ${p.ref}`, () => {
      const position = wgs84ToGrid(p.lon, p.lat);
      expect(position).not.toBeNull();
      if (!position) return;
      expect(position.grid).toBe(p.grid);
      const error = Math.hypot(position.easting - p.e, position.northing - p.n);
      expect(error).toBeLessThan(20);
    });

    it(`prints ${p.ref} for a point inside the ${p.name} square`, () => {
      // Five metres in from the corner, so a metre or two of datum error
      // cannot push the point over the edge of the ten-metre square.
      const centre = gridMetresToWgs84({ grid: p.grid, easting: p.e + 5, northing: p.n + 5 });
      const position = wgs84ToGrid(centre.lon, centre.lat);
      expect(position).not.toBeNull();
      if (!position) return;
      expect(formatGridRef(position)).toBe(p.ref);
    });
  }

  it("agrees with the well-known coordinates of Stonehenge", () => {
    const position = wgs84ToGrid(-1.8262, 51.1789);
    expect(position).not.toBeNull();
    if (!position) return;
    expect(formatGridRef(position, 4)).toBe("SU 12 42");
  });

  it("uses the Irish Grid on the island of Ireland only", () => {
    expect(wgs84ToGrid(-5.9305779, 54.5965219)?.grid).toBe("irish");
    // Rathlin Island, off the Antrim coast.
    expect(wgs84ToGrid(-6.1900735, 55.3014422)?.grid).toBe("irish");
    // The Mull of Kintyre is twenty kilometres away, in Scotland.
    expect(wgs84ToGrid(-5.7980666, 55.2979369)?.grid).toBe("british");
    // Isle of Man and Anglesey.
    expect(wgs84ToGrid(-4.48, 54.15)?.grid).toBe("british");
    expect(wgs84ToGrid(-4.63, 53.31)?.grid).toBe("british");
  });

  it("returns null outside both grids", () => {
    expect(wgs84ToGrid(2.35, 48.86)).toBeNull();
    expect(wgs84ToGrid(-74, 40.7)).toBeNull();
    expect(wgs84ToGrid(-9, 50)).toBeNull();
  });

  it("rejects positions that are not numbers", () => {
    expect(() => wgs84ToGrid(Number.NaN, 51)).toThrow(GridRefError);
    expect(() => wgs84ToGrid(0, 91)).toThrow(GridRefError);
  });
});

describe("transverse Mercator", () => {
  it("reproduces the Ordnance Survey worked example", () => {
    // "A guide to coordinate systems in Great Britain", annexe C: an OSGB36
    // latitude and longitude and its National Grid easting and northing.
    const lat = (52 + 39 / 60 + 27.2531 / 3600) * RAD;
    const lon = (1 + 43 / 60 + 4.5177 / 3600) * RAD;
    const { easting, northing } = projectTransverseMercator(lat, lon, "british");
    expect(easting).toBeCloseTo(651409.903, 2);
    expect(northing).toBeCloseTo(313177.27, 2);
  });

  it("inverts to within a millimetre", () => {
    for (const grid of ["british", "irish"] as const) {
      const { lat, lon } = unprojectTransverseMercator(312345.6, 265432.1, grid);
      const back = projectTransverseMercator(lat, lon, grid);
      expect(back.easting).toBeCloseTo(312345.6, 3);
      expect(back.northing).toBeCloseTo(265432.1, 3);
    }
  });
});

describe("gridMetresToWgs84", () => {
  it("round-trips through wgs84ToGridMetres to within a centimetre", () => {
    for (const p of PUBLISHED) {
      const ll = gridMetresToWgs84({ grid: p.grid, easting: p.e, northing: p.n });
      const back = wgs84ToGridMetres(ll.lon, ll.lat, p.grid);
      expect(Math.hypot(back.easting - p.e, back.northing - p.n)).toBeLessThan(0.01);
    }
  });

  it("matches the PROJ positions to within 20 m", () => {
    for (const p of PUBLISHED) {
      const ll = gridMetresToWgs84({ grid: p.grid, easting: p.e, northing: p.n });
      const northM = (ll.lat - p.lat) * 111320;
      const eastM = (ll.lon - p.lon) * 111320 * Math.cos(p.lat * RAD);
      expect(Math.hypot(northM, eastM)).toBeLessThan(20);
    }
  });
});

describe("gridLetters and formatGridRef", () => {
  it("letters the British 100 km squares", () => {
    expect(gridLetters({ grid: "british", easting: 0, northing: 0 })).toBe("SV");
    expect(gridLetters({ grid: "british", easting: 410250, northing: 169960 })).toBe("SU");
    expect(gridLetters({ grid: "british", easting: 216670, northing: 771280 })).toBe("NN");
    expect(gridLetters({ grid: "british", easting: 530000, northing: 180000 })).toBe("TQ");
    expect(gridLetters({ grid: "british", easting: 447000, northing: 1141000 })).toBe("HU");
  });

  it("letters the Irish 100 km squares", () => {
    expect(gridLetters({ grid: "irish", easting: 333800, northing: 374000 })).toBe("J");
    expect(gridLetters({ grid: "irish", easting: 0, northing: 0 })).toBe("V");
    expect(gridLetters({ grid: "irish", easting: 315000, northing: 452000 })).toBe("D");
    expect(gridLetters({ grid: "irish", easting: 315000, northing: 234000 })).toBe("O");
  });

  it("truncates to the requested number of figures", () => {
    const avebury = { grid: "british", easting: 410259.9, northing: 169969.9 } as const;
    expect(formatGridRef(avebury)).toBe("SU 1025 6996");
    expect(formatGridRef(avebury, 6)).toBe("SU 102 699");
    expect(formatGridRef(avebury, 10)).toBe("SU 10259 69969");
    expect(formatGridRef({ grid: "british", easting: 400005, northing: 100009 })).toBe("SU 0000 0000");
  });

  it("refuses positions outside the grid", () => {
    expect(() => gridLetters({ grid: "british", easting: -1, northing: 0 })).toThrow(GridRefError);
    expect(() => gridLetters({ grid: "irish", easting: 500000, northing: 0 })).toThrow(GridRefError);
  });
});

describe("isOnIslandOfIreland", () => {
  it("separates Ireland from its neighbours", () => {
    expect(isOnIslandOfIreland(-6.26, 53.35)).toBe(true); // Dublin
    expect(isOnIslandOfIreland(-9.05, 53.27)).toBe(true); // Galway
    expect(isOnIslandOfIreland(-7.37, 55.38)).toBe(true); // Malin Head
    expect(isOnIslandOfIreland(-5.43, 54.49)).toBe(true); // Ards peninsula
    expect(isOnIslandOfIreland(-6.33, 55.58)).toBe(false); // Islay
    expect(isOnIslandOfIreland(-5.31, 51.9)).toBe(false); // St Davids Head
    expect(isOnIslandOfIreland(-4.86, 54.63)).toBe(false); // Mull of Galloway
  });
});

describe("kmSquareAt", () => {
  it("returns the one-kilometre square around a point", () => {
    const square = kmSquareAt(-1.8539567, 51.4285545);
    expect(square).not.toBeNull();
    if (!square) return;
    expect(square.ref).toBe("SU1069");
    expect(square.ring).toHaveLength(5);
    expect(square.ring[0]).toEqual(square.ring[4]);
    const lons = square.ring.map((c) => c[0]);
    const lats = square.ring.map((c) => c[1]);
    expect(Math.min(...lons)).toBeLessThan(-1.8539567);
    expect(Math.max(...lons)).toBeGreaterThan(-1.8539567);
    expect(Math.min(...lats)).toBeLessThan(51.4285545);
    expect(Math.max(...lats)).toBeGreaterThan(51.4285545);
    // One kilometre is about 0.009 degrees of latitude.
    expect(Math.max(...lats) - Math.min(...lats)).toBeCloseTo(0.009, 2);
  });

  it("is null outside the grids", () => {
    expect(kmSquareAt(2.35, 48.86)).toBeNull();
  });
});
