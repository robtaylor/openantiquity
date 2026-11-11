import { ImageOff } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useWaitingPhotos, WHO_SEES_WAITING } from "./waiting.js";
import "./photos.css";

export interface PhotoProps {
  /** The address the API gives for the photo, such as `MediaOut.url`. */
  src: string;
  alt: string;
  /** The photo's id, so the uploader's own waiting photo can say so. */
  mediaId?: number;
  /** Said in place of the photo when the server won't send it to this viewer. */
  unavailable?: string;
  /** Controls for the photo itself, such as reporting it, shown only while there is a photo to see. */
  actions?: ReactNode;
}

/** Said where a photo would be, when there is none this viewer may see. */
export const NOT_YET_SHOWN = "This photo shows here once it has been approved.";

/** The place of a photo this viewer can't be shown, and why. */
export function PhotoPlaceholder({ children = NOT_YET_SHOWN }: { children?: ReactNode }) {
  return (
    <div className="fc-photo fc-photo--missing">
      <ImageOff size={20} aria-hidden />
      <p>{children}</p>
    </div>
  );
}

/**
 * A photo, shown only from the address the API gives. The server answers
 * 404 to anyone who may not see it, such as everyone but the uploader and
 * the approvers before it is approved, and then a placeholder says why
 * there is no picture. The uploader's own photo says while it waits.
 */
export function Photo({ src, alt, mediaId, unavailable = NOT_YET_SHOWN, actions }: PhotoProps) {
  const [failed, setFailed] = useState<string | null>(null);
  const waiting = useWaitingPhotos((state) => mediaId !== undefined && state.ids.has(mediaId));
  if (failed === src) return <PhotoPlaceholder>{unavailable}</PhotoPlaceholder>;
  return (
    <figure className="fc-photo">
      <img src={src} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(src)} />
      {waiting ? <figcaption>Waiting for approval. {WHO_SEES_WAITING}</figcaption> : null}
      {actions ? <div className="fc-photo__actions">{actions}</div> : null}
    </figure>
  );
}
