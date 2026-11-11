import { ArrowLeftRight } from "lucide-react";
import { memo, useId, useState } from "react";
import {
  type LayerTerms,
  type Meta,
  type Overlay,
  VIEW_GROUPS,
  type View,
  type ViewGroup,
  viewTitle,
} from "../api/meta.js";
import { AddToInvestigation } from "../features/investigations/AddToInvestigation.js";
import { currentView } from "../features/investigations/savedView.js";
import { TerrainTools } from "../features/layers/TerrainTools.js";
import { ViewPreview } from "../features/layers/ViewPreview.js";
import { LiveSourceControls, RecordFilterControls } from "../features/records/RecordLayerControls.js";
import { Button } from "../ui/Button.js";
import { Slider } from "../ui/Slider.js";
import { Switch } from "../ui/Switch.js";
import { TabPanel, Tabs } from "../ui/Tabs.js";
import { Attribution, parseAttribution, safeHref, useAttributions } from "./attribution.js";
import { LIMITS } from "./permalink.js";
import { useMapStore } from "./store.js";
import { overlayTroubleKey } from "./trouble.js";
import { useMapCover } from "./visibleArea.js";

/** Headings for the view groups. The groups themselves come from /meta. */
const GROUP_LABELS: Record<ViewGroup, string> = {
  lidar: "Terrain from LIDAR",
  imagery: "Aerial imagery",
  historic: "Historic maps",
  map: "Modern maps",
  geology: "Geology",
};

/** A line under a group's heading, where it has a term to explain. */
const GROUP_HINTS: Partial<Record<ViewGroup, string>> = {
  lidar:
    "LIDAR is a laser survey flown over the ground. These views are drawn from its heights to bring out banks, ditches and mounds.",
};

/**
 * A group's views in the catalogue's order, except that the default view
 * comes first: it is the one to try first.
 */
export function orderedViews(views: readonly View[]): View[] {
  return [...views].sort((a, b) => Number(b.default === true) - Number(a.default === true));
}

/**
 * What an overlay of each kind shows, where its name alone doesn't say.
 * The kinds are the schema's own. The catalogue sends no description of an
 * overlay, so the words are here, by kind, never by id.
 */
const OVERLAY_HINTS: Partial<Record<Overlay["type"], string>> = {
  coverage:
    "Shades each one-kilometre square by how many people have looked it over in “Scan a square”. It says nothing about where there is LIDAR.",
};

/**
 * A layer's credit and licence, shown while the layer is on. The licence is
 * named, as a link to its terms, unless the credit already links it by name.
 */
function LayerCredit({ attribution, terms }: { attribution: string | undefined; terms?: LayerTerms }) {
  const credit = attribution?.trim() ?? "";
  const licence = terms?.licence?.trim() ?? "";
  const named = licence !== "" && parseAttribution(credit).some((part) => part.href && part.text.trim() === licence);
  const showLicence = licence !== "" && !named;
  if (credit === "" && !showLicence) return null;
  const href = safeHref(terms?.licence_url);
  return (
    <p className="fc-layer-credit">
      {credit !== "" ? <Attribution html={credit} /> : null}
      {showLicence ? (
        <span className="fc-layer-credit__licence">
          {credit !== "" ? " · " : null}
          Licence:{" "}
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {licence}
            </a>
          ) : (
            licence
          )}
        </span>
      ) : null}
    </p>
  );
}

type Side = "main" | "compare";

