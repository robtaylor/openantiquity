import type { Meta, NextStepRule, RasterView, Vocab } from "../../api/meta.js";

/**
 * A stand-in for `GET /api/v1/meta`, used by tests and by `VITE_USE_FIXTURES=1`
 * to run the app with no backend.
 *
 * The vocabulary mirrors `backend/src/fieldclub/vocab.py`, and the layer ids,
 * titles and descriptions mirror `backend/src/fieldclub/layers.py`, both as of
 * November 2026. The catalogue has the shape the backend serves, but its
 * tiles come from public services that work with no backend running:
 *
 * - LIDAR views use the Environment Agency's hillshade WMS. Every LIDAR view
 *   shows that one hillshade until the backend renders the real styles. The
 *   service is slow at times and now and then leaves a tile unanswered.
 * - The elevation source is the Terrarium tile set on AWS Open Data.
 * - The map view is the OpenStreetMap standard layer.
 * - The overlay is OpenFreeMap's OpenMapTiles build.
 *
 * Records tiles and the findings endpoint keep their contract paths, which
 * answer nothing until the backend is running.
 *
 * Each class's `sensitivity` follows `PROTECTED_CLASSES` in vocab.py.
 */

const EA_ATTRIBUTION = "© Environment Agency copyright and/or database right 2022. All rights reserved.";

const DEM_ATTRIBUTION =
  "Elevation: Mapzen terrain tiles on AWS Open Data, from Environment Agency LIDAR and other open sources.";

// Attribution may carry links, as map attribution conventionally does. These two
// are the strings the backend's catalogue serves.
const OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const OPENFREEMAP_ATTRIBUTION =
  '<a href="https://openfreemap.org">OpenFreeMap</a> ' +
  '<a href="https://www.openmaptiles.org/">© OpenMapTiles</a> ' +
  'Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

/**
 * The WMS is asked for 512 px images on Web Mercator tile bounds. Requests of
 * that size bypass its tile cache, which is slow to fill, and are rendered
 * directly in about a second. Below zoom 10 a single image covers too much
 * one-metre data to render in time.
 */
const EA_HILLSHADE_TILES = [
  "https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wms" +
    "?service=WMS&version=1.3.0&request=GetMap&layers=Lidar_Composite_Hillshade_DTM_1m&styles=" +
    "&format=image/png&transparent=true&crs=EPSG:3857&width=512&height=512&bbox={bbox-epsg-3857}",
];

/** The licence every LIDAR view and the elevation are under, as the backend's catalogue names it. */
const OGL = {
  licence: "Open Government Licence v3.0",
  licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  reuse: "open",
} as const;

/** OpenStreetMap's data licence, for the standard map and the overlay. */
const ODBL = {
  licence: "Open Database License 1.0",
  licence_url: "https://www.openstreetmap.org/copyright",
  reuse: "share_alike",
} as const;

function lidarView(id: string, title: string, description: string, isDefault = false): RasterView {
  return {
    ...OGL,
    id,
    title,
    description,
    group: "lidar",
    type: "raster",
    tiles: EA_HILLSHADE_TILES,
    tile_size: 512,
    minzoom: 10,
    maxzoom: 16,
    attribution: EA_ATTRIBUTION,
    bounds: [-7.11, 49.85, 2.09, 55.88],
    ...(isDefault ? { default: true } : {}),
  };
}

/** A next step that a second look meets, and nothing else. */
function secondLookRule(id: string): NextStepRule {
  return {
    id,
    met_by: "second_look",
    evidence_kinds: [],
    record_relations: [],
    outcome: null,
    stance: null,
    endorsement: "not_needed",
    needs_verification: false,
  };
}

