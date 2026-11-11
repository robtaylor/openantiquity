import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { create } from "zustand";
import { apiUrl } from "../../api/client.js";
import { useSession } from "../account/session.js";
import { fetchLatestActivityId, type StreamEvent } from "./api.js";
import { Coalescer, REFETCH_DELAY_MS, refetchTarget, resync, targetKey, targetsFor } from "./liveRefetch.js";
import { type LiveStatus, LiveStream } from "./liveStream.js";

export const EVENTS_PATH = "/events/stream";

/** How the live stream is doing, for anything that wants to say so. Null before it starts. */
export const useLiveStatus = create<{ status: LiveStatus | null }>()(() => ({ status: null }));

const listeners = new Set<(event: StreamEvent) => void>();

/**
 * Hear every live event, for a feature with queries of its own to refetch.
 * An event is a hint, never data to show. Returns a function that stops.
 */
export function onLiveEvent(listener: (event: StreamEvent) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * The app's one live stream, mounted once by the shell. It holds no state
 * of its own on screen: each event invalidates the queries it could have
 * changed (`liveRefetch.ts`), and a resync refetches everything on screen.
 */
export function LiveEvents() {
  const client = useQueryClient();
  const { me } = useSession();
  const handle = useRef<string | null>(null);
  handle.current = me?.handle ?? null;

  useEffect(() => {
    const coalescer = new Coalescer();
    const stream = new LiveStream(apiUrl(EVENTS_PATH), {
      onEvent: (event) => {
        for (const target of targetsFor(event, handle.current)) {
          coalescer.schedule(targetKey(target), REFETCH_DELAY_MS[target.kind], () => refetchTarget(client, target));
        }
        for (const listener of [...listeners]) listener(event);
      },
      onResync: () => resync(client),
      latestId: () => fetchLatestActivityId(),
      onStatus: (status) => useLiveStatus.setState({ status }),
    });
    stream.start();
    return () => {
      stream.stop();
      coalescer.cancelAll();
    };
  }, [client]);

  return null;
}
