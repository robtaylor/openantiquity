/**
 * The guide's pictures and the places they show, with the words that go with
 * them. Layers, feature classes and explanations are named here by their id
 * only: their names come from `/meta`, and a picture whose view `/meta`
 * doesn't list is left out (`viewNotesFor`).
 *
 * Every picture was made from Field Club's own terrain tiles of the 2022
 * Environment Agency composite: the raking-light one as the map draws it in
 * the browser, the others straight from the rendered tiles. `pictures/README.md` says where each one is
 * and which view it uses. What each real example is comes from the heritage
 * records in the index, named in `records`. A look-alike that no record names
 * is marked `judgement`, and the page says so.
 */

import type { Meta, View } from "../../api/meta.js";
import barrowPicture from "./pictures/pair-barrow-overton.webp";
import dewPondPicture from "./pictures/pair-dewpond-barbury.webp";
import enclosurePicture from "./pictures/pair-enclosure-barbury.webp";
import fieldsPicture from "./pictures/pair-fields-fyfield.webp";
import hollowWayPicture from "./pictures/pair-hollowway-fyfield.webp";
import ploughPicture from "./pictures/pair-plough-milkhill.webp";
import reservoirPicture from "./pictures/pair-reservoir-bulford.webp";
import ridgePicture from "./pictures/pair-ridge-furrow-pewsey.webp";
import compositePicture from "./pictures/view-composite.webp";
import localReliefPicture from "./pictures/view-local-relief.webp";
import multiShadePicture from "./pictures/view-multi-shade.webp";
import opennessPicture from "./pictures/view-openness.webp";
import rakingPicture from "./pictures/view-raking.webp";
import skyViewPicture from "./pictures/view-sky-view.webp";
import slopePicture from "./pictures/view-slope.webp";

/** A place on the map, and the view and zoom to show it in. */
export interface Place {
  /** Where it is, in a few words, such as "Fyfield Down, near Avebury". */
  name: string;
  lon: number;
  lat: number;
  /** A view id from `/meta`. */
  layer: string;
  zoom: number;
}

export interface Picture {
  src: string;
  /** What the picture shows, for anyone who can't see it. */
  alt: string;
}

/** The two sentences on what a terrain view is good for, and a picture of it. */
export interface ViewNote {
  /** A view id from `/meta`. */
  view: string;
  sentences: [string, string];
  picture?: Picture;
}

/** Every picture of a view shows the same piece of Fyfield Down, so they can be compared. */
export const VIEW_PLACE: Omit<Place, "layer"> = {
  name: "Fyfield Down, near Avebury",
  lon: -1.8105,
  lat: 51.436,
  zoom: 15,
};

const VIEW_ALT =
  "Fyfield Down from above: small square fields outlined by low banks, sunken tracks fanning across the down, and a dry valley curving through.";

export const VIEW_NOTES: ViewNote[] = [
  {
    view: "composite",
    sentences: [
      "Several ways of shading the ground blended into one picture, so most banks, ditches and mounds show without choosing where the light comes from.",
      "Start here, and switch to another view when something needs a closer look.",
    ],
    picture: { src: compositePicture, alt: VIEW_ALT },
  },
  {
    view: "local_relief",
    sentences: [
      "The hills and valleys are taken away, and only the small bumps and dips are left.",
      "It's the best view for ploughed-down features on flat ground, but it can make a gentle natural slope look like a bank.",
    ],
    picture: { src: localReliefPicture, alt: VIEW_ALT },
  },
  {
    view: "sky_view",
    sentences: [
      "Each spot is shaded by how much open sky it can see, so ditches and hollows go dark and banks go bright.",
      "It's good for enclosures and hollow ways, and it never hides a feature in shadow.",
    ],
    picture: { src: skyViewPicture, alt: VIEW_ALT },
  },
  {
    view: "multi_shade",
    sentences: [
      "Three lights from different directions, in red, green and blue, mixed into one picture.",
      "A bank shows whichever way it runs, and its colour tells you which way each slope faces.",
    ],
    picture: { src: multiShadePicture, alt: VIEW_ALT },
  },
  {
    view: "slope",
    sentences: [
      "The steeper the ground, the darker it's drawn, and level ground fades to white.",
      "It picks out the sharp edges of platforms, lynchets and quarries, and makes soft, spread mounds hard to see.",
    ],
    picture: { src: slopePicture, alt: VIEW_ALT },
  },
  {
    view: "openness",
    sentences: [
      "Like sky-view, but measured across a wider stretch of ground, with no light at all.",
      "Ridges and banks go bright and ditches dark, which helps with broad, low earthworks.",
    ],
    picture: { src: opennessPicture, alt: VIEW_ALT },
  },
  {
    view: "raking",
    sentences: [
      "One low sun that you move yourself, drawn in your browser from the height of the ground.",
      "Turn it slowly: a faint ridge often shows only when the light falls across it, and disappears when the light runs along it.",
    ],
    picture: {
      src: rakingPicture,
      alt: "Silbury Hill lit by a low sun from the north-west: the great mound bright on one side and black on the other, with its silted ditch around it.",
    },
  },
];

