/**
 * Imported once, where the app starts, before anything makes a map: MapLibre
 * then fetches this site's terrain tiles through `patientTiles.ts`.
 */

import { addProtocol } from "maplibre-gl";
import { registerPatientTiles } from "./patientTiles.js";

registerPatientTiles(addProtocol);
