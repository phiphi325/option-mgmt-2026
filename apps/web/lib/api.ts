/**
 * Thin fetch wrapper for the FastAPI backend.
 *
 * Reads the API base URL from `NEXT_PUBLIC_API_BASE` (set in
 * docker-compose.yml). Falls back to localhost:8000/api/v1 for `pnpm dev`.
 *
 * Errors from the API conform to RFC 7807 (per plan v1.2 §7); we extract
 * `title` and `detail` and re-throw as ApiError for clean handling upstream.
 *
 * M1.x will layer:
 *   - JWT auth header from a session/cookie
 *   - typed responses via `option-mgmt-shared-types` (M0.6 placeholder package)
 *   - retry/timeout policy
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly title: string,
    public readonly detail?: string,
    public readonly extras?: Record<string, unknown>,
  ) {
    super(`[${status}] ${title}${detail ? `: ${detail}` : ""}`);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let problem: { title?: string; detail?: string; [k: string]: unknown } = {};
    try {
      problem = await response.json();
    } catch {
      // Body wasn't JSON; fall back to statusText.
    }
    throw new ApiError(
      response.status,
      problem.title ?? response.statusText,
      problem.detail,
      problem,
    );
  }

  // 204 No Content / 205 Reset
  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const apiBase = (): string => API_BASE;
