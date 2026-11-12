import { ExternalLink, MapPin } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { Link } from "react-router";
import { findOverlay, type Meta } from "../../api/meta.js";
import { Attribution, safeHref } from "../../map/attribution.js";
import { Button } from "../../ui/Button.js";
import { scrollBehaviour } from "../../ui/motion.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { takesUnder18s } from "../about/facts.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { nationName } from "./nations.js";
import {
  type Example,
  explanationLabel,
  featureClassLabel,
  PAIRS,
  type Pair,
  type Place,
  RAKING_PLACE,
  VIEW_PLACE,
  viewNotesFor,
} from "./places.js";
import { type MapPlace, showPlace } from "./showPlace.js";
import "./guide.css";

export const GUIDE_PATH = "/guide";

const SECTIONS = [
  { id: "guide-views", title: "The views" },
  { id: "guide-lookalikes", title: "Real or not?" },
  { id: "guide-ladder", title: "How a finding climbs" },
  { id: "guide-ground", title: "On the ground" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

/** "A pipeline" as it reads after "or": "a pipeline". */
function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** Go to a section of the page: scroll it into view and put keyboard focus on its heading. */
function jumpTo(id: SectionId): void {
  const heading = document.getElementById(id);
  if (!heading) return;
  heading.scrollIntoView({ behavior: scrollBehaviour(), block: "start" });
  heading.focus({ preventScroll: true });
}

function Section({ id, title, children }: { id: SectionId; title: string; children: ReactNode }) {
  return (
    <section className="fc-guide__section" aria-labelledby={id}>
      <h3 className="fc-guide__heading" id={id} tabIndex={-1}>
        {title}
      </h3>
      {children}
    </section>
  );
}

/**
 * "Show tramlines on the map": opens the place in its view, and calls a
 * slow move off if the page goes first. The words name the example, so the
 * button's name is the words it shows (WCAG 2.5.3).
 */
function ShowOnMap({ meta, place, label }: { meta: Meta; place: MapPlace; label: string }) {
  const environment = usePanelEnvironment();
  const cancel = useRef<(() => void) | null>(null);
  useEffect(() => () => cancel.current?.(), []);
  return (
    <Button
      size="sm"
      variant="ghost"
      icon={<MapPin size={16} aria-hidden />}
      onClick={() => {
        cancel.current?.();
        cancel.current = showPlace(meta, place, environment);
      }}
    >
      {label}
    </Button>
  );
}

function Views({ meta }: { meta: Meta }) {
  const views = viewNotesFor(meta);
  const credit = views.find(({ note }) => note?.picture)?.view.attribution;
  const lines = findOverlay(meta, "openmaptiles")?.attribution;
  return (
    <>
      <p>
        Each view below draws the ground in a different way. Most of the pictures show the same piece of{" "}
        {VIEW_PLACE.name}, about a kilometre across, so you can compare them. Try each view on the map: a feature that
        hides in one often stands out in another.
      </p>
      <ul className="fc-guide__views">
        {views.map(({ view, note }) => {
          const place: MapPlace = view.type === "raking" ? RAKING_PLACE : { ...VIEW_PLACE, layer: view.id };
          return (
            <li key={view.id} className="fc-guide__card">
              <h4 className="fc-guide__card-title">{view.title}</h4>
              {note?.picture ? (
                <img
                  className="fc-guide__picture"
                  src={note.picture.src}
                  alt={note.picture.alt}
                  width={480}
                  height={300}
                  loading="lazy"
                />
              ) : null}
              <p>{note ? note.sentences.join(" ") : view.description}</p>
              {view.type === "raking" ? (
                <p className="fc-guide__muted">
                  The picture is {RAKING_PLACE.name}. On the map, drag the sun round and watch it change.
                </p>
              ) : null}
              <ShowOnMap meta={meta} place={place} label={`Show ${view.title} on the map`} />
            </li>
          );
        })}
      </ul>
      {credit ? (
        <p className="fc-guide__credit">
          The pictures in this guide are drawn by OpenAntiquity from LIDAR elevation: <Attribution html={credit} />
          {lines ? (
            <>
              {" "}
              Map lines on the raking-light picture: <Attribution html={lines} />
            </>
          ) : null}
        </p>
      ) : null}
    </>
  );
}

function Records({ example }: { example: Example }) {
  if (example.judgement) {
    return (
      <p className="fc-guide__judgement">
        This one is our own judgement. No heritage record says what it is, so treat it as an example of the kind of
        thing, not a fact about the place.
      </p>
    );
  }
  return (
    <p className="fc-guide__muted">
      Recorded as{" "}
      {example.records.map((record, index) => (
        <span key={`${record.source}-${record.name}`}>
          {index > 0 ? "; and " : null}“{record.name}” in {record.source}
          {record.reference && safeHref(record.url) ? (
            <>
              {", "}
              <a href={safeHref(record.url)} target="_blank" rel="noopener noreferrer">
                entry {record.reference}
                <ExternalLink size={12} aria-hidden className="fc-guide__external" />
                <span className="fc-visually-hidden"> (opens in a new tab)</span>
              </a>
            </>
          ) : null}
        </span>
      ))}
      .
    </p>
  );
}

function ExampleCard({ meta, example, side }: { meta: Meta; example: Example; side: "real" | "lookalike" }) {
  const kind =
    side === "real" ? featureClassLabel(meta, example.featureClass) : explanationLabel(meta, example.explanation);
  const place: Place | undefined = example.place;
  return (
    <div className="fc-guide__card" data-side={side}>
      <p className="fc-guide__tag">
        <span className="fc-guide__tag-side">{side === "real" ? "Earthwork" : "Look-alike"}</span>
        {kind ? <span>{kind}</span> : null}
      </p>
      <h5 className="fc-guide__card-title">{example.title}</h5>
      {example.picture ? (
        <img
          className="fc-guide__picture"
          src={example.picture.src}
          alt={example.picture.alt}
          width={480}
          height={300}
          loading="lazy"
        />
      ) : example.noPicture ? (
        <p className="fc-guide__no-picture">{example.noPicture}</p>
      ) : null}
      <p>{example.body}</p>
      {place ? <p className="fc-guide__muted">{place.name}.</p> : null}
      {example.picture?.enhanced ? (
        <p className="fc-guide__muted">The picture's contrast has been raised, so it shows more than the map does.</p>
      ) : null}
      <Records example={example} />
      {place ? <ShowOnMap meta={meta} place={place} label={`Show ${example.title.toLowerCase()} on the map`} /> : null}
    </div>
  );
}

function PairItem({ meta, pair }: { meta: Meta; pair: Pair }) {
  const headingId = `guide-pair-${pair.id}`;
  return (
    <li className="fc-guide__pair" aria-labelledby={headingId}>
      <h4 className="fc-guide__pair-title" id={headingId}>
        {pair.real.title} or {lowerFirst(pair.lookalike.title)}?
      </h4>
      <ExampleCard meta={meta} example={pair.real} side="real" />
      <ExampleCard meta={meta} example={pair.lookalike} side={pair.lookalike.featureClass ? "real" : "lookalike"} />
      <p className="fc-guide__tell">
        <strong>Telling them apart. </strong>
        {pair.tell}
      </p>
    </li>
  );
}

function Lookalikes({ meta }: { meta: Meta }) {
  return (
    <>
      <p>
        Most of what looks like an earthwork in LIDAR isn't one. Here are real earthworks beside the modern or natural
        things most often mistaken for them, and two kinds of earthwork that are easily confused. Marking a doubtful
        feature is still useful, because other people's second looks are how doubtful things get checked.
      </p>
      <ul className="fc-guide__pairs">
        {PAIRS.map((pair) => (
          <PairItem key={pair.id} meta={meta} pair={pair} />
        ))}
      </ul>
      <p className="fc-guide__muted">
        A good test from Historic England's air photo mappers: a feature that runs straight through a modern road or
        hedge is very unlikely to be old.
      </p>
    </>
  );
}

function Ladder({ meta }: { meta: Meta }) {
  const ruledOut = meta.vocab.states.find((state) => state.id === "ruled_out");
  return (
    <>
      <p>
        Every finding sits on a ladder of named steps. Each step has a rule anyone can read, and the finding's page says
        what's missing for the next one.
      </p>
      <ol className="fc-guide__ladder">
        {meta.vocab.tiers.map((tier) => (
          <li key={tier.id}>
            <TierBadge tier={tier} size="sm" />
            <span>{tier.description}</span>
          </li>
        ))}
      </ol>
      <p>
        Two rules keep the ladder honest. Agreement is weighted, so a trusted regular or a recognised archaeologist
        counts for more than one member. And the evidence has to be independent: a finder can't corroborate their own
        finding by attaching five screenshots.
      </p>
      <p>
        A finding can also leave the ladder. If most people can't see it, or agree it's a modern drain, a golf bunker or
        a processing stripe, it's marked {ruledOut ? <strong>{ruledOut.label.toLowerCase()}</strong> : "as explained"},
        with the reason. That's a useful result. It stays on the map so the next person doesn't mark the same thing.
      </p>
      <p>
        Each step a finding still needs is offered to everyone else as a small task, in{" "}
        <Link to="/review">Second look</Link> and <Link to="/help">Help wanted</Link>.
      </p>
    </>
  );
}

const DO = [
  "Stay on public rights of way and open access land unless the landowner has said yes.",
  "Look, photograph and take notes, and log what you saw on the finding's page.",
  "Leave gates as you found them, keep dogs on a lead near stock, and keep off growing crops.",
  "Tell someone where you're going, and take a map and a charged phone.",
];

const DONT = [
  "Don't take a marker on this map as permission to visit.",
  "Don't dig, probe or use a metal detector, and don't take anything away.",
  "Don't climb on banks or walls, or drive onto a site.",
  "Don't post the exact place of a protected or restricted finding anywhere else.",
];

function Ground({ meta }: { meta: Meta }) {
  const nations = Object.entries(meta.notices.field_visit);
  return (
    <>
      <p>
        Most earthworks are on private farmland. A visit is the best evidence there is, and it's also the easiest way to
        damage a site or annoy the people who look after it.
      </p>
      <div className="fc-guide__dos">
        <div>
          <h4 className="fc-guide__card-title">Do</h4>
          <ul className="fc-guide__list">
            {DO.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="fc-guide__card-title">Don't</h4>
          <ul className="fc-guide__list">
            {DONT.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </div>
      <p>The law is different in each nation. Before you log a visit, OpenAntiquity shows the rules for where it is:</p>
      {nations.map(([nation, lines]) => {
        const route = meta.notices.find_reporting[nation];
        return (
          <details key={nation} className="fc-guide__nation">
            <summary>{nationName(nation)}</summary>
            <ul className="fc-guide__list">
              {lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            {route && safeHref(route.url) ? (
              <p>
                <a href={safeHref(route.url)} target="_blank" rel="noopener noreferrer">
                  {route.scheme} website
                  <ExternalLink size={12} aria-hidden className="fc-guide__external" />
                  <span className="fc-visually-hidden"> (opens in a new tab)</span>
                </a>
              </p>
            ) : null}
          </details>
        );
      })}
      {takesUnder18s(meta) ? (
        <p className="fc-guide__muted">For members who are 16 or 17 it adds: “{meta.notices.field_visit_16_17}”</p>
      ) : null}
    </>
  );
}

/** `/guide`: how to read the ground, what fools people, how the ladder works and how to behave on a visit. */
export function GuidePanel({ meta }: { meta: Meta }) {
  useDocumentTitle("Guide");
  return (
    <PanelFrame panelKey={GUIDE_PATH} title="Guide" subtitle="How to read the ground">
      <div className="fc-guide">
        <p>
          LIDAR is a laser survey flown from an aircraft. It measures the height of the ground through gaps in trees and
          crops, so banks, ditches and mounds a few centimetres high can be drawn as shaded relief. Here's how to read
          it.
        </p>
        <nav className="fc-guide__contents" aria-label="On this page">
          <ul>
            {SECTIONS.map((section) => (
              <li key={section.id}>
                <button type="button" className="fc-guide__jump" onClick={() => jumpTo(section.id)}>
                  {section.title}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <Section id="guide-views" title="The views">
          <Views meta={meta} />
        </Section>
        <Section id="guide-lookalikes" title="Real or not?">
          <Lookalikes meta={meta} />
        </Section>
        <Section id="guide-ladder" title="How a finding climbs">
          <Ladder meta={meta} />
        </Section>
        <Section id="guide-ground" title="On the ground">
          <Ground meta={meta} />
        </Section>
      </div>
    </PanelFrame>
  );
}
