import { ArrowLeftRight } from "lucide-react";
import { memo, useId, useState } from "react";
import { type Meta, type Overlay, VIEW_GROUPS, type View, type ViewGroup, viewTitle } from "../api/meta.js";
import { Button } from "../ui/Button.js";
import { Slider } from "../ui/Slider.js";
import { Switch } from "../ui/Switch.js";
import { TabPanel, Tabs } from "../ui/Tabs.js";
import { Attribution, useAttributions } from "./attribution.js";
import { LIMITS } from "./permalink.js";
import { useMapStore } from "./store.js";
import { overlayTroubleKey } from "./trouble.js";

/** Headings for the view groups. The groups themselves come from /meta. */
const GROUP_LABELS: Record<ViewGroup, string> = {
  lidar: "LIDAR",
  imagery: "Aerial imagery",
  historic: "Historic maps",
  map: "Maps",
  geology: "Geology",
};

type Side = "main" | "compare";

function ViewOption({
  view,
  name,
  checked,
  tag,
  onSelect,
}: {
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
      <Switch label={overlay.title} checked={state.visible} onChange={(visible) => setVisible(overlay.id, visible)} />
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
          {overlay.type === "findings" && ruledOut ? (
            <Switch
              label={`Show ${ruledOut.label.toLowerCase()} findings`}
              hint={ruledOut.description}
              checked={showRuledOut}
              onChange={setShowRuledOut}
            />
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
    views: meta.layers.views.filter((view) => view.group === group),
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
          {views.map((view) => (
            <ViewOption
              key={view.id}
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