function ViewOption({
  meta,
  view,
  name,
  checked,
  tag,
  onSelect,
}: {
  meta: Meta;
  view: View;
  name: string;
  checked: boolean;
  /** Says which side of a comparison is already showing this view. */
  tag: string | null;
  onSelect: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  return (
    // The card is one big label for the click target. The radio is named by
    // the title alone, so the description is read once, as its description.
    // The credit is outside the label, so its links are links and not part of the radio.
    <div className="fc-view-choice">
      <label className="fc-view-option">
        <input
          className="fc-view-option__input"
          type="radio"
          name={name}
          value={view.id}
          checked={checked}
          aria-labelledby={titleId}
          aria-describedby={view.description ? descriptionId : undefined}
          onChange={onSelect}
        />
        <span className="fc-view-option__mark" aria-hidden="true" />
        <ViewPreview meta={meta} view={view} />
        <span className="fc-view-option__text">
          <span className="fc-view-option__title" id={titleId}>
            {view.title}
            {tag ? <span className="fc-view-option__tag">{tag}</span> : null}
          </span>
          {view.description ? (
            <span className="fc-view-option__description" id={descriptionId}>
              {view.description}
            </span>
          ) : null}
        </span>
      </label>
      {checked ? <LayerCredit attribution={view.attribution} terms={view} /> : null}
    </div>
  );
}

function OverlayRow({ meta, overlay }: { meta: Meta; overlay: Overlay }) {
  const state = useMapStore((s) => s.overlays[overlay.id]);
  const key = overlayTroubleKey(overlay.id);
  const unavailable = useMapStore((s) => Boolean(s.failing[key]));
  const showRuledOut = useMapStore((s) => s.showRuledOut);
  const setVisible = useMapStore((s) => s.setOverlayVisible);
  const setOpacity = useMapStore((s) => s.setOverlayOpacity);
  const retrySource = useMapStore((s) => s.retrySource);
  const setShowRuledOut = useMapStore((s) => s.setShowRuledOut);
  if (!state) return null;

  const ruledOut = meta.vocab.states.find((s) => s.id === "ruled_out");
  return (
    <div className="fc-overlay-row" data-overlay={overlay.id}>
      <Switch
        label={overlay.title}
        hint={OVERLAY_HINTS[overlay.type]}
        checked={state.visible}
        onChange={(visible) => setVisible(overlay.id, visible)}
      />
      {state.visible && unavailable ? (
        <p className="fc-overlay-row__notice" role="status">
          This layer isn't loading right now.
          <Button size="sm" variant="ghost" onClick={() => retrySource(key)}>
            Try again
          </Button>
        </p>
      ) : null}
      {state.visible && !unavailable ? (
        <div className="fc-overlay-row__detail">
          <Slider
            label="Opacity"
            accessibleName={`${overlay.title} opacity`}
            value={Math.round(state.opacity * 100)}
            min={0}
            max={100}
            step={5}
            format={(value) => `${value}%`}
            onChange={(value) => setOpacity(overlay.id, value / 100)}
          />
          <LayerCredit
            attribution={overlay.attribution}
            terms={overlay.type === "openmaptiles" ? overlay : undefined}
          />
          {overlay.type === "findings" && ruledOut ? (
            <Switch
              label={`Show ${ruledOut.label.toLowerCase()} findings`}
              hint={ruledOut.description}
              checked={showRuledOut}
              onChange={setShowRuledOut}
            />
          ) : null}
          {overlay.type === "records" ? (
            <>
              <RecordFilterControls meta={meta} />
              <LiveSourceControls />
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The layer panel: views grouped as the catalogue groups them, the
 * comparison switch, 3D, overlays with their opacity, and the credits for
 * everything on screen.
 */
export const LayerPanel = memo(function LayerPanel({ meta }: { meta: Meta }) {
  const mainView = useMapStore((state) => state.mainView);
  const compareView = useMapStore((state) => state.compareView);
  const terrain = useMapStore((state) => state.terrain);
  const setMainView = useMapStore((state) => state.setMainView);
  const setCompareView = useMapStore((state) => state.setCompareView);
  const toggleCompare = useMapStore((state) => state.toggleCompare);
  const swapViews = useMapStore((state) => state.swapViews);
  const setTerrainEnabled = useMapStore((state) => state.setTerrainEnabled);
  const setTerrainExaggeration = useMapStore((state) => state.setTerrainExaggeration);
  const attributions = useAttributions(meta);

  const [chosenSide, setChosenSide] = useState<Side>("main");
  const id = useId();
  const comparing = compareView !== null;
  const side: Side = comparing ? chosenSide : "main";
  const selected = side === "main" ? mainView : compareView;
  const canCompare = meta.layers.views.length > 1;

  const groups = VIEW_GROUPS.map((group) => ({
    group,
    views: orderedViews(meta.layers.views.filter((view) => view.group === group)),
  })).filter((entry) => entry.views.length > 0);

  function select(viewId: string): void {
    if (side === "main") setMainView(viewId);
    else setCompareView(viewId);
  }

  function tagFor(viewId: string): string | null {
    if (!comparing) return null;
    if (viewId === mainView) return "Left";
    if (viewId === compareView) return "Right";
    return null;
  }

  const viewList = (
    <div className="fc-layers__views">
      {groups.map(({ group, views }) => (
        <fieldset key={group} className="fc-layers__group">
          <legend className="fc-layers__heading">{GROUP_LABELS[group]}</legend>
          {GROUP_HINTS[group] ? <p className="fc-field__hint">{GROUP_HINTS[group]}</p> : null}
          {views.map((view) => (
            <ViewOption
              key={view.id}
              meta={meta}
              view={view}
              name={`${id}-view`}
              checked={view.id === selected}
              tag={tagFor(view.id)}
              onSelect={() => select(view.id)}
            />
          ))}
        </fieldset>
      ))}
    </div>
  );

  return (
    <div className="fc-layers">
      <section className="fc-layers__section">
        <Switch
          label="Compare two layers"
          hint="Puts a second layer on the right. Drag the handle on the map to swipe between them."
          checked={comparing}
          disabled={!canCompare}
          onChange={() => toggleCompare()}
        />
        {comparing ? (
          <div className="fc-layers__sides">
            <Tabs
              label="Side of the map to change"
              idPrefix={id}
              value={side}
              onChange={(next) => setChosenSide(next as Side)}
              tabs={[
                { id: "main", label: "Left", detail: viewTitle(meta, mainView) },
                { id: "compare", label: "Right", detail: viewTitle(meta, compareView) },
              ]}
            />
            <Button
              size="sm"
              variant="ghost"
              icon={<ArrowLeftRight size={16} aria-hidden />}
              onClick={() => swapViews()}
            >
              Swap sides
            </Button>
          </div>
        ) : null}
      </section>

      <section className="fc-layers__section">
        {comparing ? (
          <TabPanel idPrefix={id} id={side}>
            {viewList}
          </TabPanel>
        ) : (
          viewList
        )}
      </section>

      <section className="fc-layers__section">
        <h3 className="fc-layers__heading">3D</h3>
        <Switch
          label="Tilt into 3D"
          hint="Drapes the map over the terrain. Hold Ctrl and drag, or use two fingers, to change the angle."
          checked={terrain.enabled}
          onChange={setTerrainEnabled}
        />
        {terrain.enabled ? (
          <div className="fc-overlay-row__detail">
            <Slider
              label="Height exaggeration"
              value={terrain.exaggeration}
              min={LIMITS.terrainExaggeration.min}
              max={LIMITS.terrainExaggeration.max}
              step={0.25}
              format={(value) => `×${value.toFixed(2).replace(/\.?0+$/, "")}`}
              onChange={setTerrainExaggeration}
            />
          </div>
        ) : null}
      </section>

      <TerrainTools />

      <section className="fc-layers__section">
        <h3 className="fc-layers__heading">Keep this view</h3>
        <p className="fc-field__hint">
          An investigation can keep where the map is, with its layers and light, to come back to this picture.
        </p>
        <div>
          <AddToInvestigation
            item={() => ({ kind: "view", view: currentView(meta, useMapCover.getState().cover) })}
            what="This view of the map"
          />
        </div>
      </section>

      <section className="fc-layers__section">
        <h3 className="fc-layers__heading">Overlays</h3>
        {meta.layers.overlays.map((overlay) => (
          <OverlayRow key={overlay.id} meta={meta} overlay={overlay} />
        ))}
      </section>

      <section className="fc-layers__section fc-layers__credits">
        <h3 className="fc-layers__heading">Credits for what's showing</h3>
        <ul>
          {attributions.map((line) => (
            <li key={line}>
              <Attribution html={line} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
});
