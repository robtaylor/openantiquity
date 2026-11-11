# The guide's pictures

Each picture is 480 by 300 pixels, made on 2026-11-11 from Open Antiquity's own terrain tiles of the Environment Agency's 2022 LIDAR composite (Open Government Licence v3.0), served by the backend from the local elevation mirror. A crop of 640 by 400 tile pixels, centred on the point below, was scaled to three quarters. The dew pond and the reservoir are 320 by 200 crops at one and a half times. The tramlines and the ridge and furrow had their contrast stretched (Pillow's `ImageOps.autocontrast`, cutting 1 and 2 per cent of the darkest and lightest pixels), and their cards say so. The raking-light picture is a crop of the map in the browser, as the app draws it from the elevation tiles, with the OpenStreetMap overlay on.

What each real example is comes from the heritage records in the development index: the National Heritage List for England (NHLE) and Historic England's Aerial Investigation and Mapping (AIM). A look-alike no record names is marked as our own judgement in `places.ts` and on the page.

| File                            | Place                           | Centre (lon, lat)  | View                        | Zoom | What it shows, and the record                            |
| ------------------------------- | ------------------------------- | ------------------ | --------------------------- | ---- | -------------------------------------------------------- |
| `view-composite.webp`           | Fyfield Down, near Avebury      | -1.8105, 51.4360   | composite                   | 15   | Field system and hollow ways. NHLE 1019190               |
| `view-local-relief.webp`        | The same                        | the same           | local_relief                | 15   | The same ground                                          |
| `view-sky-view.webp`            | The same                        | the same           | sky_view                    | 15   | The same ground                                          |
| `view-multi-shade.webp`         | The same                        | the same           | multi_shade                 | 15   | The same ground                                          |
| `view-slope.webp`               | The same                        | the same           | slope                       | 15   | The same ground                                          |
| `view-openness.webp`            | The same                        | the same           | openness                    | 15   | The same ground                                          |
| `view-raking.webp`              | Silbury Hill                    | -1.8574, 51.4157   | raking (sun 315°, 25° high) | 16   | Silbury Hill                                             |
| `pair-barrow-overton.webp`      | Overton Hill                    | -1.83245, 51.42147 | composite                   | 16   | Bell barrow, NHLE 1008099                                |
| `pair-reservoir-bulford.webp`   | South of Bulford Camp           | -1.7330, 51.1858   | composite                   | 16   | AIM "Reservoir" beside four bowl barrows of NHLE 1009576 |
| `pair-fields-fyfield.webp`      | Fyfield Down                    | -1.8150, 51.4330   | composite                   | 16   | Field system and strip lynchets: NHLE 1019190, AIM       |
| `pair-plough-milkhill.webp`     | Below Milk Hill, Vale of Pewsey | -1.85412, 51.36834 | local_relief                | 16   | Tramlines ending at the field edge: our judgement        |
| `pair-hollowway-fyfield.webp`   | Fyfield Down                    | -1.8122, 51.4371   | sky_view                    | 16   | AIM "Trackway"                                           |
| `pair-enclosure-barbury.webp`   | North of Barbury Castle         | -1.78705, 51.48975 | composite                   | 16   | Enclosure, NHLE 1016357                                  |
| `pair-dewpond-barbury.webp`     | North of Barbury Castle         | -1.78619, 51.48922 | composite                   | 16   | Dew pond, NHLE 1016357                                   |
| `pair-ridge-furrow-pewsey.webp` | Pewsey Down                     | -1.82729, 51.37596 | local_relief                | 16   | AIM "Ridge and furrow"                                   |

No clear pipeline or data stripe was found in the mirrored tiles, so those two look-alikes have no picture.
