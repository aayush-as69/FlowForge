"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/** GET with loading/error state, optional polling (pauses when the tab is hidden), keeps stale data while refreshing. */
export function useApi(path, { interval = 0 } = {}) {
  const [result, setResult] = useState({ path: null, data: null, error: null });
  const [reloading, setReloading] = useState(false);
  const alive = useRef(true);

  const run = useCallback(async () => {
    if (!path) return;
    try {
      const data = await api(path);
      if (alive.current) setResult({ path, data, error: null });
    } catch (error) {
      if (alive.current) setResult((r) => ({ path, data: r.data, error }));
    }
  }, [path]);

  const reload = useCallback(async () => {
    setReloading(true);
    try {
      await run();
    } finally {
      if (alive.current) setReloading(false);
    }
  }, [run]);

  useEffect(() => {
    alive.current = true;
    run();
    let timer;
    if (interval) {
      timer = setInterval(() => {
        if (document.visibilityState === "visible") run();
      }, interval);
    }
    return () => {
      alive.current = false;
      if (timer) clearInterval(timer);
    };
  }, [run, interval]);

  // Loading is derived: true until the first answer for the current path arrives (or while a manual reload runs).
  const loading = Boolean(path) && (result.path !== path || reloading);
  return { data: result.data, error: result.path === path ? result.error : null, loading, reload };
}