/** Silbury Hill, where the guide sends someone to try raking light. */
export const RAKING_PLACE: Place = {
  name: "Silbury Hill, near Avebury",
  lon: -1.8574,
  lat: 51.4157,
  layer: "raking",
  zoom: 16,
};

/** A record in the index that says what a real example is. */
export interface RecordRef {
  /** The record's name in its source, shortened where it is long. */
  name: string;
  /** The source as it reads after "in", such as "the National Heritage List for England". */
  source: string;
  /** Its number in that source, where it has a public one. */
  reference?: string;
  url?: string;
}

export interface Example {
  title: string;
  /** A feature class id from `/meta`, for a real earthwork. */
  featureClass?: string;
  /** An explanation id from `/meta`, for a look-alike that is modern, natural or in the data. */
  explanation?: string;
  /** What to look at, in a sentence or two. */
  body: string;
  place?: Place;
  picture?: Picture;
  /** The records that say what it is. Empty for one that is our own judgement. */
  records: RecordRef[];
  /** True when no record names it, and calling it what it is is our own judgement. */
  judgement: boolean;
  /** Said when there is no picture, to say why. */
  noPicture?: string;
}

export interface Pair {
  id: string;
  real: Example;
  lookalike: Example;
  /** How to tell them apart, in a sentence or two. */
  tell: string;
}

const NHLE = "the National Heritage List for England";
const AIM = "Historic England's aerial investigation and mapping";

function nhle(name: string, reference: string): RecordRef {
  return {
    name,
    source: NHLE,
    reference,
    url: `https://historicengland.org.uk/listing/the-list/list-entry/${reference}`,
  };
}

const aim = (name: string): RecordRef => ({ name, source: AIM });

