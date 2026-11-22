"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/** GET with loading/error state, optional polling (pauses when the tab is hidden), keeps stale data while refreshing. */
export function useApi(path, { interval = 0 } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(path));
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    if (alive.current) setLoading(true);
    try {
      const d = await api(path);
      if (alive.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    load();
    let timer;
    if (interval) {
      timer = setInterval(() => {
        if (document.visibilityState === "visible") load();
      }, interval);
    }
    return () => {
      alive.current = false;
      if (timer) clearInterval(timer);
    };
  }, [load, interval, path]);

  return { data, error, loading, reload: load };
}
