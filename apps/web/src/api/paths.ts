/** Base path of the Typist-ML HTTP API (design doc section 14). In dev, Vite proxies it to 127.0.0.1:8000. */
export const API_BASE = "/api/v1";

/**
 * Returns the same-origin URL path for an API endpoint, for example
 * `apiPath("/health")` → `"/api/v1/health"`.
 *
 * @param endpoint Path below the API base. Must start with "/".
 * @throws RangeError if `endpoint` does not start with "/".
 */
export function apiPath(endpoint: string): string {
  if (!endpoint.startsWith("/")) {
    throw new RangeError(`API endpoint must start with "/": ${JSON.stringify(endpoint)}`);
  }
  return `${API_BASE}${endpoint}`;
}
