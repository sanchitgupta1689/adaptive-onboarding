# @healthfirst/embed-sdk

TypeScript SDK for embedding third-party apps inside the HealthFirst platform via the **HealthFirst Embed Protocol v1.0**.

---

## Overview

HealthFirst is a health super-app platform. Third-party developers can embed their apps inside HealthFirst as iFrames. This SDK handles all the PostMessage communication between your app (Guest) and the HealthFirst shell (Host) — session init, auth tokens, payments, navigation, analytics, and more.

```
┌──────────────────────────────────────┐
│        HealthFirst Platform (Host)    │
│  ┌────────────────────────────────┐  │
│  │   Your App (Guest iFrame)      │  │
│  │                                │  │
│  │   import { HealthFirstSDK }    │  │
│  │     from '@healthfirst/sdk'    │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

---

## Installation

```bash
npm install @healthfirst/embed-sdk
# or
yarn add @healthfirst/embed-sdk
```

---

## Quick Start

```typescript
import { HealthFirstSDK } from "@healthfirst/embed-sdk";

const sdk = new HealthFirstSDK({
  // Optional — defaults to "https://app.healthfirst.in"
  hostOrigin: "https://app.healthfirst.in",

  // Optional — HMAC-SHA256 key from the developer portal
  // Required in production; omit only in sandbox testing
  secretKey: process.env.HEALTHFIRST_SECRET_KEY,

  // Optional — ms to wait for INIT before timing out (default: 10000)
  initTimeout: 10000,

  // Optional — log messages to console (default: false)
  debug: false,
});

// 1. Wait for the platform to send INIT
const { userContext, platform, session } = await sdk.onInit((payload) => {
  console.log("User goals:", payload.user_context.goals);
  console.log("Theme:", payload.platform.theme);
});

// 2. Tell the platform your app is ready
await sdk.ready(document.body.scrollHeight);
```

---

## Core Concepts

### Session Lifecycle

```
Host sends INIT  →  sdk.onInit() fires  →  sdk.ready()  →  App renders
                                                              ↓
                                                     sdk.resize() on height change
                                                              ↓
                                              sdk.close() or Host sends CLOSE_REQUEST
```

### UserContext

HealthFirst injects the user's health profile on INIT. Fields are only present if the user consented to share them — always check before accessing.

```typescript
sdk.onInit((payload) => {
  const { user_context } = payload;

  // user_id is always present
  console.log(user_context.user_id);

  // All other fields are optional — guard before use
  if (user_context.goals?.includes("weight_loss")) {
    showWeightLossContent();
  }

  if (user_context.persona === "busy_professional") {
    showQuickSummary();
  }
});
```

### Auth Tokens

The platform issues short-lived JWT tokens (15 min TTL). The SDK **automatically** requests a refresh at the 13-minute mark — you don't need to manage this manually.

If you need the current token (e.g. for a backend call):

```typescript
const token = await sdk.refreshToken(); // returns current valid token
```

---

## API Reference

### `sdk.onInit(callback)`

Registers a callback for the INIT message from the platform.

```typescript
sdk.onInit((payload: InitPayload) => {
  const { session_id, auth_token, user_context, platform, app } = payload;
});
```

Returns a cleanup function. Call it to unregister the listener.

---

### `sdk.ready(initialHeight)`

Signals that your app has finished rendering. Must be called after `onInit`.

```typescript
await sdk.ready(document.body.scrollHeight);
```

---

### `sdk.resize(height)`

Notifies the platform that your app's height changed. Rate-limited to 10 calls/second.

```typescript
const observer = new ResizeObserver(() => {
  sdk.resize(document.body.scrollHeight);
});
observer.observe(document.body);
```

---

### `sdk.track(eventName, properties?)`

Sends an analytics event to the platform. Rate-limited to 30 calls/minute.

```typescript
sdk.track("product_viewed", { product_id: "omega-3-1000", price: 799 });
sdk.track("cta_clicked", { cta: "buy_now", position: "hero" });
```

---

### `sdk.requestPayment(opts)`

Initiates a payment flow managed by the HealthFirst platform.

```typescript
const result = await sdk.requestPayment({
  plan_id:       "omega3-monthly",
  amount:        799,
  currency:      "INR",
  billing_cycle: "monthly",
  description:   "Omega-3 Monthly Subscription",
  trial: { duration_days: 7 },  // optional
});

