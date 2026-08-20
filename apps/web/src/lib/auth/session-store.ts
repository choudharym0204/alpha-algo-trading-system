/**
 * In-memory session store.
 *
 * Access and refresh tokens live ONLY in this module's memory — never in
 * localStorage/sessionStorage/cookies/IndexedDB. The backend returns tokens in
 * the JSON body (it sets no httpOnly cookie), so there is no safer
 * browser-storage mechanism to use; keeping them out of persistent storage is
 * the correct choice (spec §5 / §42).
 *
 * Consequence (documented, not a bug): a full page reload clears this module,
 * so the user must sign in again. Client-side navigations preserve the session.
 */

export interface Session {
  accessToken: string;
  refreshToken: string;
  /** Epoch ms when the access token expires (login/refresh return expires_in seconds). */
  accessExpiresAt: number;
}

let currentSession: Session | null = null;

export function setSession(session: Session): void {
  currentSession = session;
}

export function getSession(): Session | null {
  return currentSession;
}

export function clearSession(): void {
  currentSession = null;
}

/** True when the access token is present and not yet expired (with 5s skew). */
export function isAccessTokenUsable(session: Session | null, now: number = Date.now()): boolean {
  if (!session) return false;
  return now < session.accessExpiresAt - 5000;
}
