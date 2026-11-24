/** Where the browser tests run their own app. Not the local stack's 5173 / 8000: Playwright reuses a
 *  server already on a port, and the tests would then sign in to the dev database and fail. Override
 *  with E2E_WEB_PORT / E2E_API_PORT. */
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5199);
export const API_PORT = Number(process.env.E2E_API_PORT ?? 8099);
export const WEB = `http://localhost:${WEB_PORT}`;
export const API_ROOT = `http://localhost:${API_PORT}`;