const vocab: Vocab = {
  feature_classes: [
    {
      id: "enclosure",
      label: "Enclosure",
      hint: "A patch of ground with a bank, a ditch or both running round it.",
      fish_term: "ENCLOSURE",
      sensitivity: "open",
    },
    {
      id: "hillfort",
      label: "Hillfort",
      hint: "A hilltop ringed by one or more big banks and ditches, usually Iron Age.",
      fish_term: "HILLFORT",
      sensitivity: "open",
    },
    {
      id: "round_barrow",
      label: "Round barrow or mound",
      hint: "A round burial mound, often with a ditch circling it, usually Bronze Age.",
      fish_term: "ROUND BARROW",
      sensitivity: "protected",
    },
    {
      id: "long_barrow",
      label: "Long barrow",
      hint: "A long, low burial mound from the Neolithic, often with a ditch down each side.",
      fish_term: "LONG BARROW",
      sensitivity: "protected",
    },
    {
      id: "hut_circle",
      label: "Hut circle",
      hint: "A low ring a few metres across, left by the wall of a prehistoric round house.",
      fish_term: "HUT CIRCLE",
      sensitivity: "open",
    },
    {
      id: "settlement",
      label: "Settlement earthworks",
      hint: "The bumps and hollows left by the houses, yards and lanes of an abandoned village or farm.",
      fish_term: "SETTLEMENT",
      sensitivity: "protected",
    },
    {
      id: "field_system",
      label: "Field system",
      hint: "A pattern of old field edges, seen as low banks, ditches or steps in a slope.",
      fish_term: "FIELD SYSTEM",
      sensitivity: "open",
    },
    {
      id: "ridge_and_furrow",
      label: "Ridge and furrow",
      hint: "Long parallel ridges, like corduroy, left by medieval and later ploughing.",
      fish_term: "RIDGE AND FURROW",
      sensitivity: "open",
    },
    {
      id: "linear",
      label: "Linear bank or ditch",
      hint: "A single bank or ditch running across country, such as an old boundary.",
      fish_term: "LINEAR EARTHWORK",
      sensitivity: "open",
    },
    {
      id: "trackway",
      label: "Trackway or hollow way",
      hint: "An old route worn into the ground by feet, hooves and wheels, often a sunken lane.",
      fish_term: "TRACKWAY",
      sensitivity: "open",
    },
    {
      id: "road",
      label: "Road",
      hint: "A built road, often straight and raised on a bank, such as a Roman road.",
      fish_term: "ROAD",
      sensitivity: "open",
    },
    {
      id: "moat",
      label: "Moat",
      hint: "A wide ditch, once full of water, round the island where a house stood.",
      fish_term: "MOAT",
      sensitivity: "open",
    },
    {
      id: "motte",
      label: "Motte or castle earthwork",
      hint: "A steep man-made mound or ring of bank built for an early castle.",
      fish_term: "MOTTE",
      sensitivity: "open",
    },
    {
      id: "platform",
      label: "Platform",
      hint: "A levelled patch cut into a slope or built out from it, where a building once stood.",
      fish_term: "BUILDING PLATFORM",
      sensitivity: "open",
    },
    {
      id: "pond",
      label: "Pond or water management",
      hint: "Ponds, dams and channels made to hold or move water, such as fishponds and water meadows.",
      fish_term: "POND",
      sensitivity: "open",
    },
    {
      id: "pit",
      label: "Pit or quarry",
      hint: "A hollow or cluster of hollows left by digging for stone, chalk, clay or ore.",
      fish_term: "EXTRACTIVE PIT",
      sensitivity: "open",
    },
    {
      id: "industrial",
      label: "Industrial",
      hint: "Remains of industry, such as spoil heaps, kilns, tramways and mine workings.",
      fish_term: "INDUSTRIAL SITE",
      sensitivity: "open",
    },
    {
      id: "military",
      label: "Military",
      hint: "Remains of defence or training, such as trenches, gun positions and airfields.",
      fish_term: "MILITARY INSTALLATION",
      sensitivity: "open",
    },
    {
      id: "ritual",
      label: "Ritual monument",
      hint: "A prehistoric ceremonial site, such as a henge, a stone circle or a cursus.",
      fish_term: "RELIGIOUS RITUAL AND FUNERARY",
      sensitivity: "protected",
    },
    {
      id: "garden",
      label: "Garden earthworks",
      hint: "Terraces, mounds, ponds and paths left by a formal garden that has gone.",
      fish_term: "GARDEN",
      sensitivity: "open",
    },
    {
      id: "unknown",
      label: "Not sure",
      hint: "You can see something but can't say what it is. Other people can help work it out.",
      fish_term: "SITE",
      sensitivity: "open",
    },
  ],
  periods: [
    {
      id: "prehistoric",
      label: "Prehistoric",
      hint: "Before AD 43, when you can't say which part",
    },
    {
      id: "neolithic",
      label: "Neolithic",
      hint: "4000 to 2500 BC",
    },
    {
      id: "bronze_age",
      label: "Bronze Age",
      hint: "2500 to 800 BC",
    },
    {
      id: "iron_age",
      label: "Iron Age",
      hint: "800 BC to AD 43",
    },
    {
      id: "roman",
      label: "Roman",
      hint: "AD 43 to 410",
    },
    {
      id: "early_medieval",
      label: "Early medieval",
      hint: "AD 410 to 1066",
    },
    {
      id: "medieval",
      label: "Medieval",
      hint: "1066 to 1540",
    },
    {
      id: "post_medieval",
      label: "Post-medieval",
      hint: "1540 to 1901",
    },
    {
      id: "modern",
      label: "Modern",
      hint: "1901 to today",
    },
    {
      id: "unknown",
      label: "Not sure",
      hint: "No guess at a date",
    },
  ],
  evidence_kinds: [
    {
      id: "lidar_view",
      label: "LIDAR view",
      strand: "lidar",
      group: "desk",
      hint: "Another LIDAR view that shows it, in a different style or with the light from another side.",
    },
    {
      id: "aerial",
      label: "Aerial photo",
      strand: "aerial",
      group: "desk",
      hint: "An aerial or satellite photo that shows it, as a mark in a crop, in bare soil or in shadow.",
    },
    {
      id: "historic_map",
      label: "Old map",
      strand: "historic_map",
      group: "desk",
      hint: "An old map that draws or names it, such as a first edition Ordnance Survey sheet.",
    },
    {
      id: "record_link",
      label: "Heritage record",
      strand: "records",
      group: "desk",
      hint: "A link to an existing record of the same site or one connected to it.",
    },
    {
      id: "document",
      label: "Book or report",
      strand: "literature",
      group: "desk",
      hint: "A book, article or report that mentions it.",
    },
    {
      id: "photo",
      label: "Ground photo",
      strand: "ground",
      group: "field",
      hint: "A photograph taken standing at the site.",
    },
    {
      id: "field_visit",
      label: "Site visit",
      strand: "ground",
      group: "field",
      hint: "Notes from someone who has been to look, with the landowner's permission.",
    },
    {
      id: "geophysics",
      label: "Geophysical survey",
      strand: "survey",
      group: "field",
      hint: "A survey that maps what lies under the surface without digging, such as magnetometry.",
    },
    {
      id: "excavation",
      label: "Excavation",
      strand: "survey",
      group: "field",
      hint: "A dig by archaeologists that tested what's there.",
    },
    {
      id: "her_record",
      label: "HER entry",
      strand: "official",
      group: "official",
      hint: "An entry in a Historic Environment Record, the local list of known sites.",
    },
    {
      id: "designation",
      label: "Designation",
      strand: "official",
      group: "official",
      hint: "Legal protection, such as being scheduled as an ancient monument.",
    },
    {
      id: "publication",
      label: "Publication",
      strand: "official",
      group: "official",
      hint: "A published account in a journal, a monograph or a report series.",
    },
  ],
  tiers: [
    {
      id: "spotted",
      label: "Spotted",
      description: "One person has marked it.",
      base_score: 10,
    },
    {
      id: "seen",
      label: "Seen by others",
      description: "At least two other people can see it too, and few can't.",
      base_score: 30,
    },
    {
      id: "corroborated",
      label: "Corroborated",
      description:
        "It shows up in two more kinds of evidence, such as an aerial photo and an old map, and people agree what it is.",
      base_score: 50,
    },
    {
      id: "probable",
      label: "Probable",
      description:
        "Reviewers have ruled out modern, natural and data-processing explanations, and an experienced reviewer agrees.",
      base_score: 70,
    },
    {
      id: "ground_checked",
      label: "Checked on the ground",
      description: "Someone has visited or surveyed it and what they found supports it.",
      base_score: 85,
    },
    {
      id: "confirmed",
      label: "On record",
      description: "A Historic Environment Record, a designation or a publication now includes it.",
      base_score: 100,
    },
  ],
  states: [
    {
      id: "open",
      label: "Open",
      description: "Still being looked at.",
    },
    {
      id: "known",
      label: "Matches a known record",
      description: "It's the same thing as an existing heritage record, which is linked from the finding.",
    },
    {
      id: "disputed",
      label: "Disputed",
      description: "People or evidence disagree about it.",
    },
    {
      id: "ruled_out",
      label: "Explained",
      description: "Most people can't see it, or it turned out to be modern, natural or a fault in the data.",
    },
    {
      id: "withdrawn",
      label: "Withdrawn",
      description: "The finder took it back.",
    },
  ],
  checks: [
    {
      id: "not_modern",
      question: "Could it be modern?",
      hint: "Drains, pipelines, golf bunkers, vehicle tracks and recent field edges can all look old in LIDAR.",
    },
    {
      id: "not_natural",
      question: "Could it be natural?",
      hint: "Old river channels, landslips, sinkholes and frost patterns make shapes that look built.",
    },
    {
      id: "not_artefact",
      question: "Could it be a fault in the data?",
      hint: "Stripes where survey flights overlap, steps at tile edges and blotches under trees come from processing, not from the ground.",
    },
  ],
  explanations: [
    {
      id: "modern",
      label: "Modern feature",
      hint: "Something recent, such as a drain, a pipeline, a bunker or a vehicle track.",
    },
    {
      id: "natural",
      label: "Natural feature",
      hint: "Shaped by water, ice or geology, not by people.",
    },
    {
      id: "artefact",
      label: "Data artefact",
      hint: "A stripe, step or blotch that comes from how the LIDAR was flown or processed.",
    },
  ],
  mention_kinds: [
    {
      id: "video",
      label: "Video",
    },
    {
      id: "article",
      label: "Article",
    },
    {
      id: "podcast",
      label: "Podcast",
    },
    {
      id: "paper",
      label: "Paper",
    },
    {
      id: "broadcast",
      label: "Broadcast",
    },
    {
      id: "social",
      label: "Social post",
    },
  ],
  record_categories: [
    {
      id: "designation",
      label: "Designations",
      colour: "#d9544d",
    },
    {
      id: "monument",
      label: "Monument records",
      colour: "#4fb3a5",
    },
    {
      id: "find",
      label: "Finds",
      colour: "#e6c84f",
    },
    {
      id: "event",
      label: "Fieldwork",
      colour: "#6ba6c9",
    },
    {
      id: "document",
      label: "Reports and publications",
      colour: "#b08fd8",
    },
    {
      id: "community",
      label: "Community data",
      colour: "#7fb069",
    },
    {
      id: "map_label",
      label: "Antiquities on old maps",
      colour: "#c9a27e",
    },
  ],
  // The backend's `confidence.STEP_RULES`, as `/meta` serves them.
  next_steps: [
    secondLookRule("need_observers"),
    {
      id: "need_strand",
      met_by: "evidence",
      evidence_kinds: ["lidar_view", "aerial", "historic_map", "record_link", "document"],
      record_relations: ["part_of", "related"],
      outcome: null,
      stance: "supports",
      endorsement: "if_added_by_finder",
      needs_verification: false,
    },
    secondLookRule("need_class_agreement"),
    secondLookRule("need_check"),
    secondLookRule("need_trusted_review"),
    {
      id: "need_ground",
      met_by: "evidence",
      evidence_kinds: ["photo", "field_visit", "geophysics", "excavation"],
      record_relations: [],
      outcome: "supports",
      stance: null,
      endorsement: "unless_added_by_trusted_other",
      needs_verification: false,
    },
    {
      id: "need_official",
      met_by: "evidence",
      evidence_kinds: ["her_record", "designation", "publication"],
      record_relations: [],
      outcome: null,
      stance: "supports",
      endorsement: "not_needed",
      needs_verification: true,
    },
  ],
  report_reasons: [
    {
      id: "location_risk",
      label: "Puts a site at risk",
      hint: "It could lead someone to damage a site or dig or detect there.",
      due_hours: null,
    },
    {
      id: "illegal",
      label: "Illegal",
      hint: "It encourages a crime, such as metal detecting on a scheduled monument.",
      due_hours: null,
    },
    {
      id: "intimate_image",
      label: "Intimate image",
      hint: "A sexual or intimate image of someone shared without their consent.",
      due_hours: 48,
    },
    {
      id: "privacy",
      label: "Reveals personal details",
      hint: "It identifies a person, a home or a private garden, or says who owns the land.",
      due_hours: null,
    },
    {
      id: "defamation",
      label: "Untrue about a person",
      hint: "It says something untrue that harms a person's or an organisation's reputation.",
      due_hours: 48,
    },
    { id: "abuse", label: "Abusive", hint: "Harassment, threats, hate or bullying of anyone.", due_hours: null },
    {
      id: "under_age",
      label: "Under 16",
      hint: "The person behind this account seems to be younger than 16.",
      due_hours: null,
    },
    { id: "spam", label: "Spam", hint: "Advertising, or posts that have nothing to do with the map.", due_hours: null },
    {
      id: "misleading",
      label: "Deliberately false",
      hint: "Made up on purpose, such as a fake finding or a doctored picture.",
      due_hours: null,
    },
    { id: "other", label: "Something else", hint: "Tell the moderators what is wrong in the note.", due_hours: null },
  ],
};

