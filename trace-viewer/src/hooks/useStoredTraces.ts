import { useEffect, useState } from "react";
import { fetchStoredTraces } from "../lib/api";
import type { StoredTrace } from "../types/job";

const POLL_MS = 4000;

export function useStoredTraces(enabled: boolean) {
  const [traces, setTraces] = useState<StoredTrace[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const payload = await fetchStoredTraces();
        if (cancelled) return;
        setTraces(payload.traces);
        setError(null);
      } catch (exc) {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : "Could not list traces.");
      }
    };

    void tick();
    timer = window.setInterval(() => {
      void tick();
    }, POLL_MS);

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [enabled]);

  return { traces, error };
}
