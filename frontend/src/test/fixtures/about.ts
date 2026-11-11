import type { components } from "../../api/schema.js";

type LiveSource = components["schemas"]["LiveSource"];

/**
 * A source the browser asks itself, as `GET /context/live-sources` lists it,
 * for the about page's credits.
 */
export function liveSourceFixture(overrides: Partial<LiveSource> = {}): LiveSource {
  return {
    key: "wiltshire-her",
    name: "Wiltshire and Swindon HER",
    publisher: "Wiltshire Council",
    coverage: "england",
    endpoint: "https://example.org/query",
    query_pattern: "https://example.org/query?bbox={west},{south},{east},{north}",
    answer_format: "geojson",
    attribution: "Wiltshire Council",
    credit: "Wiltshire Council Archaeology Service",
    licence: "Unstated. The service sits in the website folder.",
    licence_label: "No licence stated",
    homepage: "https://example.org/",
    credit_field: null,
    preferred_credit_field: null,
    licence_field: null,
    id_field: null,
    name_field: null,
    limit_param: null,
    max_limit: null,
    limits: null,
    link_template: null,
    min_zoom: null,
    response_fields: "",
    shown: true,
    ...overrides,
  };
}
