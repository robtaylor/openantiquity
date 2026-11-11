/**
 * `GET /terrain/coverage?bbox=-2.75,51.6,-2.6,51.7`, recorded from the backend
 * in November 2026: the Wye at Chepstow, where England's 1 m elevation stops
 * at the Welsh border. Squares west of the river have no coverage.
 */
export const BORDER_COVERAGE = {
  type: "FeatureCollection",
  edition: "england-dtm-2022",
  features: [
    {
      type: "Feature",
      id: "SO50se",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.652489, 51.696933],
            [-2.58015, 51.697312],
            [-2.580726, 51.742265],
            [-2.653137, 51.741885],
            [-2.652489, 51.696933],
          ],
        ],
      },
      properties: {
        tile: "SO50se",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2017, 2018],
      },
    },
    {
      type: "Feature",
      id: "SO50sw",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.724827, 51.696508],
            [-2.652489, 51.696933],
            [-2.653137, 51.741885],
            [-2.725546, 51.74146],
            [-2.724827, 51.696508],
          ],
        ],
      },
      properties: {
        tile: "SO50sw",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2017, 2018],
      },
    },
    {
      type: "Feature",
      id: "ST48ne",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.794801, 51.561184],
            [-2.72268, 51.56165],
            [-2.723394, 51.606603],
            [-2.795586, 51.606136],
            [-2.794801, 51.561184],
          ],
        ],
      },
      properties: {
        tile: "ST48ne",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2005, 2006, 2010, 2016, 2018, 2019, 2020, 2021],
      },
    },
    {
      type: "Feature",
      id: "ST58ne",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.650557, 51.562072],
            [-2.578432, 51.56245],
            [-2.579003, 51.607404],
            [-2.651199, 51.607026],
            [-2.650557, 51.562072],
          ],
        ],
      },
      properties: {
        tile: "ST58ne",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2018, 2019, 2020, 2022],
      },
    },
    {
      type: "Feature",
      id: "ST58nw",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.72268, 51.56165],
            [-2.650557, 51.562072],
            [-2.651199, 51.607026],
            [-2.723394, 51.606603],
            [-2.72268, 51.56165],
          ],
        ],
      },
      properties: {
        tile: "ST58nw",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2005, 2006, 2009, 2010, 2016, 2017, 2018, 2019, 2020, 2021, 2022],
      },
    },
    {
      type: "Feature",
      id: "ST59ne",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.651843, 51.651979],
            [-2.579576, 51.652358],
            [-2.58015, 51.697312],
            [-2.652489, 51.696933],
            [-2.651843, 51.651979],
          ],
        ],
      },
      properties: {
        tile: "ST59ne",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2017, 2018, 2019, 2022],
      },
    },
    {
      type: "Feature",
      id: "ST59nw",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.724109, 51.651556],
            [-2.651843, 51.651979],
            [-2.652489, 51.696933],
            [-2.724827, 51.696508],
            [-2.724109, 51.651556],
          ],
        ],
      },
      properties: {
        tile: "ST59nw",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2017, 2018],
      },
    },
    {
      type: "Feature",
      id: "ST59se",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.651199, 51.607026],
            [-2.579003, 51.607404],
            [-2.579576, 51.652358],
            [-2.651843, 51.651979],
            [-2.651199, 51.607026],
          ],
        ],
      },
      properties: {
        tile: "ST59se",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2018, 2019, 2020, 2022],
      },
    },
    {
      type: "Feature",
      id: "ST59sw",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-2.723394, 51.606603],
            [-2.651199, 51.607026],
            [-2.651843, 51.651979],
            [-2.724109, 51.651556],
            [-2.723394, 51.606603],
          ],
        ],
      },
      properties: {
        tile: "ST59sw",
        capture: "2022 composite",
        resolution_m: 1,
        years: [2005, 2006, 2018, 2019, 2020, 2022],
      },
    },
  ],
} as const;

/** The view the recording was made for, west, south, east, north. */
export const BORDER_VIEW: [number, number, number, number] = [-2.75, 51.6, -2.6, 51.7];

/** A spot in Wales, west of the Wye at ST 489 993, in square ST49ne, which has no coverage. */
export const WALES_SPOT = { lng: -2.74, lat: 51.69 };
/** A spot by the Severn at ST 571 914, in square ST59sw, which has coverage. */
export const ENGLAND_SPOT = { lng: -2.62, lat: 51.62 };
