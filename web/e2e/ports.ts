/** Where the browser tests find the app: the usual ports, or others (E2E_WEB_PORT, E2E_API_PORT)
 *  so the tests can run while a local stack holds 5173 and 8000. */
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5173);
export const API_PORT = Number(process.env.E2E_API_PORT ?? 8000);
export const WEB = `http://localhost:${WEB_PORT}`;
export const API_ROOT = `http://localhost:${API_PORT}`;
