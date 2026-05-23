/**
 * Polls /api/tasks/{id} until terminal status.
 */
import { useEffect, useRef, useState } from 'react';
import { getTask } from '../api/tasks';
import type { TaskInfo } from '../api/types';

export interface UseTaskPollingOptions {
  intervalMs?: number;
  onSuccess?: (task: TaskInfo) => void;
  onError?: (task: TaskInfo) => void;
}

export interface UseTaskPollingState {
  task: TaskInfo | null;
  loading: boolean;
}

export function useTaskPolling(
  taskId: string | null,
  options: UseTaskPollingOptions = {},
): UseTaskPollingState {
  const { intervalMs = 1000, onSuccess, onError } = options;
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const stoppedRef = useRef<boolean>(false);
  // Stash callbacks in refs so the polling effect doesn't re-run when caller
  // passes inline arrow functions.
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);
  onSuccessRef.current = onSuccess;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      setLoading(false);
      return;
    }

    stoppedRef.current = false;
    setLoading(true);

    let timer: number | null = null;
    const tick = async () => {
      if (stoppedRef.current) return;
      try {
        const t = await getTask(taskId);
        if (stoppedRef.current) return;
        setTask(t);
        if (t.status === 'success') {
          setLoading(false);
          stoppedRef.current = true;
          onSuccessRef.current?.(t);
          return;
        }
        if (t.status === 'failed') {
          setLoading(false);
          stoppedRef.current = true;
          onErrorRef.current?.(t);
          return;
        }
        timer = window.setTimeout(tick, intervalMs);
      } catch (err) {
        if (stoppedRef.current) return;
        setLoading(false);
        stoppedRef.current = true;
      }
    };

    tick();

    return () => {
      stoppedRef.current = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [taskId, intervalMs]);

  return { task, loading };
}
