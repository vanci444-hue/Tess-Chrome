import { useCallback, useEffect, useRef, useState } from "react";
import { tess } from "../services/tess";
import type { SessionDetail, RunStatus } from "../types/api";
export function useSession(id: string) {
  const [data, setData] = useState<SessionDetail | null>(null),
    [error, setError] = useState(""),
    [run, setRun] = useState<RunStatus | null>(null);
  const alive = useRef(true);
  // A route instance owns exactly one session. Late A results cannot mutate B's view.
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, [id]);
  const refresh = useCallback(async () => {
    const next = await tess.session(id);
    if (alive.current && next.id === id) setData(next);
    return next;
  }, [id]);
  useEffect(() => {
    let current = true;
    tess
      .session(id)
      .then((value) => {
        if (current) setData(value);
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [id]);
  const activeId = data?.active_run?.run_id;
  useEffect(() => {
    if (!activeId) return;
    let current = true,
      timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await tess.runStatus(id, activeId);
        if (!current) return;
        setRun(result);
        if (["queued", "running"].includes(result.status))
          timer = setTimeout(poll, 1000);
        else await refresh();
      } catch (e) {
        if (current) setError((e as Error).message);
      }
    };
    void poll();
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [activeId, id, refresh]);
  const track = useCallback(
    async (runId: string) => {
      const status = await tess.runStatus(id, runId);
      if (alive.current && status.session_id === id) setRun(status);
      await refresh();
    },
    [id, refresh],
  );
  return { data, error, setError, run, refresh, track };
}
