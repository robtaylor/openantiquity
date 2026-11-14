import { QueryClientContext } from "@tanstack/react-query";
import { Bug, Copy, ExternalLink, Mail } from "lucide-react";
import { useContext, useId, useState } from "react";
import { createPortal } from "react-dom";
import { useInRouterContext, useLocation } from "react-router";
import { keptFailures } from "../../api/failures.js";
import type { Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { Button, type ButtonSize, type ButtonVariant } from "../../ui/Button.js";
import { copyText } from "../../ui/clipboard.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { accountKeys, type Me } from "../account/api.js";
import { isPhoneNow } from "../shell/useIsPhone.js";
import { usePlaceKeptBack } from "./keptBack.js";
import {
  browserName,
  emailUrl,
  githubIssueUrl,
  type MapFacts,
  type MapPosition,
  pagePattern,
  type ReportFacts,
  reportText,
  reportTitle,
} from "./report.js";
import "./problem.css";

/** The longest description the box takes. */
const DESCRIPTION_MAX = 2000;

function mapFacts(): MapFacts | null {
  const state = useMapStore.getState();
  if (state.meta === null) return null;
  return {
    mainView: state.mainView,
    compareView: state.compareView,
    overlays: Object.entries(state.overlays)
      .filter(([, overlay]) => overlay.visible)
      .map(([id]) => id),
    threeD: state.terrain.enabled,
  };
}

/**
 * What a report says about the page, read once when the form opens. The
 * session and `/meta` are read from wherever they are kept, so the button
 * works in any error state, the one shown before the map starts included.
 */
function gatherFacts(pathname: string, meta: Meta | null, me: Me | null | undefined): ReportFacts {
  return {
    version: meta?.app.version ?? null,
    commit: meta?.app.commit ?? null,
    page: pagePattern(pathname),
    layout: isPhoneNow() ? "phone" : "desktop",
    browser: browserName(navigator.userAgent),
    window: { width: window.innerWidth, height: window.innerHeight },
    map: mapFacts(),
    signedIn: me === undefined ? null : me !== null,
    failures: keptFailures(),
  };
}

function cameraNow(): MapPosition | null {
  const { meta, camera } = useMapStore.getState();
  return meta === null ? null : { lng: camera.lng, lat: camera.lat, zoom: camera.zoom };
}

type Copied = "copied" | "refused" | null;

interface ReportFormProps {
  pathname: string;
  onClose: () => void;
}

/** The form: what the person writes, what will be sent, and the ways to send it. */
export function ReportProblemDialog({ pathname, onClose }: ReportFormProps) {
  const client = useContext(QueryClientContext);
  const meta = useMapStore((state) => state.meta);
  const [facts] = useState(() => gatherFacts(pathname, meta, client?.getQueryData<Me | null>(accountKeys.me)));
  const [camera] = useState(cameraNow);
  const keptBack = usePlaceKeptBack(pathname);
  const [description, setDescription] = useState("");
  const [addPosition, setAddPosition] = useState(false);
  const [copied, setCopied] = useState<Copied>(null);
  const positionHint = useId();

  const position = addPosition && !keptBack ? camera : null;
  const choices = { description, position };
  const text = reportText(facts, choices);
  const title = reportTitle(facts, choices);
  const issue = githubIssueUrl(title, text);
  // The server trims it, and sends null for none.
  const reportEmail = meta?.app.report_email;

  const copy = async (): Promise<void> => setCopied((await copyText(text)) ? "copied" : "refused");

  return (
    <Dialog
      open
      onClose={onClose}
      title="Report a problem"
      className="fc-problem"
      actions={
        <>
          <Button icon={<Copy size={16} aria-hidden />} onClick={() => void copy()}>
            Copy the details
          </Button>
          {reportEmail ? (
            <a className="fc-button fc-button--secondary fc-button--md" href={emailUrl(reportEmail, title, text)}>
              <Mail size={16} aria-hidden />
              Email it
            </a>
          ) : null}
          <a
            className="fc-button fc-button--primary fc-button--md"
            href={issue.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => {
              // The issue will hold only the start, so the whole text goes on the clipboard to paste over it.
              if (issue.cut) void copy();
            }}
          >
            <ExternalLink size={16} aria-hidden />
            Open a GitHub issue
          </a>
        </>
      }
    >
      <div className="fc-problem__body">
        <p>
          Say what you were doing. The box below shows everything that goes with it, and nothing is sent until you
          choose how to send it. A GitHub issue can be read by anyone.
        </p>
        <Field
          label="What were you doing, and what went wrong?"
          hint="This is the only part you write. Please don't say where a protected finding is."
        >
          {(control) => (
            <textarea
              className="fc-input fc-problem__description"
              rows={4}
              maxLength={DESCRIPTION_MAX}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              {...control}
            />
          )}
        </Field>
        <div className="fc-field">
          <label className="fc-problem__check">
            <input
              type="checkbox"
              checked={position !== null}
              disabled={keptBack || camera === null}
              aria-describedby={positionHint}
              onChange={(event) => setAddPosition(event.target.checked)}
            />
            Add where the map is looking
          </label>
          <p className="fc-field__hint" id={positionHint}>
            {keptBack
              ? "Not on this page: it shows a place that is kept back from you."
              : camera === null
                ? "The map hasn't started, so there is nowhere to add."
                : "Its centre and zoom. They often help with a fault in the terrain."}
          </p>
        </div>
        <Field label="What will be sent">
          {(control) => (
            <textarea className="fc-input fc-problem__text fc-mono" readOnly rows={12} value={text} {...control} />
          )}
        </Field>
        {issue.cut ? (
          <p className="fc-problem__note" role="note">
            This report is too long for GitHub to take whole, so the issue will hold the start of it. Opening the issue
            puts the full text on your clipboard as well: paste it over what the issue holds.
          </p>
        ) : null}
        <p className="fc-problem__status" role="status">
          {copied === "copied"
            ? "Copied. Paste it wherever you're sending the report."
            : copied === "refused"
              ? "This browser wouldn't copy it. Select the text in the box above and copy it yourself."
              : null}
        </p>
      </div>
    </Dialog>
  );
}

function RoutedReportProblemDialog({ onClose }: { onClose: () => void }) {
  const { pathname } = useLocation();
  return <ReportProblemDialog pathname={pathname} onClose={onClose} />;
}

export interface ReportProblemButtonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/**
 * "Report a problem", which opens the form. It reads the page from the
 * router when there is one and from the address bar otherwise, so it works
 * in any error state.
 */
export function ReportProblemButton({ variant = "secondary", size = "md" }: ReportProblemButtonProps) {
  const [open, setOpen] = useState(false);
  const inRouter = useInRouterContext();
  const close = () => setOpen(false);
  return (
    <>
      <Button variant={variant} size={size} icon={<Bug size={16} aria-hidden />} onClick={() => setOpen(true)}>
        Report a problem
      </Button>
      {open
        ? createPortal(
            inRouter ? (
              <RoutedReportProblemDialog onClose={close} />
            ) : (
              <ReportProblemDialog pathname={window.location.pathname} onClose={close} />
            ),
            document.body,
          )
        : null}
    </>
  );
}
