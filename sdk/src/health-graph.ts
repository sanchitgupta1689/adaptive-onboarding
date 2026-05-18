import { HealthGraphResponse, HealthGraphError, Environment } from "./types";

const API_URLS: Record<Environment, string> = {
  production: "https://api.healthfirst.in/v1",
  sandbox:    "https://sandbox-api.healthfirst.in/v1",
};

/**
 * Fetches the user's health graph from the HealthFirst REST API.
 *
 * The auth_token received in INIT is passed as a Bearer token.
 * The API returns only the fields the user consented to share —
 * non-consented fields are absent from the response (not null).
 *
 * Throws HealthGraphError on any failure.
 *
 * @param userId    - The user_id from UserContext
 * @param authToken - The JWT from InitPayload.auth_token
 * @param sessionId - The session_id from InitPayload.session_id
 * @param env       - "production" | "sandbox"
 */
export async function fetchHealthGraph(
  userId:    string,
  authToken: string,
  sessionId: string,
  env:       Environment = "production"
): Promise<HealthGraphResponse> {
  const baseUrl = API_URLS[env];
  const url     = `${baseUrl}/users/${encodeURIComponent(userId)}/health-graph`;

  let response: Response;

  try {
    response = await fetch(url, {
      method:  "GET",
      headers: {
        "Authorization": `Bearer ${authToken}`,
        "X-Session-ID":  sessionId,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
      },
    });
  } catch (networkError) {
    throw {
      code:    "SERVER_ERROR",
      message: "Network request failed. Check your connection.",
    } as HealthGraphError;
  }

  if (response.ok) {
    return response.json() as Promise<HealthGraphResponse>;
  }

  // Map HTTP status codes to typed errors
  const errorMap: Record<number, HealthGraphError["code"]> = {
    401: "UNAUTHORIZED",   // token expired or invalid
    403: "FORBIDDEN",      // field not in token scope
    404: "NOT_FOUND",      // user not found
    429: "RATE_LIMITED",   // too many requests
  };

  const code = errorMap[response.status] ?? "SERVER_ERROR";
  let message = `Health Graph API error: ${response.status}`;

  try {
    const body = await response.json();
    if (body?.message) message = body.message;
  } catch { /* ignore JSON parse failure */ }

  throw { code, message } as HealthGraphError;
}
