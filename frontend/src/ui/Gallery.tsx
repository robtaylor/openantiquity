import { Layers, MapPinPlus, Search, Telescope } from "lucide-react";
import { useState } from "react";
import type { Meta } from "../api/meta.js";
import { isSensitivity, type Sensitivity } from "../features/findings/types.js";
import { Avatar } from "./Avatar.js";
import { Button } from "./Button.js";
import { ChipGroup } from "./Chip.js";
import { Dialog } from "./Dialog.js";
import { EmptyState } from "./EmptyState.js";
import { Field } from "./Field.js";
import { FeatureIcon } from "./featureIcons.js";
import { IconButton } from "./IconButton.js";
import { Meter } from "./Meter.js";
import { Skeleton } from "./Skeleton.js";
import { Slider } from "./Slider.js";
import { Switch } from "./Switch.js";
import { TabPanel, Tabs } from "./Tabs.js";
import { TierBadge } from "./TierBadge.js";
import { toast } from "./toastStore.js";
import "./Gallery.css";

/**
 * Every shared component on one page, fed from the live vocabulary. It is a
 * development aid for checking the kit by eye, and is only routed in dev
 * builds (at `/_ui`).
 */
export function Gallery({ meta }: { meta: Meta }) {
  const [featureClass, setFeatureClass] = useState<string | null>("round_barrow");
  const [periods, setPeriods] = useState<string[]>(["bronze_age"]);
  const [tab, setTab] = useState("evidence");
  const [opacity, setOpacity] = useState(80);
  const [sensitivity, setSensitivity] = useState<Sensitivity>("protected");
  const [following, setFollowing] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const tiers = meta.vocab.tiers;
  const known = meta.vocab.states.find((state) => state.id === "known");
  const disputed = meta.vocab.states.find((state) => state.id === "disputed");
  const ruledOut = meta.vocab.states.find((state) => state.id === "ruled_out");

  return (
    <div className="fc-gallery">
      <section>
        <h3>Buttons</h3>
        <div className="fc-gallery__row">
          <Button variant="primary">Save finding</Button>
          <Button variant="secondary">Add evidence</Button>
          <Button variant="ghost">Cancel</Button>
          <Button variant="danger">Withdraw</Button>
        </div>
        <div className="fc-gallery__row">
          <Button variant="primary" size="lg" icon={<MapPinPlus size={20} aria-hidden />}>
            Mark a finding
          </Button>
          <Button size="sm">Small</Button>
          <Button disabled>Disabled</Button>
        </div>
        <div className="fc-gallery__row">
          <IconButton label="Layers">
            <Layers size={20} aria-hidden />
          </IconButton>
          <IconButton label="Layers, floating" floating>
            <Layers size={20} aria-hidden />
          </IconButton>
          <IconButton label="Layers, on" floating pressed>
            <Layers size={20} aria-hidden />
          </IconButton>
        </div>
      </section>

      <section>
        <h3>Confidence</h3>
        <div className="fc-gallery__stack">
          {tiers.map((tier, index) => {
            const next = tiers[index + 1];
            const score = next ? tier.base_score + (next.base_score - tier.base_score) * 0.5 : tier.base_score;
            return (
              <div key={tier.id} className="fc-gallery__meter">
                <TierBadge tier={tier} />
                <Meter value={score} tiers={tiers} tierId={tier.id} showScale={index === 0} />
              </div>
            );
          })}
          {tiers[1] && known ? (
            <div className="fc-gallery__meter">
              <TierBadge tier={tiers[1]} state={known} />
              <Meter value={tiers[1].base_score} tiers={tiers} tierId={tiers[1].id} />
            </div>
          ) : null}
          {tiers[0] && ruledOut ? (
            <div className="fc-gallery__meter">
              <TierBadge tier={tiers[0]} state={ruledOut} />
              <Meter value={0} tiers={tiers} tierId={tiers[0].id} ruledOut />
            </div>
          ) : null}
        </div>
        <div className="fc-gallery__row">
          {tiers[2] && disputed ? <TierBadge tier={tiers[2]} state={disputed} size="sm" /> : null}
          {tiers.slice(0, 3).map((tier) => (
            <TierBadge key={tier.id} tier={tier} size="sm" />
          ))}
        </div>
      </section>

      <section>
        <h3>Feature classes</h3>
        <ul className="fc-gallery__features">
          {meta.vocab.feature_classes.map((item) => (
            <li key={item.id} title={item.hint}>
              <FeatureIcon classId={item.id} size={32} />
              <span>{item.label}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Chips</h3>
        <ChipGroup
          label="What do you think it is?"
          value={featureClass}
          onChange={setFeatureClass}
          options={meta.vocab.feature_classes.slice(0, 6).map((item) => ({
            id: item.id,
            label: item.label,
            icon: <FeatureIcon classId={item.id} size={18} />,
          }))}
        />
        <ChipGroup
          multiple
          label="Period"
          value={periods}
          onChange={setPeriods}
          options={meta.vocab.periods.slice(1, 6).map((item) => ({ id: item.id, label: item.label }))}
        />
      </section>

      <section>
        <h3>Tabs, fields and sliders</h3>
        <Tabs
          label="Finding sections"
          idPrefix="gallery"
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "evidence", label: "Evidence" },
            { id: "discussion", label: "Discussion" },
            { id: "timeline", label: "Timeline" },
          ]}
        />
        <TabPanel idPrefix="gallery" id={tab}>
          <p className="fc-muted">The {tab} tab is showing.</p>
        </TabPanel>
        <Field label="Title" hint="A few words that would help someone find it again.">
          {(control) => <input className="fc-input" defaultValue="Ring ditch south of the henge" {...control} />}
        </Field>
        <Field label="Link" error="That doesn't look like a web address.">
          {(control) => <input className="fc-input" defaultValue="youtube" {...control} />}
        </Field>
        <Slider
          label="Opacity"
          value={opacity}
          min={0}
          max={100}
          step={5}
          format={(v) => `${v}%`}
          onChange={setOpacity}
        />
        <ChipGroup
          label="Who sees the exact position?"
          value={sensitivity}
          onChange={(value) => {
            if (isSensitivity(value)) setSensitivity(value);
          }}
          options={[
            { id: "open", label: "Everyone" },
            { id: "protected", label: "Members" },
          ]}
        />
        <Switch
          label="Follow this finding"
          hint="Tells you when someone adds evidence or a second look."
          checked={following}
          onChange={setFollowing}
        />
      </section>

      <section>
        <h3>People</h3>
        <div className="fc-gallery__row">
          <Avatar name="QuietBarrow42" />
          <Avatar name="Mary Leakey" size={40} />
          <Avatar name="os_surveyor" size={24} />
          <Avatar name="Hill Fort Harry" />
        </div>
      </section>

      <section>
        <h3>Feedback</h3>
        <div className="fc-gallery__row">
          <Button size="sm" onClick={() => toast("Saved.", { kind: "success" })}>
            Success toast
          </Button>
          <Button
            size="sm"
            onClick={() =>
              toast("Couldn't save your answer.", { kind: "error", action: { label: "Retry", onClick: () => {} } })
            }
          >
            Error toast
          </Button>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            Open dialog
          </Button>
        </div>
        <EmptyState
          icon={<Telescope size={22} />}
          title="Nothing waiting for a second look"
          action={<Button icon={<Search size={18} aria-hidden />}>Scan a square instead</Button>}
        >
          <p>Every finding near here has had enough answers for now.</p>
        </EmptyState>
        <Skeleton lines={3} />
      </section>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title="Withdraw this finding?"
        actions={
          <>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              Keep it
            </Button>
            <Button variant="danger" onClick={() => setDialogOpen(false)}>
              Withdraw
            </Button>
          </>
        }
      >
        <p>It stays visible, marked as withdrawn, so nobody marks the same thing again.</p>
      </Dialog>
    </div>
  );
}
