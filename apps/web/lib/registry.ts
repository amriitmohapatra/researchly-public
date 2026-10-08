/**
 * The engine's registry (`GET /v1/rules`: rule names, scopes and, since S4,
 * the article-type choices and the reporting checklists), fetched once per engine URL and shared by every
 * hook that wants it. No text is sent. An engine without one (the local
 * server, an older build) is not asked again this session; the callers'
 * built-in lists stand in.
 */
import { useEffect, useSyncExternalStore } from "react";
import type { ChecklistChoiceInfo, ProfileChoice } from "@researchly/contract";
import { FALLBACK_CHECKLISTS } from "./checklists";
import { listRegistry, type Registry } from "./engine";
import { FALLBACK_PROFILES } from "./profiles";

const cache = new Map<string, Registry>();
const unavailable = new Set<string>();
const pending = new Map<string, AbortController>();
const listeners = new Set<() => void>();
let version = 0;

function notify() {
  version++;
  for (const l of listeners) l();
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

function snapshot(): number {
  return version;
}

function fetchOnce(engineUrl: string) {
  if (cache.has(engineUrl) || unavailable.has(engineUrl) || pending.has(engineUrl)) return;
  const ctrl = new AbortController();
  pending.set(engineUrl, ctrl);
  void listRegistry(engineUrl, ctrl.signal)
    .then((r) => {
      if (ctrl.signal.aborted) return;
      if (r.ok) cache.set(engineUrl, r.data);
      else unavailable.add(engineUrl);
      notify();
    })
    .catch(() => {
      /* aborted or failed before a response: the built-in lists apply */
    })
    .finally(() => {
      if (pending.get(engineUrl) === ctrl) pending.delete(engineUrl);
    });
}

/**
 * The registry for `engineUrl` once it has arrived; null until then, or when
 * the engine has none. Fetched only while `wanted`.
 */
export function useRegistry(engineUrl: string | null, wanted: boolean): Registry | null {
  useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => {
    if (wanted && engineUrl) fetchOnce(engineUrl);
  }, [engineUrl, wanted]);
  return engineUrl ? (cache.get(engineUrl) ?? null) : null;
}

/** The article types a caller can check as, with the engine's labels when it has them, else the contract's list. */
export function useProfileChoices(engineUrl: string | null): readonly ProfileChoice[] {
  const registry = useRegistry(engineUrl, true);
  return registry && registry.profiles.length > 0 ? registry.profiles : FALLBACK_PROFILES;
}

/** The reporting checklists a caller can check against, with the engine's labels when it has them, else the built-in list. */
export function useChecklistChoices(engineUrl: string | null): readonly ChecklistChoiceInfo[] {
  const registry = useRegistry(engineUrl, true);
  return registryChecklists(registry);
}

/** The checklists from a registry, or the built-in list when it has none (pure; unit-tested). */
export function registryChecklists(registry: Registry | null): readonly ChecklistChoiceInfo[] {
  return registry && registry.checklists.length > 0 ? registry.checklists : FALLBACK_CHECKLISTS;
}

/** Tests only: forget every engine. */
export function resetRegistryCache(): void {
  for (const c of pending.values()) c.abort();
  pending.clear();
  cache.clear();
  unavailable.clear();
}
