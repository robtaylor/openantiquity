/**
 * What to tell someone whose photo didn't upload, by the server's code, and
 * whether trying the same file again could work. The codes are the ones
 * `POST /media` refuses with (docs/ARCHITECTURE.md, "Photos").
 */

import { ApiError } from "../../api/client.js";

export interface UploadProblem {
  message: string;
  /** Sending the same file again might work: the network or the server, not the picture. */
  retry: boolean;
}

const REFUSALS: Record<string, UploadProblem> = {
  image_too_large: { message: "That photo is over 15 MB. Choose a smaller copy.", retry: false },
  image_too_many_pixels: {
    message: "That picture is very large for the size of its file. Choose a smaller copy.",
    retry: false,
  },
  not_an_image: { message: "That file isn't a picture we can read. Choose a JPEG, PNG or WebP photo.", retry: false },
  unsupported_image: {
    message: "We can't take that kind of picture. Choose a still JPEG, PNG or WebP photo.",
    retry: false,
  },
  media_blocked: { message: "That photo was refused before, so it can't be added again.", retry: false },
  uploads_busy: { message: "The server is busy with other photos. Try again in a minute.", retry: true },
  rate_limited: { message: "You've sent a lot of photos in the last hour. Try again later.", retry: true },
};

export function uploadProblem(error: unknown): UploadProblem {
  if (error instanceof ApiError) {
    const known = REFUSALS[error.code];
    if (known) return known;
    if (error.status === 0) return { message: "The connection dropped before the photo was sent.", retry: true };
    if (error.status >= 500) return { message: "The server couldn't take the photo just now.", retry: true };
    return { message: error.message, retry: false };
  }
  return { message: "The photo couldn't be sent.", retry: true };
}
