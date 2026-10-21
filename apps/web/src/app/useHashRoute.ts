import { useSyncExternalStore } from "react";

/** Which view the hash selects: the TypingSurface demo, or the matrix page for one session. */
export type Route =
  | { readonly name: "demo" }
  | { readonly name: "matrix"; readonly sessionId: string };

/**
 * Parse a location hash into a Route. "#/matrix/<id>" -> matrix(<id>) (id URL-decoded); anything
 * else (including "", "#", "#/") -> demo. Pure; no window access.
 */
export function parseHash(hash: string): Route {
  const match = /^#\/matrix\/(.+)$/.exec(hash);
  const encoded = match?.[1];
  if (encoded !== undefined) {
    return { name: "matrix", sessionId: decodeURIComponent(encoded) };
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

/** The current Route, re-rendering on every hashchange (useSyncExternalStore over window.location.hash). */
export function useHashRoute(): Route {
  const hash = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return parseHash(hash);
}