if (result.success) {
  console.log("Transaction:", result.transaction?.transaction_id);
} else {
  console.error("Payment failed:", result.failure?.code);
}
```

---

### `sdk.navigate(destination)`

Requests navigation to a platform screen.

```typescript
sdk.navigate("health_goals");    // User's health goals screen
sdk.navigate("health_profile");  // Health profile editor
sdk.navigate("product_match");   // Product matching results
sdk.navigate("dashboard");       // Main dashboard
sdk.navigate("back");            // Go back
```

---

### `sdk.close(reason, outcome?)`

Closes the embedded app and returns control to the platform.

```typescript
// User completed onboarding
sdk.close("completed", {
  converted:     true,
  plan_selected: "omega3-monthly",
});

// User dismissed
sdk.close("dismissed");
```

---

### `sdk.onCloseRequest(callback)`

The platform may ask your app to close (e.g. user tapped outside the iFrame).

```typescript
sdk.onCloseRequest((payload) => {
  // payload.reason: "user_dismissed" | "session_timeout" | "platform_close"
  saveProgress();
  sdk.close("dismissed");
});
```

---

### `sdk.onThemeChange(callback)`

React to the user switching between light/dark mode.

```typescript
sdk.onThemeChange((payload) => {
  document.documentElement.setAttribute("data-theme", payload.theme);
});
```

---

### `sdk.reportError(code, message, fatal)`

Reports an error to the platform for logging and alerting.

```typescript
sdk.reportError("RENDER_FAILED", "Component tree crashed", true);
```

| Code | When to use |
|------|-------------|
| `INIT_FAILED` | Could not process the INIT payload |
| `HEALTH_GRAPH_UNAVAILABLE` | Health Graph API returned an error |
| `RENDER_FAILED` | UI crashed or failed to render |
| `UNEXPECTED_ERROR` | Catch-all for unhandled errors |

---

### `sdk.getHealthGraph()`

Fetches the full Health Graph from the HealthFirst REST API. Richer than `UserContext` — includes all consented fields.

```typescript
const graph = await sdk.getHealthGraph();

if (graph.persona === "performance_athlete") {
  showProteinProducts();
}
```

Requires the `auth_token` from INIT — the SDK manages this automatically.

---

### `sdk.getUserContext()`

Returns the `UserContext` from the INIT payload (synchronous, no API call).

```typescript
const ctx = sdk.getUserContext();
// null if called before onInit fires
```

---

### `sdk.getPlatformContext()`

Returns `PlatformContext` from the INIT payload (synchronous).

```typescript
const platform = sdk.getPlatformContext();
// { env, locale, currency, theme }
```

---

### `sdk.destroy()`

Removes all event listeners and clears timers. Call when your app unmounts.

```typescript
// React example
useEffect(() => {
  return () => sdk.destroy();
}, []);
```

---

## Health Graph API

Use `fetchHealthGraph()` directly if you need lower-level access:

```typescript
import { fetchHealthGraph } from "@healthfirst/embed-sdk";

const graph = await fetchHealthGraph(userId, authToken, sessionId, "production");
```

---

## Security

- All Host → Guest messages carry an **HMAC-SHA256 signature** over `message_id + type + sent_at`.
- The SDK verifies every signature when `secretKey` is provided in `SDKOptions`.
- **Never skip signature verification in production.**
- Tokens expire after 15 minutes. The SDK auto-refreshes at 13 minutes.
- The iFrame must be sandboxed with `allow-scripts allow-same-origin allow-forms allow-popups`.

---

## Sandbox Testing

```typescript
const sdk = new HealthFirstSDK({
  hostOrigin: "https://sandbox.healthfirst.in",
  // secretKey can be omitted in sandbox — signature verification is skipped
});
```

Use the sandbox environment to test without affecting production data.

---

## Error Handling

```typescript
import type { HealthGraphError } from "@healthfirst/embed-sdk";

try {
  const graph = await sdk.getHealthGraph();
} catch (err) {
  const error = err as HealthGraphError;

  switch (error.code) {
    case "UNAUTHORIZED":  // Token expired
      await sdk.refreshToken();
      break;
    case "FORBIDDEN":     // User hasn't consented to this field
      showConsentPrompt();
      break;
    case "RATE_LIMITED":
      showRetryMessage();
      break;
    default:
      sdk.reportError("HEALTH_GRAPH_UNAVAILABLE", error.message, false);
  }
}
```

---

## TypeScript Support

Full types are exported for all payloads, message envelopes, and enums:

```typescript
import type {
  InitPayload,
  UserContext,
  PaymentResultPayload,
  HealthGoal,
  Persona,
  Theme,
} from "@healthfirst/embed-sdk";
```

---

## Protocol Version

This SDK implements **HealthFirst Embed Protocol v1.0**.

Major version compatibility: the SDK accepts messages from any `1.x` host but rejects `2.x` messages.

---

## License

© HealthFirst. For use by registered HealthFirst App Store developers only.
