"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/**
 * GET with loading/error state, optional polling (pauses when the tab is hidden), keeps stale data while refreshing.
 * `interval` is milliseconds, or a function of the latest data returning milliseconds (0 stops polling), so a
 * finished workflow stops polling and one waiting on a human polls slowly.
 */
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

  const latest = useRef(null);
  useEffect(() => { latest.current = result.data; }, [result.data]);

  useEffect(() => {
    alive.current = true;
    run();
    let timer;
    const delay = () => (typeof interval === "function" ? interval(latest.current) : interval);
    const tick = () => {
      const ms = delay();
      if (!alive.current || !ms) { timer = setTimeout(tick, 1000); return; } // stopped for now; re-check cheaply
      timer = setTimeout(async () => {
        if (document.visibilityState === "visible") await run();
        if (alive.current) tick();
      }, ms);
    };
    if (interval) tick();
    return () => {
      alive.current = false;
      clearTimeout(timer);
    };
  }, [run, interval]);

  // Loading is derived: true until the first answer for the current path arrives (or while a manual reload runs).
  const loading = Boolean(path) && (result.path !== path || reloading);
  return { data: result.data, error: result.path === path ? result.error : null, loading, reload };
}
