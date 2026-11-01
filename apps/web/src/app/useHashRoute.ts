import { useEffect, useSyncExternalStore } from "react";

export type Route =
  | { readonly name: "demo" }
  | { readonly name: "matrix"; readonly sessionId: string }
  | { readonly name: "admin"; readonly participantId?: string }
  | { readonly name: "dashboard"; readonly participantId?: string; readonly tab?: string }
  | { readonly name: "debrief"; readonly participantId?: string };

export function parseHash(hash: string): Route {
  const matrixMatch = /^#\/matrix\/(.+)$/.exec(hash);
  const matrixEncoded = matrixMatch?.[1];
  if (matrixEncoded !== undefined) {
    return { name: "matrix", sessionId: decodeURIComponent(matrixEncoded) };
  }
  const adminMatch = /^#\/admin(?:\?(.*))?$/.exec(hash);
  if (adminMatch) {
    const search = adminMatch[1];
    const params = new URLSearchParams(search ?? "");
    const participantId = params.get("participant") ?? undefined;
    return { name: "admin", participantId };
  }
  const dashboardMatch = /^#\/dashboard(?:\?(.*))?$/.exec(hash);
  if (dashboardMatch) {
    const search = dashboardMatch[1];
    const params = new URLSearchParams(search ?? "");
    const participantId = params.get("participant") ?? undefined;
    const tab = params.get("tab") ?? undefined;
    return { name: "dashboard", participantId, tab };
  }
  const debriefMatch = /^#\/(?:results|debrief)(?:\/([^?]+?))?\/?(?:\?(.*))?$/.exec(hash);
  if (debriefMatch) {
    const pathPid = debriefMatch[1];
    const search = debriefMatch[2];
    const params = new URLSearchParams(search ?? "");
    const participantId = pathPid
      ? decodeURIComponent(pathPid)
      : (params.get("participant") ?? undefined);
    return { name: "debrief", participantId };
  }
  return { name: "demo" };
}

/**
 * If a user opens a known SPA path directly without a `#` prefix (e.g. `/dashboard`, `/admin`,
 * `/results`, `/debrief`, `/matrix/<id>`), convert it into the canonical hash route.
 */
export function hashFromLocation(pathname: string, search: string, hash: string): string {
  if (hash !== "" && hash !== "#") {
    return hash;
  }
  if (/^\/(?:admin|dashboard|results|debrief|matrix\/)/.test(pathname)) {
    return `#${pathname}${search}`;
  }
  return hash;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
  };
}

function getSnapshot(): string {
  return hashFromLocation(window.location.pathname, window.location.search, window.location.hash);
}

function getServerSnapshot(): string {
  return "";
}

export function useHashRoute(): Route {
  const effectiveHash = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    if (
      (window.location.hash === "" || window.location.hash === "#") &&
      effectiveHash.startsWith("#/")
    ) {
      window.history.replaceState(null, "", `/${effectiveHash}`);
    }
  }, [effectiveHash]);

  return parseHash(effectiveHash);
}