export const PAIRS: Pair[] = [
  {
    id: "barrow",
    real: {
      title: "A round barrow",
      featureClass: "round_barrow",
      body: "A bell barrow on Overton Hill: a smooth, round mound with the faint ring of its ditch around the foot.",
      place: { name: "Overton Hill, near Avebury", lon: -1.83245, lat: 51.42147, layer: "composite", zoom: 16 },
      picture: {
        src: barrowPicture,
        alt: "A round mound with a ring around its foot, alone in a large field crossed by a modern track.",
      },
      records: [nhle("Bell barrow 400m north-east of West Kennett Farm on Overton Hill", "1008099")],
      judgement: false,
    },
    lookalike: {
      title: "A small reservoir",
      explanation: "modern",
      body: "South of Bulford Camp a small round reservoir, with a sharp rim and a hollow middle, sits beside three bowl barrows. The barrows are the soft domes to its left.",
      place: {
        name: "South of Bulford Camp, near Stonehenge",
        lon: -1.7327,
        lat: 51.1858,
        layer: "composite",
        zoom: 16,
      },
      picture: {
        src: reservoirPicture,
        alt: "Three small round mounds and, a little to the right, a ring with a hollow centre, at the edge of a field beside buildings and yards.",
      },
      records: [aim("Reservoir"), nhle("A group of five bowl barrows south of Bulford Camp", "1009576")],
      judgement: false,
    },
    tell: "Spoil heaps, muck heaps and golf bunkers fool people too. Look for sharp edges, odd shapes and what's next door: a quarry, a farmyard or a fairway.",
  },
  {
    id: "fields",
    real: {
      title: "A field system",
      featureClass: "field_system",
      body: "Small, squarish prehistoric fields on Fyfield Down, outlined by lynchets: banks of soil that built up against the field edges as the land was ploughed.",
      place: { name: "Fyfield Down, near Avebury", lon: -1.815, lat: 51.433, layer: "composite", zoom: 16 },
      picture: {
        src: fieldsPicture,
        alt: "A patchwork of small rectangular plots, each edged by a low bank, across a gently sloping down.",
      },
      records: [
        nhle("Prehistoric to post-medieval remains on Fyfield, Overton and Manton Downs", "1019190"),
        aim("Clearance cairn, field system, strip lynchet"),
      ],
      judgement: false,
    },
    lookalike: {
      title: "Plough marks",
      explanation: "modern",
      body: "Fine, evenly spaced lines that fill one modern field, left by modern ploughing and drilling. The curving bank above them is a real earthwork: Historic England's aerial mapping records it as a strip lynchet of a medieval field system.",
      place: { name: "Below Milk Hill, Vale of Pewsey", lon: -1.85715, lat: 51.36959, layer: "local_relief", zoom: 16 },
      picture: {
        src: ploughPicture,
        alt: "A flat field covered in fine parallel lines running from side to side, with a curving bank across the top.",
      },
      records: [],
      judgement: true,
    },
    tell: "Old field banks are uneven, meet at odd angles and ignore today's hedges. Plough lines are dead straight, closely spaced and end exactly at the edge of a modern field.",
  },
  {
    id: "hollow_way",
    real: {
      title: "A hollow way",
      featureClass: "trackway",
      body: "Sunken tracks fan out across Fyfield Down where an old route climbs onto the down and traffic spread out to find firmer ground.",
      place: { name: "Fyfield Down, near Avebury", lon: -1.8122, lat: 51.4371, layer: "sky_view", zoom: 16 },
      picture: {
        src: hollowWayPicture,
        alt: "A bundle of narrow dark grooves that run side by side, split and rejoin as they cross the picture.",
      },
      records: [aim("Trackway")],
      judgement: false,
    },
    lookalike: {
      title: "A pipeline",
      explanation: "modern",
      body: "A buried pipe or cable leaves a dead straight line, a slight ridge or a strip of different growth, that crosses hedges, roads and slopes without turning.",
      records: [],
      judgement: true,
      noPicture:
        "We haven't yet found a clear pipeline in the stretch of terrain we can draw, so there's no picture of one here.",
    },
    tell: "A hollow way bends with the ground, deepens on slopes and splits where people went round a bad patch. Anything that runs straight through a hedge and on across the next field is almost certainly modern.",
  },
  {
    id: "enclosure",
    real: {
      title: "An enclosure",
      featureClass: "enclosure",
      body: "A banked rectangular enclosure on the down north of Barbury Castle. It is scheduled together with the dew pond beside it.",
      place: {
        name: "North of Barbury Castle, Marlborough Downs",
        lon: -1.78705,
        lat: 51.48975,
        layer: "composite",
        zoom: 16,
      },
      picture: {
        src: enclosurePicture,
        alt: "A large rectangle outlined by a bank, with a much smaller square banked hollow just below its corner.",
      },
      records: [nhle("Earthwork enclosure and dewpond 490m north of Barbury Castle", "1016357")],
      judgement: false,
    },
    lookalike: {
      title: "A dew pond",
      body: "A dew pond is a hollow lined to hold rainwater for stock, ringed by the bank of the soil dug out of it. This one is the small square below the enclosure.",
      place: {
        name: "North of Barbury Castle, Marlborough Downs",
        lon: -1.78619,
        lat: 51.48922,
        layer: "composite",
        zoom: 16,
      },
      picture: {
        src: dewPondPicture,
        alt: "Close up, a small square bank around a hollow, with tracks passing nearby.",
      },
      records: [nhle("Earthwork enclosure and dewpond 490m north of Barbury Castle", "1016357")],
      judgement: false,
    },
    tell: "A pond is small, a few metres to a few tens of metres across, with a deep middle and a bank all round. An enclosure is usually bigger, often has an entrance, and its middle is level with the ground outside.",
  },
  {
    id: "ridge_and_furrow",
    real: {
      title: "Ridge and furrow",
      featureClass: "ridge_and_furrow",
      body: "Broad ridges ploughed up in the Middle Ages, several metres apart and slightly curved, on Pewsey Down.",
      place: { name: "Pewsey Down", lon: -1.82729, lat: 51.37596, layer: "local_relief", zoom: 16 },
      picture: {
        src: ridgePicture,
        alt: "Broad, gently curving parallel ridges in one part of a field, cut off by a later field edge.",
      },
      records: [aim("Ridge and furrow")],
      judgement: false,
    },
    lookalike: {
      title: "Stripes in the data",
      explanation: "artefact",
      body: "LIDAR is flown in overlapping strips. Where two strips meet, or the scanner wobbled, the ground can show faint, perfectly even stripes or a step along a straight line.",
      records: [],
      judgement: true,
      noPicture:
        "We haven't yet found a clear example in the stretch of terrain we can draw, so there's no picture of one here.",
    },
    tell: "Real ridges stop at old field edges and change direction from one furlong to the next. Data stripes keep one direction across fields, hedges, roads and woods alike, often for kilometres.",
  },
];

/** The lidar views in `/meta`, in its order, each with the guide's note where the guide has one. */
export function viewNotesFor(meta: Meta): { view: View; note: ViewNote | undefined }[] {
  return meta.layers.views
    .filter((view) => view.group === "lidar")
    .map((view) => ({ view, note: VIEW_NOTES.find((note) => note.view === view.id) }));
}

/** A feature class's name from `/meta`, or null when it doesn't list the class. */
export function featureClassLabel(meta: Meta, id: string | undefined): string | null {
  return id ? (meta.vocab.feature_classes.find((item) => item.id === id)?.label ?? null) : null;
}

/** An explanation's name from `/meta`, or null when it doesn't list it. */
export function explanationLabel(meta: Meta, id: string | undefined): string | null {
  return id ? (meta.vocab.explanations.find((item) => item.id === id)?.label ?? null) : null;
}
