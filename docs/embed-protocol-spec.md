# HealthFirst Embed Protocol Specification

**Version:** 1.0.0
**Status:** Draft
**Author:** HealthFirst Platform Team
**Last Updated:** 2026-05-18

---

## Table of Contents

1. [Overview](#1-overview)
2. [Glossary](#2-glossary)
3. [Architecture](#3-architecture)
4. [Message Envelope](#4-message-envelope)
5. [Session Lifecycle](#5-session-lifecycle)
6. [Platform → App Messages](#6-platform--app-messages)
7. [App → Platform Messages](#7-app--platform-messages)
8. [Auth Token Specification](#8-auth-token-specification)
9. [User Context Object](#9-user-context-object)
10. [Error Codes](#10-error-codes)
11. [Security Rules](#11-security-rules)
12. [iFrame Sandbox Policy](#12-iframe-sandbox-policy)
13. [SDK Method Mapping](#13-sdk-method-mapping)
14. [Versioning Policy](#14-versioning-policy)
15. [Compliance Requirements](#15-compliance-requirements)

---

## 1. Overview

The HealthFirst Embed Protocol defines the communication contract between the
HealthFirst platform (the **Host**) and third-party developer applications
(the **Guest**) embedded inside the platform via iFrame.

This protocol governs:
- How the Host injects user health context into the Guest
- How the Guest requests actions from the Host
- How payments are initiated and confirmed
- How user health data is accessed securely
- How the session lifecycle is managed

All communication uses the browser's `window.postMessage` API.
The HealthFirst Embed SDK (`@healthfirst/embed-sdk`) implements this
protocol on the Guest side — developers should use the SDK rather than
implementing raw postMessage calls.

### Design Principles

```
1. Host controls the frame — Guest cannot navigate or resize the outer window
2. Least privilege — Guest receives only what the user consented to share
3. Payment isolation — Guest never handles money; all payments go through Host
4. Fail safe — any protocol violation closes the session, never exposes data
5. Backwards compatible — new fields are additive; old fields are never removed
```

---

## 2. Glossary

| Term | Definition |
|---|---|
| **Host** | The HealthFirst platform. Owns the outer page, renders the iFrame, controls the App Container. |
| **Guest** | The third-party developer application running inside the iFrame. |
| **App Container** | The UI chrome the Host renders around the Guest iFrame (header bar, loading state, error state). |
| **Context Bridge** | The postMessage channel between Host and Guest. |
| **Health Graph** | The user's persistent health profile owned by the Host platform. |
| **Auth Token** | Short-lived signed JWT the Host issues so the Guest can read the Health Graph API. |
| **Session** | One instance of a Guest app opened by a user. Starts on `INIT`, ends on `CLOSE` or error. |
| **Consented Fields** | The subset of Health Graph fields the user explicitly permitted this app to read. |

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  HOST (HealthFirst Platform)                                     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  App Container                                             │  │
│  │                                                            │  │
│  │  [App Name]  [HealthFirst Verified ✓]          [✕ Close]  │  │
│  │  ─────────────────────────────────────────────────────    │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │                                                      │  │  │
│  │  │   GUEST iFrame                                       │  │  │
│  │  │   origin: https://developer-app.com                  │  │  │
│  │  │                                                      │◄─┼──┼── postMessage
│  │  │   Developer app renders here.                        │  │  │   Context Bridge
│  │  │   Cannot access Host DOM.                            │──┼──┼──►
│  │  │   Cannot navigate Host window.                       │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Health Graph   │  │  Payment Sheet  │  │  Analytics      │  │
│  │  API            │  │  (overlaid on   │  │  Event Pipe     │  │
│  │                 │  │   iFrame when   │  │                 │  │
│  │  REST API that  │  │   payment       │  │  Receives       │  │
│  │  Guest calls    │  │   requested)    │  │  TRACK events   │  │
│  │  using JWT      │  │                 │  │  from Guest     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Origin Model

```
Host origin:   https://app.healthfirst.in          (production)
               https://sandbox.healthfirst.in       (sandbox)

Guest origin:  https://<developer-registered-domain>
               Must match app manifest allowed_origins exactly.
               Subdomains are NOT auto-allowed — each must be registered.
```

---

## 4. Message Envelope

Every postMessage in both directions uses this standard envelope.
Messages that do not conform to this envelope MUST be silently ignored.

```typescript
interface MessageEnvelope {
  // Identifies the message as part of this protocol.
  // Recipients MUST check this field first and ignore messages
  // where namespace !== "HEALTHFIRST_EMBED"
  namespace:  "HEALTHFIRST_EMBED";

  // Protocol version. Recipient must check compatibility.
  version:    string;                // e.g. "1.0"

  // Unique message ID for correlation (UUID v4)
  message_id: string;

  // The message type — determines the payload shape
  type:       MessageType;

  // The message payload — shape defined per type below
  payload:    object;

  // Unix timestamp (ms) when this message was sent
  sent_at:    number;

  // HMAC-SHA256 of (message_id + type + sent_at) using app's secret key.
  // Present only on Host → Guest messages.
  // Guest MUST verify this signature before trusting any message.
  signature?: string;
}
```

### Sending a message (Host side pseudocode)

```javascript
guestIframe.contentWindow.postMessage(
  {
    namespace:  "HEALTHFIRST_EMBED",
    version:    "1.0",
    message_id: crypto.randomUUID(),
    type:       "INIT",
    payload:    { ... },
    sent_at:    Date.now(),
    signature:  hmac(message_id + type + sent_at, app_secret_key)
  },
  "https://developer-registered-origin.com"   // targetOrigin — never "*"
);
```

### Receiving a message (Guest side pseudocode)

```javascript
window.addEventListener("message", (event) => {
  // 1. Verify origin
  if (event.origin !== "https://app.healthfirst.in") return;

  // 2. Verify namespace
  if (event.data?.namespace !== "HEALTHFIRST_EMBED") return;

  // 3. Verify version compatibility
  if (!isCompatibleVersion(event.data.version)) return;

  // 4. Verify signature (for Host→Guest messages)
  if (!verifySignature(event.data, appSecretKey)) return;

  // 5. Handle the message
  handleMessage(event.data);
});
```

---

## 5. Session Lifecycle

```
HOST                                    GUEST
 │                                        │
 │  Renders iFrame with embed URL         │
 │ ─────────────────────────────────────► │  iFrame loads
 │                                        │  Guest includes SDK
 │                                        │  SDK listens for INIT
 │                                        │
 │  [after iFrame load event]             │
 │  Sends INIT message with context       │
 │ ─────────────────────────────────────► │
 │                                        │  Guest receives context
 │                                        │  Guest renders UI
 │                                        │  Guest sends APP_READY
 │                                        │
 │ ◄───────────────────────────────────── │  APP_READY
 │                                        │
 │  App Container removes loading state   │
 │  Guest iFrame becomes visible to user  │
 │                                        │
 │         [active session]               │
 │                                        │
 │ ◄───────────────────────────────────── │  RESIZE (as needed)
 │ ◄───────────────────────────────────── │  TRACK_EVENT (as needed)
 │ ◄───────────────────────────────────── │  REQUEST_PAYMENT (if needed)
 │  ─────────────────────────────────────►│  PAYMENT_RESULT
 │ ◄───────────────────────────────────── │  TOKEN_REFRESH_REQUEST (before expiry)
 │  ─────────────────────────────────────►│  TOKEN_REFRESH
 │                                        │
 │         [session end]                  │
 │                                        │
 │ ◄───────────────────────────────────── │  CLOSE (guest-initiated)
 │                  OR                    │
 │  User clicks Host close button         │
 │  ─────────────────────────────────────►│  CLOSE_REQUEST (host-initiated)
 │                                        │  Guest does cleanup
 │ ◄───────────────────────────────────── │  CLOSE
 │                                        │
 │  Host destroys iFrame                  │
```

### Timeout Rules

| Timeout | Duration | Action |
|---|---|---|
| INIT delivery timeout | 5s after iFrame load | Host shows error state |
| APP_READY timeout | 10s after INIT sent | Host shows error state |
| Token refresh window | Must refresh within 13 min (of 15 min TTL) | Auto-close if missed |
| CLOSE acknowledgement | 3s after CLOSE_REQUEST | Host force-destroys iFrame |

---

## 6. Platform → App Messages

### 6.1 INIT

Sent by the Host immediately after the iFrame loads.
This is the first message in every session.
Guest MUST NOT render any UI until INIT is received.

```typescript
{
  type: "INIT",
  payload: {
    // Session identifier — unique per user+app+open
    session_id: string;                     // e.g. "sess_a1b2c3"

    // Short-lived JWT for Health Graph API access
    // TTL: 15 minutes. Refresh using TOKEN_REFRESH_REQUEST before expiry.
    auth_token: string;

    // User's health context — only consented fields are populated.
    // Non-consented fields are omitted entirely (not null, not empty).
    user_context: UserContext;              // See Section 9

    // Platform environment
    platform: {
      env:        "production" | "sandbox";
      locale:     string;                   // e.g. "en-IN"
      currency:   string;                   // e.g. "INR"
      theme:      "light" | "dark";
    };

    // App's own configuration (from manifest, passed back for convenience)
    app: {
      app_id:     string;
      name:       string;
      version:    string;                   // approved manifest version
    };
  }
}
```

### 6.2 TOKEN_REFRESH

Sent in response to a TOKEN_REFRESH_REQUEST from the Guest.

```typescript
{
  type: "TOKEN_REFRESH",
  payload: {
    auth_token:   string;    // new JWT, 15 min TTL
    expires_at:   number;    // Unix ms
  }
}
```

### 6.3 PAYMENT_RESULT

Sent after the Host completes or cancels a payment triggered by REQUEST_PAYMENT.

```typescript
{
  type: "PAYMENT_RESULT",
  payload: {
    // Correlates to the REQUEST_PAYMENT message_id
    request_id:      string;

    success:         boolean;

    // Present only if success = true
    transaction?: {
      transaction_id: string;     // platform transaction ID
      amount:         number;     // amount charged in smallest currency unit
      currency:       string;
      plan_id:        string;     // as sent in REQUEST_PAYMENT
      charged_at:     number;     // Unix ms
    };

    // Present only if success = false
    failure?: {
      code:    PaymentFailureCode;
      message: string;            // human-readable, safe to show to user
    };
  }
}
```

```typescript
type PaymentFailureCode =
  | "USER_CANCELLED"
  | "INSUFFICIENT_FUNDS"
  | "PAYMENT_GATEWAY_ERROR"
  | "SESSION_EXPIRED"
  | "DUPLICATE_REQUEST";
```

### 6.4 CLOSE_REQUEST

Sent when the user clicks the close button in the Host's App Container chrome,
or when the platform needs to close the app programmatically (e.g. session timeout).

```typescript
{
  type: "CLOSE_REQUEST",
  payload: {
    reason: "user_dismissed" | "session_timeout" | "platform_close";
  }
}
```

Guest should do cleanup (save state, cancel pending requests) and respond with CLOSE
within 3 seconds. After 3 seconds, Host force-destroys the iFrame regardless.

### 6.5 THEME_CHANGE

Sent when the user changes the platform theme during an active session.

```typescript
{
  type: "THEME_CHANGE",
  payload: {
    theme: "light" | "dark";
  }
}
```

---

## 7. App → Platform Messages

### 7.1 APP_READY

Sent by the Guest after it has rendered its initial UI and is ready for the user to see.
Host removes the loading skeleton and makes the iFrame visible.

```typescript
{
  type: "APP_READY",
  payload: {
    initial_height: number;    // pixels — Host sets iFrame height to this on reveal
  }
}
```

### 7.2 RESIZE

Sent when the Guest's content height changes and the iFrame needs to be taller/shorter.
Host must respond by updating the iFrame height within one animation frame.

```typescript
{
  type: "RESIZE",
  payload: {
    height: number;    // pixels
                       // Must be between app manifest min_height and max_height
                       // Host clamps to manifest limits silently
  }
}
```

**Rate limit:** Maximum 10 RESIZE messages per second. Excess messages are dropped.

### 7.3 TRACK_EVENT

Sent when the Guest wants to log a user interaction event to the platform's
analytics pipeline. These events appear in the developer's analytics dashboard.

```typescript
{
  type: "TRACK_EVENT",
  payload: {
    // Developer-defined event name.
    // Must match pattern: ^[a-z][a-z0-9_]{1,49}$
    event_name: string;          // e.g. "meal_plan_viewed"

    // Developer-defined properties.
    // All values must be string, number, or boolean — no nested objects.
    // Maximum 20 properties per event.
    // Maximum key length: 40 characters.
    // Maximum string value length: 255 characters.
    properties?: Record<string, string | number | boolean>;
  }
}
```

**Reserved event names** (used by Host internally — Guest must not send these):
- `app_opened`, `app_closed`, `payment_started`, `payment_completed`

**Rate limit:** Maximum 30 TRACK_EVENT messages per minute. Excess messages are dropped.

### 7.4 REQUEST_PAYMENT

Sent when the Guest wants to charge the user. Host overlays a native payment sheet
on top of the iFrame. Guest must pause its UI while payment is in progress.

```typescript
{
  type: "REQUEST_PAYMENT",
  payload: {
    // Developer-defined plan identifier — returned in PAYMENT_RESULT
    plan_id:        string;

    // Amount in smallest currency unit (paise for INR)
    amount:         number;           // e.g. 49900 for ₹499

    currency:       "INR";            // Only INR supported in v1.0

    // Billing frequency
    billing_cycle:  "one_time" | "monthly" | "quarterly" | "annual";

    // Shown to user in Host's payment sheet
    description:    string;           // max 80 characters
    
    // Optional: free trial before charging
    trial?: {
      duration_days: number;          // e.g. 7
    };
  }
}
```

**Rules:**
- Only one REQUEST_PAYMENT may be in-flight at a time
- Sending a second REQUEST_PAYMENT while one is pending is a protocol error
- Amount must match the price declared in the approved app manifest (±2% tolerance)
  Mismatches are rejected and flagged for compliance review

### 7.5 TOKEN_REFRESH_REQUEST

Sent when the Guest's auth token is approaching expiry.
Guest should send this at least 2 minutes before expiry (token TTL is 15 minutes,
so send at the 13-minute mark).

```typescript
{
  type: "TOKEN_REFRESH_REQUEST",
  payload: {}    // no payload needed
}
```

Host responds with TOKEN_REFRESH. If Host cannot refresh (session invalidated),
it sends CLOSE_REQUEST instead.

### 7.6 NAVIGATE

Sent when the Guest wants to ask the Host to navigate the user to a specific
step in the Host's onboarding flow. Use sparingly — typically for "Go back to
your health dashboard" type flows.

```typescript
{
  type: "NAVIGATE",
  payload: {
    destination: "health_goals"
                | "health_profile"
                | "product_match"
                | "dashboard"
                | "back";     // navigate to whatever was shown before this app
  }
}
```

### 7.7 CLOSE

Sent when the Guest is done and wants to close itself.
Must be sent in response to CLOSE_REQUEST, or guest-initiated when the flow is complete.

```typescript
{
  type: "CLOSE",
  payload: {
    reason:  "completed"    // user completed the app's flow successfully
           | "dismissed"    // user chose to exit without completing
           | "error";       // app encountered an unrecoverable error

    // Optional outcome data passed back to Host for analytics + user profile update
    outcome?: {
      converted:      boolean;
      plan_selected?: string;         // developer-defined plan ID
      goal_achieved?: string;         // e.g. "onboarding_complete"
    };
  }
}
```

### 7.8 ERROR

Sent when the Guest encounters an error it cannot recover from.
Host shows an error state in the App Container.

```typescript
{
  type: "ERROR",
  payload: {
    code:    AppErrorCode;
    message: string;        // developer-facing message (not shown to user)
    fatal:   boolean;       // if true, Host closes the container
  }
}
```

```typescript
type AppErrorCode =
  | "INIT_FAILED"            // Guest could not process INIT payload
  | "HEALTH_GRAPH_UNAVAILABLE" // Health Graph API unreachable
  | "RENDER_FAILED"          // Guest UI failed to render
  | "UNEXPECTED_ERROR";      // catch-all
```

---

## 8. Auth Token Specification

The auth token is a signed JWT issued by the Host.
Guests use it as a Bearer token to call the HealthFirst Health Graph REST API.

### JWT Header
```json
{
  "alg": "HS256",
  "typ": "JWT"
}
```

### JWT Payload
```json
{
  "iss": "healthfirst-platform",
  "sub": "usr_a1b2c3d4",         // HealthFirst platform user ID
  "app": "app_nutricoach",        // app_id from manifest
  "sid": "sess_x9y8z7",           // session_id from INIT
  "scope": [                      // consented fields user approved for this app
    "goals",
    "persona",
    "diet_type"
  ],
  "env": "production",
  "iat": 1716000000,              // issued at (Unix seconds)
  "exp": 1716000900               // expires at (iat + 900s = 15 minutes)
}
```

### Validation rules (Guest must enforce)

```
1. Verify signature using app's secret key (from developer portal)
2. Check iss === "healthfirst-platform"
3. Check app matches your own app_id (prevents token reuse across apps)
4. Check exp > current time (reject expired tokens)
5. Only request Health Graph fields listed in scope
   — API will reject out-of-scope requests anyway, but client-side check is good practice
```

### Health Graph API usage

```http
GET https://api.healthfirst.in/v1/users/{user_id}/health-graph
Authorization: Bearer <auth_token>
X-App-ID: app_nutricoach
X-Session-ID: sess_x9y8z7

Response 200:
{
  "user_id": "usr_a1b2c3d4",
  "goals": ["weight_loss", "more_energy"],
  "persona": "busy_professional",
  "diet_type": "keto"
  // Only consented fields are returned
  // Non-consented fields are absent (not null)
}

Response 401: token expired or invalid
Response 403: requested field not in token scope
Response 429: rate limit exceeded
```

---

## 9. User Context Object

Passed in the INIT message payload.
Only fields the user consented to share are present.
All fields are optional at the type level — check for presence before use.

```typescript
interface UserContext {
  // Platform-assigned user identifier.
  // Use this as the key for your own user records.
  // Never changes for the same user.
  user_id: string;

  // ── Explicitly declared by user ────────────────────────────────────────

  // Primary health goals. Maximum 3.
  goals?: Array<
    | "weight_loss"
    | "muscle_gain"
    | "better_sleep"
    | "more_energy"
    | "immunity"
    | "gut_health"
    | "stress_relief"
  >;

  // Broad age bucket — never exact age
  age_range?: "18-24" | "25-34" | "35-44" | "45-54" | "55+";

  // Activity level
  activity_level?: "sedentary" | "lightly_active" | "moderate" | "very_active";

  // Dietary preference
  diet_type?: "vegan" | "vegetarian" | "keto" | "paleo" | "no_preference";

  // Self-declared health conditions (only shared if user explicitly consented)
  conditions?: string[];          // e.g. ["diabetes_type_2", "hypertension"]

  // Budget sensitivity (never exact income)
  budget_range?: "value" | "mid" | "premium";

  // ── Inferred by platform (never exposed to developers) ─────────────────
  // trust_level, persona_scores, behavioral signals, purchase_history
  // are NEVER included in user_context regardless of consent.
  // Developers cannot request these fields.

  // ── Derived signals (available with explicit consent) ──────────────────

  // Broad health archetype inferred from behavior
  persona?: 
    | "busy_professional"
    | "performance_athlete"
    | "chronic_condition"
    | "weight_loss_seeker"
    | "wellness_explorer";

  // How health-engaged is this user
  health_maturity?: "new"       // first health purchase journey
                  | "aware"     // knows basics, building habits
                  | "committed" // consistent health routines
                  | "expert";   // deep health knowledge, high engagement
}
```

---

## 10. Error Codes

### Protocol Errors (Host closes session immediately on these)

| Code | Trigger | Action |
|---|---|---|
| `INVALID_ORIGIN` | Message from unregistered origin | Silently ignore |
| `INVALID_NAMESPACE` | `namespace !== "HEALTHFIRST_EMBED"` | Silently ignore |
| `INVALID_SIGNATURE` | HMAC verification fails | Close session, log security event |
| `VERSION_INCOMPATIBLE` | Guest on unsupported version | Close with error, prompt SDK update |
| `DUPLICATE_PAYMENT` | Second REQUEST_PAYMENT while one in-flight | Reject, send ERROR to Guest |
| `AMOUNT_MISMATCH` | Payment amount deviates > 2% from manifest | Reject, flag for compliance |
| `RATE_LIMIT_EXCEEDED` | Too many RESIZE or TRACK_EVENT messages | Drop excess, log |
| `INIT_TIMEOUT` | APP_READY not received within 10s of INIT | Show error state in container |
| `CLOSE_TIMEOUT` | CLOSE not received within 3s of CLOSE_REQUEST | Force-destroy iFrame |
| `RESERVED_EVENT_NAME` | Guest sends reserved TRACK_EVENT name | Drop event, log warning |

---

## 11. Security Rules

### 11.1 Origin Validation (Both sides)

```
Host must:
  - Always set targetOrigin to app's registered production/sandbox domain
  - Never use targetOrigin = "*"
  - Reject all messages where event.origin is not the Host's own origin

Guest must:
  - Always verify event.origin === "https://app.healthfirst.in" (production)
    or "https://sandbox.healthfirst.in" (sandbox) before processing
  - Never trust messages from any other origin
  - Never use targetOrigin = "*" when posting back
```

### 11.2 Signature Verification

```
Every Host → Guest message is HMAC-SHA256 signed.
Signature covers: message_id + type + sent_at
Key: app's secret key from developer portal

Guest MUST verify signature before processing INIT or TOKEN_REFRESH.
Failure to verify = close session.

Note: Guest → Host messages are NOT signed because the Guest does not
hold a symmetric secret that is safe in browser JS. Origin validation
is the security boundary for Guest → Host messages.
```

### 11.3 Data Handling Rules for Guests

```
Guests MUST:
  □ Only read Health Graph fields listed in auth token scope
  □ Not store auth_token beyond the session (no localStorage, no cookies)
  □ Not log user_context fields to external analytics
  □ Not pass user_id or health data to any third-party service
  □ Destroy all session data on CLOSE

Guests MUST NOT:
  □ Attempt to access the Host's DOM via any mechanism
  □ Use document.referrer to infer platform URL structure
  □ Make cross-origin requests with user credentials attached
  □ Store health data server-side beyond what's needed to provide the service
```

### 11.4 Content Security Policy

Host sets the following CSP for the iFrame's parent frame to prevent
the Guest from loading unexpected resources:

```
frame-src 'self' <developer-registered-origins>;
```

Guests must declare all external resources loaded in their app
(CDNs, fonts, analytics) during manifest submission.
Undeclared external resources will be blocked.

---

## 12. iFrame Sandbox Policy

```html
<iframe
  src="https://developer-app.com/healthfirst/embed?token=..."
  sandbox="allow-scripts allow-forms allow-same-origin allow-popups"
  allow="camera 'none'; microphone 'none'; geolocation 'none';
         payment 'none'; usb 'none'"
  referrerpolicy="no-referrer"
  loading="lazy"
  title="[App Name] — HealthFirst"
/>
```

### Sandbox attribute explanation

| Attribute | Reason |
|---|---|
| `allow-scripts` | Guest JS must execute |
| `allow-forms` | Guest may have forms (search, input) |
| `allow-same-origin` | Required for postMessage to work reliably |
| `allow-popups` | Needed for OAuth flows (e.g. Google login inside Guest) |
| ~~`allow-top-navigation`~~ | **Blocked** — Guest cannot redirect the Host page |
| ~~`allow-downloads`~~ | **Blocked** — no file downloads |

---

## 13. SDK Method Mapping

The `@healthfirst/embed-sdk` package maps clean developer-facing methods
to the underlying postMessage protocol.

| SDK Method | Sends Message | Receives Message |
|---|---|---|
| `sdk.onInit(callback)` | — | `INIT` |
| `sdk.ready(height)` | `APP_READY` | — |
| `sdk.resize(height)` | `RESIZE` | — |
| `sdk.track(name, props)` | `TRACK_EVENT` | — |
| `sdk.requestPayment(opts)` | `REQUEST_PAYMENT` | `PAYMENT_RESULT` |
| `sdk.refreshToken()` | `TOKEN_REFRESH_REQUEST` | `TOKEN_REFRESH` |
| `sdk.navigate(dest)` | `NAVIGATE` | — |
| `sdk.close(reason, outcome)` | `CLOSE` | — |
| `sdk.onCloseRequest(cb)` | — | `CLOSE_REQUEST` |
| `sdk.onThemeChange(cb)` | — | `THEME_CHANGE` |
| `sdk.getHealthGraph(token)` | (REST API call, not postMessage) | — |

### SDK Quick Start

```javascript
import { HealthFirstSDK } from '@healthfirst/embed-sdk';

const sdk = new HealthFirstSDK();

// 1. Wait for platform to inject context
sdk.onInit(async ({ user, auth_token, platform }) => {

  // 2. Optionally fetch full health graph
  const graph = await sdk.getHealthGraph(auth_token);

  // 3. Render your UI using context
  renderApp(user, graph, platform.theme);

  // 4. Tell platform you're ready (pass your initial height)
  sdk.ready(600);
});

// Handle theme changes
sdk.onThemeChange(({ theme }) => applyTheme(theme));

// Handle close request from platform
sdk.onCloseRequest(({ reason }) => {
  saveProgress();
  sdk.close('dismissed');
});
```

---

## 14. Versioning Policy

### Version format: MAJOR.MINOR

```
MAJOR bump: Breaking change — old Guests will stop working.
            Platform gives 6 months deprecation notice.
            Old version served in parallel during transition.

MINOR bump: Additive change — new optional fields, new message types.
            Old Guests continue working without changes.
            New fields are always optional; old fields never removed.
```

### Version compatibility matrix

| SDK Version | Protocol Version | Support Status |
|---|---|---|
| 1.x | 1.0 | ✓ Active |

### Deprecation process

```
1. New major version announced with migration guide
2. Old version marked deprecated in developer portal
3. 6-month parallel support window
4. Email notifications to all developers on old version at:
   T-6 months, T-3 months, T-1 month, T-2 weeks
5. Old version sunset — requests return VERSION_INCOMPATIBLE error
```

---

## 15. Compliance Requirements

All Guests embedding in the HealthFirst platform must comply with:

### Data handling
```
□ India Digital Personal Data Protection Act (DPDP) 2023
□ User data must be stored in India (data residency)
□ Health data (conditions, diagnoses) requires explicit separate consent
□ User can request deletion of their data — Guest must honour within 72 hours
□ No selling or sharing of user health data with third parties
```

### Health content
```
□ No claims to diagnose, treat, cure, or prevent any medical condition
□ Any health advice content must carry "Consult your doctor" disclaimer
□ Supplement claims must be backed by referenced studies
□ Pricing must be transparent — no hidden charges
```

### Accessibility
```
□ Guest UI must meet WCAG 2.1 AA minimum
□ Guest must respond to platform theme (light/dark)
□ Guest must be operable without mouse (keyboard navigation)
```

---

## Appendix A — Complete Message Type Reference

| Type | Direction | Description |
|---|---|---|
| `INIT` | Host → Guest | Inject session context + auth token |
| `TOKEN_REFRESH` | Host → Guest | New auth token in response to refresh request |
| `PAYMENT_RESULT` | Host → Guest | Outcome of a payment request |
| `CLOSE_REQUEST` | Host → Guest | Platform asking Guest to close |
| `THEME_CHANGE` | Host → Guest | User changed platform theme |
| `APP_READY` | Guest → Host | Guest rendered and visible |
| `RESIZE` | Guest → Host | Request container height change |
| `TRACK_EVENT` | Guest → Host | Log analytics event |
| `REQUEST_PAYMENT` | Guest → Host | Initiate payment via platform rails |
| `TOKEN_REFRESH_REQUEST` | Guest → Host | Request new auth token |
| `NAVIGATE` | Guest → Host | Navigate Host to a platform step |
| `CLOSE` | Guest → Host | Guest closing the session |
| `ERROR` | Guest → Host | Unrecoverable Guest error |

---

## Appendix B — Minimal Integration Checklist

Before submitting your app for review, verify:

```
□ SDK initialised and APP_READY sent within 5 seconds of page load
□ Token refresh implemented (send TOKEN_REFRESH_REQUEST at 13-minute mark)
□ CLOSE_REQUEST handler implemented (respond within 3 seconds)
□ No health data logged to external services
□ Auth token not persisted in localStorage or cookies
□ All external resource URLs declared in app manifest
□ Payment amount matches manifest (within 2% tolerance)
□ Tested in sandbox environment with all synthetic user personas
□ WCAG 2.1 AA accessibility validated
□ App responds correctly to both light and dark theme
```
