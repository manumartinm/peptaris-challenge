import { useCallback, useEffect, useState } from "react";
import { parseRoute, serializeRoute, type AppRoute } from "../lib/routes";

export function useAppRoute() {
  const [route, setRoute] = useState<AppRoute>(() => parseRoute(window.location));

  useEffect(() => {
    const sync = () => setRoute(parseRoute(window.location));
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const go = useCallback((next: AppRoute, mode: "push" | "replace" = "push") => {
    const url = serializeRoute(next);
    const current = `${window.location.pathname}${window.location.search}`;
    if (url !== current) {
      if (mode === "push") window.history.pushState(null, "", url);
      else window.history.replaceState(null, "", url);
    }
    setRoute(next);
  }, []);

  return { route, go };
}