export const metaFixture: Meta = {
  app: { name: "Open Antiquity", version: "0.1.0", contribution_licence: "CC BY 4.0" },
  auth: {
    providers: [
      { id: "google", label: "Google", enabled: true },
      { id: "apple", label: "Apple", enabled: false },
      { id: "osm", label: "OpenStreetMap", enabled: true },
      { id: "email", label: "Email link", enabled: true },
    ],
    age_bands: ["16_17", "18_plus"],
    terms: {
      summary:
        "You're 16 or over. What you add is public and published under CC BY 4.0, so anyone may reuse it with credit. If you leave, it stays on the map, credited to “Former member”.",
      url: "/about#terms",
    },
  },
  vocab,
  layers: {
    views: [
      lidarView(
        "composite",
        "Composite",
        "Sky-view, openness, slope and hillshade blended. Shows most earthworks with no light to aim.",
        true,
      ),
      lidarView(
        "local_relief",
        "Local relief",
        "Takes away the hills and keeps the small stuff. Best for ploughed-down features on flat ground.",
      ),
      lidarView(
        "sky_view",
        "Sky-view",
        "Ditches and hollows go dark, banks go bright. Good for enclosures and hollow ways.",
      ),
      lidarView(
        "multi_shade",
        "Multi-direction shade",
        "Three lights in red, green and blue, so nothing hides by running parallel to the sun.",
      ),
      lidarView("slope", "Slope", "Steepness. Picks out the sharp edges of platforms, lynchets and quarries."),
      lidarView(
        "openness",
        "Openness",
        "How much sky each spot sees, without the light. Banks and ridges go bright, ditches dark.",
      ),
      {
        id: "raking",
        title: "Raking light",
        description: "Low light from a side you choose. Drag the sun round and watch faint ridges appear.",
        group: "lidar",
        type: "raking",
        attribution: DEM_ATTRIBUTION,
        ...OGL,
      },
      {
        id: "osm_standard",
        title: "OpenStreetMap",
        description: "The standard OpenStreetMap map, for roads, paths and place names.",
        group: "map",
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tile_size: 256,
        minzoom: 0,
        maxzoom: 19,
        attribution: OSM_ATTRIBUTION,
        ...ODBL,
        bounds: null,
      },
    ],
    dem: {
      tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
      tile_size: 256,
      encoding: "terrarium",
      minzoom: 0,
      maxzoom: 15,
      attribution: DEM_ATTRIBUTION,
      ...OGL,
    },
    overlays: [
      {
        id: "osm",
        title: "OpenStreetMap",
        type: "openmaptiles",
        tilejson: "https://tiles.openfreemap.org/planet",
        glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
        default_opacity: 0.8,
        attribution: OPENFREEMAP_ATTRIBUTION,
        ...ODBL,
      },
      {
        id: "records",
        title: "Heritage records",
        type: "records",
        tiles: ["/tiles/records/{z}/{x}/{y}.mvt?v=fixture1"],
      },
      { id: "findings", title: "Findings", type: "findings" },
      { id: "coverage", title: "Scan coverage", type: "coverage" },
    ],
    initial_view: { center: [-1.8542, 51.4286], zoom: 14 },
  },
  sources: [
    {
      key: "nhle-scheduled",
      name: "Scheduled monuments in England",
      publisher: "Historic England",
      licence: "OGL v3.0",
      attribution: "© Historic England. Contains Ordnance Survey data © Crown copyright and database right.",
      homepage: "https://historicengland.org.uk/listing/the-list/",
      category: "designation",
      access: "bulk",
      record_count: 0,
    },
  ],
  notices: {
    field_visit: {
      england: [
        "Get the landowner's permission before you leave a public right of way or open access land.",
        "Look, photograph and take notes. Never dig, and don't take anything away.",
        "Using a metal detector on a scheduled monument without written consent from Historic England is a criminal offence.",
        "Report anything you find to the Portable Antiquities Scheme. Possible treasure must be reported to the coroner within 14 days.",
      ],
      scotland: [
        "You have a right of responsible access to most land. Follow the Scottish Outdoor Access Code, and ask before going near houses, farmyards or growing crops.",
        "Look, photograph and take notes. Never dig, and don't take anything away.",
        "Using a metal detector on a scheduled monument without written consent from Historic Environment Scotland is a criminal offence.",
        "Every archaeological find in Scotland, whatever it's made of, must be reported to the Treasure Trove Unit.",
      ],
      wales: [
        "Get the landowner's permission before you leave a public right of way or open access land.",
        "Look, photograph and take notes. Never dig, and don't take anything away.",
        "Using a metal detector on a scheduled monument without written consent from Cadw is a criminal offence.",
        "Report anything you find to the Portable Antiquities Scheme in Wales. Possible treasure must be reported to the coroner within 14 days.",
      ],
      northern_ireland: [
        "Get the landowner's permission before you go onto private land.",
        "Look, photograph and take notes. Digging to search for archaeological objects anywhere in Northern Ireland needs a licence from the Department for Communities.",
        "Using a metal detector on a scheduled monument or a monument in state care without written consent from the Department for Communities is a criminal offence.",
        "Any archaeological object you find must be reported within 14 days to the Ulster Museum, the police or the Department for Communities.",
      ],
    },
    find_reporting: {
      england: {
        scheme: "Portable Antiquities Scheme",
        url: "https://finds.org.uk/",
        text: "Report anything you find to the Portable Antiquities Scheme. Possible treasure must be reported to the coroner within 14 days.",
      },
      scotland: {
        scheme: "Treasure Trove Scotland",
        url: "https://treasuretrovescotland.co.uk/",
        text: "Every archaeological object you find, whatever it's made of, must be reported to Treasure Trove.",
      },
      wales: {
        scheme: "Portable Antiquities Scheme in Wales",
        url: "https://finds.org.uk/",
        text: "Report anything you find to the Portable Antiquities Scheme in Wales. Possible treasure must be reported to the coroner within 14 days.",
      },
      northern_ireland: {
        scheme: "Department for Communities",
        url: null,
        text: "Report any archaeological object you find within 14 days, to the Ulster Museum, the police or the Department for Communities. Possible treasure must be reported to the coroner within 14 days.",
      },
    },
    field_visit_16_17: "You're 16 or 17, so go with an adult you know, and tell someone at home where you're going.",
    sensitivity:
      "Some findings have their position hidden to protect the site, and are shown as a one-kilometre square. Protected findings are exact once you sign in. Restricted findings are exact only to their finder, trusted members, archaeologists and moderators.",
  },
  terrain: { fine_minzoom: 13, catalogue_tiles: 5877, overview: { built: false, built_at: null, tiles: 0 } },
};
