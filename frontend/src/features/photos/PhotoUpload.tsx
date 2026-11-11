import { ImageUp, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "../../ui/Button.js";
import { Field } from "../../ui/Field.js";
import { PHOTO_TYPES, photoProblem } from "../finding/evidenceForms.js";
import { type Media, uploadPhoto } from "./api.js";
import { type UploadProblem, uploadProblem } from "./uploadWords.js";
import { useWaitingPhotos, WHO_SEES_APPROVED, WHO_SEES_WAITING } from "./waiting.js";
import "./photos.css";

/** Where a photo field stands, as the form that holds it needs to know. */
export type PhotoState =
  | { status: "empty" }
  | { status: "uploading"; name: string }
  | { status: "failed"; name: string }
  | { status: "done"; name: string; media: Media };

export const NO_PHOTO: PhotoState = { status: "empty" };

export interface PhotoUploadProps {
  label: string;
  hint?: string;
  required?: boolean;
  /** Where the photo stands, kept by the form so a form opened again shows it as it was. */
  value: PhotoState;
  onChange: (state: PhotoState) => void;
  /** A problem the form found, such as no photo chosen yet. */
  error?: string;
}

type Attempt = { file: File; progress: number | null } | { file: File; problem: UploadProblem };

/**
 * Choosing a photo and sending it at once, with how far it has got, a way to
 * stop it, and a retry when the network or the server let it down. A
 * refusal says what was wrong with the picture. Once it is up, it says that
 * it waits for approval and who can see it meanwhile.
 */
export function PhotoUpload({ label, hint, required, value, onChange, error }: PhotoUploadProps) {
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const controller = useRef<AbortController | null>(null);
  const latest = useRef(onChange);
  latest.current = onChange;
  const addWaiting = useWaitingPhotos((state) => state.add);

  // Leaving the form stops an upload that is still going.
  useEffect(() => () => controller.current?.abort(), []);

  async function send(file: File): Promise<void> {
    controller.current?.abort();
    const ours = new AbortController();
    controller.current = ours;
    setAttempt({ file, progress: null });
    latest.current({ status: "uploading", name: file.name });
    try {
      const media = await uploadPhoto(file, {
        signal: ours.signal,
        onProgress: (progress) => {
          if (controller.current === ours) setAttempt({ file, progress });
        },
      });
      if (controller.current !== ours) return;
      if (!media.approved) addWaiting(media.id);
      setAttempt(null);
      latest.current({ status: "done", name: file.name, media });
    } catch (cause) {
      if (controller.current !== ours) return;
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setAttempt({ file, problem: uploadProblem(cause) });
      latest.current({ status: "failed", name: file.name });
    }
  }

  function choose(file: File | null): void {
    if (file === null) return;
    // Said at once, rather than after the server refuses it.
    const problem = photoProblem(file);
    if (problem) {
      controller.current?.abort();
      controller.current = null;
      setAttempt({ file, problem: { message: problem, retry: false } });
      onChange({ status: "failed", name: file.name });
      return;
    }
    void send(file);
  }

  function stop(): void {
    controller.current?.abort();
    controller.current = null;
    setAttempt(null);
    onChange(NO_PHOTO);
  }

  const problem = attempt && "problem" in attempt ? attempt.problem : null;
  const progress = attempt && "progress" in attempt ? attempt.progress : null;
  const uploading = attempt !== null && problem === null;

  return (
    <div className="fc-photo-upload">
      <Field label={label} hint={hint} error={problem ? undefined : error}>
        {(control) => (
          <input
            {...control}
            className="fc-input fc-input--file"
            type="file"
            accept={PHOTO_TYPES.join(",")}
            required={required}
            onChange={(event) => {
              choose(event.target.files?.[0] ?? null);
              // The same file can be chosen again after a refusal.
              event.target.value = "";
            }}
          />
        )}
      </Field>

      <div className="fc-photo-upload__status" role="status">
        {uploading ? (
          <div className="fc-photo-upload__progress">
            <span>
              Sending <bdi>{attempt?.file.name}</bdi>
              {progress === null ? "…" : `, ${Math.round(progress * 100)}%`}
            </span>
            <div
              className="fc-photo-upload__bar"
              role="progressbar"
              aria-label="Sending the photo"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress === null ? undefined : Math.round(progress * 100)}
              data-indeterminate={progress === null || undefined}
            >
              <span style={progress === null ? undefined : { width: `${Math.round(progress * 100)}%` }} />
            </div>
            <Button size="sm" variant="ghost" icon={<X size={14} aria-hidden />} onClick={stop}>
              Stop
            </Button>
          </div>
        ) : null}
        {!uploading && value.status === "done" ? (
          <div className="fc-photo-upload__done">
            <img className="fc-photo-upload__thumb" src={value.media.url} alt="" />
            <div>
              <p>
                <ImageUp size={15} aria-hidden /> <bdi>{value.name}</bdi> is uploaded.
              </p>
              <p className="fc-photo-upload__who">
                {value.media.approved ? WHO_SEES_APPROVED : `It's waiting for approval. ${WHO_SEES_WAITING}`}
              </p>
            </div>
          </div>
        ) : null}
      </div>
      {problem ? (
        <div className="fc-photo-upload__problem" role="alert">
          <p>{problem.message}</p>
          {problem.retry && attempt ? (
            <Button size="sm" icon={<RotateCcw size={14} aria-hidden />} onClick={() => void send(attempt.file)}>
              Try again
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
