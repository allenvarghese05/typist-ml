import { useSyncExternalStore } from "react";

export type Route =
  | { readonly name: "demo" }
  | { readonly name: "matrix"; readonly sessionId: string }
  | { readonly name: "admin"; readonly participantId?: string }
  | { readonly name: "dashboard"; readonly participantId?: string; readonly tab?: string };

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
  return { name: "demo" };
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
  };
}

function getSnapshot(): string {
  return window.location.hash;
}

function getServerSnapshot(): string {
  return "";
}

export function useHashRoute(): Route {
  const hash = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return parseHash(hash);
}
