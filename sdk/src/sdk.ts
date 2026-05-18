import {
  SDKOptions,
  UserContext,
  PlatformContext,
  AppInfo,
  InitPayload,
  TokenRefreshPayload,
  PaymentResultPayload,
  CloseRequestPayload,
  ThemeChangePayload,
  AppReadyPayload,
  RequestPaymentPayload,
  ClosePayload,
  CloseReason,
  ErrorPayload,
  AppErrorCode,
  NavigationDestination,
  Theme,
  HealthGraphResponse,
  DesignTokens,
} from "./types";

import {
  buildMessage,
  isValidHostMessage,
  verifySignature,
  RateLimiter,
} from "./messages";

import { fetchHealthGraph } from "./health-graph";

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_HOST_ORIGIN  = "https://app.healthfirst.in";
const DEFAULT_INIT_TIMEOUT = 10_000;  // 10 seconds

// Token refresh: send TOKEN_REFRESH_REQUEST 2 minutes before expiry
// Token TTL is 15 minutes (900s), so refresh at 780s (13 min)
const TOKEN_REFRESH_BEFORE_EXPIRY_MS = 2 * 60 * 1000;

// Rate limits from spec
const RESIZE_RATE_LIMIT      = { maxCount: 10, windowMs: 1_000 };   // 10/sec
const TRACK_EVENT_RATE_LIMIT = { maxCount: 30, windowMs: 60_000 };  // 30/min

// Reserved event names that developers must not use
const RESERVED_EVENT_NAMES = new Set([
  "app_opened", "app_closed", "payment_started", "payment_completed",
]);

// ─── HealthFirstSDK ───────────────────────────────────────────────────────────

/**
 * HealthFirst Embed SDK
 *
 * Implements the HealthFirst Embed Protocol v1.0 for Guest (developer) apps.
 * Handles all postMessage communication, auth token lifecycle, and rate limiting.
 *
 * Quick start:
 *   const sdk = new HealthFirstSDK();
 *   sdk.onInit(async ({ user, auth_token, session_id, platform }) => {
 *     const graph = await sdk.getHealthGraph(auth_token);
 *     renderApp(user, graph);
 *     sdk.ready(600);
 *   });
 */
export class HealthFirstSDK {
  private readonly hostOrigin:  string;
  private readonly initTimeout: number;
  private readonly debug:       boolean;

  // Session state — populated after INIT is received
  private sessionId?:      string;
  private authToken?:      string;
  private tokenExpiry?:    number;
  private userContext?:    UserContext;
  private platform?:       PlatformContext;
  private appInfo?:        AppInfo;
  private currentTokens?:  DesignTokens;
  private isReady          = false;
  private paymentInFlight  = false;

  // Pending payment promise resolver — resolved when PAYMENT_RESULT arrives
  private pendingPaymentResolve?: (result: PaymentResultPayload) => void;
  // Pending token refresh resolver
  private pendingTokenRefreshResolve?: (token: TokenRefreshPayload) => void;

  // Developer-registered callbacks
  private initCallback?:         (ctx: InitContext)         => void | Promise<void>;
  private closeRequestCallback?: (payload: CloseRequestPayload) => void;
  private themeChangeCallback?:  (payload: ThemeChangePayload)  => void;

  // Rate limiters
  private resizeLimiter     = new RateLimiter(RESIZE_RATE_LIMIT.maxCount, RESIZE_RATE_LIMIT.windowMs);
  private trackEventLimiter = new RateLimiter(TRACK_EVENT_RATE_LIMIT.maxCount, TRACK_EVENT_RATE_LIMIT.windowMs);

  // Token auto-refresh timer handle
  private tokenRefreshTimer?: ReturnType<typeof setTimeout>;

  // The bound event listener (stored so we can remove it on destroy)
  private messageListener: (event: MessageEvent) => void;

  constructor(options: SDKOptions = {}) {
    this.hostOrigin  = options.hostOrigin  ?? DEFAULT_HOST_ORIGIN;
    this.initTimeout = options.initTimeout ?? DEFAULT_INIT_TIMEOUT;
    this.debug       = options.debug       ?? false;

    // Bind the message listener once and store it for removal later
    this.messageListener = this.handleMessage.bind(this);
    window.addEventListener("message", this.messageListener);

    this.log("SDK initialised. Waiting for INIT from host...");

    // Start INIT timeout — if INIT not received in time, log a warning
    setTimeout(() => {
      if (!this.sessionId) {
        this.log("WARNING: INIT message not received within timeout.", "warn");
      }
    }, this.initTimeout);
  }

  // ─── Developer-facing API ─────────────────────────────────────────────────

  /**
   * Register a callback to be called when the platform sends INIT.
   * This is the entry point for every Guest app — do all setup here.
   *
   * The callback receives the full InitContext:
   *   user       — UserContext (only consented fields present)
   *   auth_token — Use this with getHealthGraph() to fetch the full graph
   *   session_id — Unique ID for this session
   *   platform   — Theme, locale, currency, environment
   *   app        — Your app's ID, name, and manifest version
   */
  onInit(callback: (ctx: InitContext) => void | Promise<void>): this {
    this.initCallback = callback;
    return this;
  }

  /**
   * Tell the platform your app is rendered and ready to be shown to the user.
   * The platform removes the loading skeleton on receiving this.
   * Call this as soon as your initial UI is painted.
   *
   * @param initialHeight - Your app's initial height in pixels
   */
  ready(initialHeight: number): this {
    this.assertInitReceived("ready");

    const payload: AppReadyPayload = { initial_height: initialHeight };
    this.postToHost(buildMessage("APP_READY", payload));
    this.isReady = true;
    this.log(`APP_READY sent (height: ${initialHeight}px)`);
    return this;
  }

  /**
   * Request the platform to resize the iFrame container.
   * Rate limited to 10 calls per second — excess calls are silently dropped.
   *
   * @param height - Desired height in pixels
   */
  resize(height: number): this {
    this.assertInitReceived("resize");

    if (!this.resizeLimiter.isAllowed()) {
      this.log("RESIZE rate limit exceeded — message dropped.", "warn");
      return this;
    }

    this.postToHost(buildMessage("RESIZE", { height }));
    return this;
  }

  /**
   * Send a user interaction event to the platform's analytics pipeline.
   * Appears in the developer analytics dashboard.
   * Rate limited to 30 calls per minute.
   *
   * @param eventName  - Snake_case event name (e.g. "meal_plan_viewed")
   * @param properties - Optional flat key-value properties
   */
  track(
    eventName:  string,
    properties?: Record<string, string | number | boolean>
  ): this {
    this.assertInitReceived("track");

    if (!this.trackEventLimiter.isAllowed()) {
      this.log(`TRACK_EVENT rate limit exceeded — "${eventName}" dropped.`, "warn");
      return this;
    }

    if (RESERVED_EVENT_NAMES.has(eventName)) {
      this.log(`"${eventName}" is a reserved event name — dropped.`, "warn");
      return this;
    }

    if (!/^[a-z][a-z0-9_]{1,49}$/.test(eventName)) {
      this.log(`Invalid event name "${eventName}" — must match ^[a-z][a-z0-9_]{1,49}$.`, "warn");
      return this;
    }

    this.postToHost(buildMessage("TRACK_EVENT", { event_name: eventName, properties }));
    return this;
  }

  /**
   * Initiate a payment through the platform's payment rails.
   * The platform overlays a native payment sheet — your app stays in the background.
   * Returns a Promise that resolves with the payment result.
   *
   * Only one payment can be in-flight at a time.
   * Amount must match your app manifest price within 2% tolerance.
   *
   * @param opts - Payment options (plan_id, amount in paise, billing_cycle, description)
   */
  requestPayment(opts: RequestPaymentPayload): Promise<PaymentResultPayload> {
    this.assertInitReceived("requestPayment");

    if (this.paymentInFlight) {
      return Promise.reject(new Error(
        "A payment is already in progress. Wait for it to complete before requesting another."
      ));
    }

    this.paymentInFlight = true;
    this.postToHost(buildMessage("REQUEST_PAYMENT", opts));
    this.log(`REQUEST_PAYMENT sent (plan: ${opts.plan_id}, amount: ${opts.amount})`);

    // Return a Promise that resolves when PAYMENT_RESULT is received
    return new Promise((resolve) => {
      this.pendingPaymentResolve = resolve;
    });
  }

  /**
   * Request a new auth token from the platform before the current one expires.
   * You should call this at the 13-minute mark (token TTL is 15 minutes).
   *
   * The SDK handles this automatically if you use startAutoTokenRefresh().
   * Call this manually only if you need finer control.
   */
  refreshToken(): Promise<TokenRefreshPayload> {
    this.assertInitReceived("refreshToken");
    this.postToHost(buildMessage("TOKEN_REFRESH_REQUEST", {}));
    this.log("TOKEN_REFRESH_REQUEST sent");

    return new Promise((resolve) => {
      this.pendingTokenRefreshResolve = resolve;
    });
  }

  /**
   * Ask the platform to navigate to a different step.
   * Use sparingly — typically only for "Back to dashboard" type flows.
   */
  navigate(destination: NavigationDestination): this {
    this.assertInitReceived("navigate");
    this.postToHost(buildMessage("NAVIGATE", { destination }));
    this.log(`NAVIGATE sent → ${destination}`);
    return this;
  }

  /**
   * Close the app session. Always call this when the user is done
   * or when responding to onCloseRequest.
   *
   * @param reason   - "completed" | "dismissed" | "error"
   * @param outcome  - Optional outcome data for analytics + health graph update
   */
  close(reason: CloseReason, outcome?: ClosePayload["outcome"]): void {
    const payload: ClosePayload = { reason, outcome };
    this.postToHost(buildMessage("CLOSE", payload));
    this.log(`CLOSE sent (reason: ${reason})`);
    this.destroy();
  }

  /**
   * Report an unrecoverable error to the platform.
   * If fatal=true, the platform closes the container.
   */
  reportError(code: AppErrorCode, message: string, fatal = false): void {
    const payload: ErrorPayload = { code, message, fatal };
    this.postToHost(buildMessage("ERROR", payload));
    this.log(`ERROR sent (code: ${code}, fatal: ${fatal})`, "error");
    if (fatal) this.destroy();
  }

  /**
   * Register a callback for when the platform requests the app to close.
   * You MUST call sdk.close() within 3 seconds of this callback firing,
   * or the platform will force-destroy the iFrame.
   */
  onCloseRequest(callback: (payload: CloseRequestPayload) => void): this {
    this.closeRequestCallback = callback;
    return this;
  }

  /**
   * Register a callback for when the user changes the platform theme.
   * Use to apply light/dark mode inside your app.
   */
  onThemeChange(callback: (payload: ThemeChangePayload) => void): this {
    this.themeChangeCallback = callback;
    return this;
  }

  /**
   * Fetch the user's full health graph from the HealthFirst API.
   * Uses the auth_token from INIT. Returns only consented fields.
   *
   * @param authToken - The auth_token received in onInit callback
   */
  async getHealthGraph(authToken: string): Promise<HealthGraphResponse> {
    this.assertInitReceived("getHealthGraph");
    return fetchHealthGraph(
      this.userContext!.user_id,
      authToken,
      this.sessionId!,
      this.platform!.env
    );
  }

  /**
   * Returns the current user context (from INIT).
   * Returns undefined if INIT has not been received yet.
   */
  getUserContext(): UserContext | undefined {
    return this.userContext;
  }

  /**
   * Returns the current platform context (from INIT).
   */
  getPlatformContext(): PlatformContext | undefined {
    return this.platform;
  }

  /**
   * Returns the current design tokens injected by the platform.
   * Useful for imperative rendering contexts (canvas, chart libraries, inline styles)
   * where CSS custom properties can't be used directly.
   * Returns undefined if the platform hasn't sent tokens yet.
   */
  getDesignTokens(): DesignTokens | undefined {
    return this.currentTokens;
  }

  // ─── Internal: message handling ───────────────────────────────────────────

  private async handleMessage(event: MessageEvent): Promise<void> {
    // Validate origin + namespace + version
    if (!isValidHostMessage(event, this.hostOrigin)) return;

    const msg = event.data;
    this.log(`Received: ${msg.type}`);

    switch (msg.type) {
      case "INIT":
        await this.handleInit(msg.payload as InitPayload);
        break;

      case "TOKEN_REFRESH":
        this.handleTokenRefresh(msg.payload as TokenRefreshPayload);
        break;

      case "PAYMENT_RESULT":
        this.handlePaymentResult(msg.payload as PaymentResultPayload);
        break;

      case "CLOSE_REQUEST":
        this.handleCloseRequest(msg.payload as CloseRequestPayload);
        break;

      case "THEME_CHANGE":
        this.handleThemeChange(msg.payload as ThemeChangePayload);
        break;
    }
  }

  private async handleInit(payload: InitPayload): Promise<void> {
    // Guard: only process INIT once per session
    if (this.sessionId) {
      this.log("Duplicate INIT received — ignored.", "warn");
      return;
    }

    this.sessionId   = payload.session_id;
    this.authToken   = payload.auth_token;
    this.userContext = payload.user_context;
    this.platform    = payload.platform;
    this.appInfo     = payload.app;

    // Apply design tokens from platform if provided
    if (payload.platform.tokens) {
      this.applyTokens(payload.platform.tokens, payload.platform.theme);
    }

    // Calculate token expiry from JWT exp claim
    this.tokenExpiry = parseTokenExpiry(payload.auth_token);

    // Schedule automatic token refresh
    this.scheduleTokenRefresh();

    this.log(`INIT received (session: ${this.sessionId}, user: ${this.userContext.user_id})`);

    // Call developer's callback if registered
    if (this.initCallback) {
      try {
        await this.initCallback({
          user:       payload.user_context,
          auth_token: payload.auth_token,
          session_id: payload.session_id,
          platform:   payload.platform,
          app:        payload.app,
        });
      } catch (err) {
        this.log(`onInit callback threw an error: ${err}`, "error");
        this.reportError("INIT_FAILED", String(err), false);
      }
    }
  }

  private handleTokenRefresh(payload: TokenRefreshPayload): void {
    this.authToken   = payload.auth_token;
    this.tokenExpiry = payload.expires_at * 1000;

    // Schedule next refresh
    this.scheduleTokenRefresh();

    this.log(`Token refreshed (expires: ${new Date(this.tokenExpiry).toISOString()})`);

    // Resolve any pending manual refresh Promise
    if (this.pendingTokenRefreshResolve) {
      this.pendingTokenRefreshResolve(payload);
      this.pendingTokenRefreshResolve = undefined;
    }
  }

  private handlePaymentResult(payload: PaymentResultPayload): void {
    this.paymentInFlight = false;
    this.log(`PAYMENT_RESULT received (success: ${payload.success})`);

    if (this.pendingPaymentResolve) {
      this.pendingPaymentResolve(payload);
      this.pendingPaymentResolve = undefined;
    }
  }

  private handleCloseRequest(payload: CloseRequestPayload): void {
    this.log(`CLOSE_REQUEST received (reason: ${payload.reason})`);

    if (this.closeRequestCallback) {
      this.closeRequestCallback(payload);
      // Developer must call sdk.close() within 3 seconds
    } else {
      // No handler registered — auto-close gracefully
      this.close("dismissed");
    }
  }

  private handleThemeChange(payload: ThemeChangePayload): void {
    this.log(`THEME_CHANGE received (theme: ${payload.theme})`);
    if (payload.tokens) {
      this.applyTokens(payload.tokens, payload.theme);
    } else {
      // No token bundle — at minimum flip the data attribute so CSS selectors work
      document.documentElement.setAttribute("data-hf-theme", payload.theme);
    }
    if (this.themeChangeCallback) {
      this.themeChangeCallback(payload);
    }
  }

  // ─── Internal: design tokens ──────────────────────────────────────────────

  /**
   * Writes DesignTokens as CSS custom properties on :root and sets
   * the data-hf-theme attribute so developers can use both approaches:
   *
   *   CSS vars:       color: var(--hf-color-primary)
   *   Attribute sel:  [data-hf-theme="dark"] { ... }
   */
  private applyTokens(tokens: DesignTokens, theme: string): void {
    this.currentTokens = tokens;

    const root = document.documentElement;

    // Theme attribute — lets devs use [data-hf-theme="dark"] selectors
    root.setAttribute("data-hf-theme", theme);

    // Color tokens
    root.style.setProperty("--hf-color-primary",    tokens.color.primary);
    root.style.setProperty("--hf-color-surface",    tokens.color.surface);
    root.style.setProperty("--hf-color-background", tokens.color.background);
    root.style.setProperty("--hf-color-text",       tokens.color.text);
    root.style.setProperty("--hf-color-muted",      tokens.color.muted);
    root.style.setProperty("--hf-color-error",      tokens.color.error);
    root.style.setProperty("--hf-color-success",    tokens.color.success);

    // Typography
    root.style.setProperty("--hf-font-family",   tokens.typography.fontFamily);
    root.style.setProperty("--hf-font-scale-base", `${tokens.typography.scaleBase}px`);

    // Border radius
    root.style.setProperty("--hf-radius-sm", tokens.radius.sm);
    root.style.setProperty("--hf-radius-md", tokens.radius.md);
    root.style.setProperty("--hf-radius-lg", tokens.radius.lg);

    // Spacing
    root.style.setProperty("--hf-spacing-unit", `${tokens.spacing.unit}px`);

    this.log(`Design tokens applied (theme: ${theme})`);
  }

  // ─── Internal: token refresh scheduling ──────────────────────────────────

  /**
   * Schedules TOKEN_REFRESH_REQUEST to be sent automatically
   * 2 minutes before the current token expires.
   */
  private scheduleTokenRefresh(): void {
    if (this.tokenRefreshTimer) {
      clearTimeout(this.tokenRefreshTimer);
    }

    if (!this.tokenExpiry) return;

    const msUntilExpiry = this.tokenExpiry - Date.now();
    const refreshIn     = msUntilExpiry - TOKEN_REFRESH_BEFORE_EXPIRY_MS;

    if (refreshIn <= 0) {
      // Token already expired or about to — refresh immediately
      this.refreshToken().catch(() => {});
      return;
    }

    this.tokenRefreshTimer = setTimeout(() => {
      this.log("Auto-refreshing token...");
      this.refreshToken().catch(() => {});
    }, refreshIn);
  }

  // ─── Internal: utilities ──────────────────────────────────────────────────

  private postToHost(message: object): void {
    window.parent.postMessage(message, this.hostOrigin);
  }

  private assertInitReceived(methodName: string): void {
    if (!this.sessionId) {
      throw new Error(
        `sdk.${methodName}() called before INIT was received. ` +
        `Make sure to call this inside your sdk.onInit() callback.`
      );
    }
  }

  private log(msg: string, level: "log" | "warn" | "error" = "log"): void {
    if (!this.debug) return;
    const prefix = "[HealthFirst SDK]";
    console[level](`${prefix} ${msg}`);
  }

  /**
   * Remove event listeners and clear timers.
   * Called automatically after sdk.close() or a fatal error.
   */
  private destroy(): void {
    window.removeEventListener("message", this.messageListener);
    if (this.tokenRefreshTimer) {
      clearTimeout(this.tokenRefreshTimer);
    }
    this.log("SDK destroyed.");
  }
}

// ─── InitContext ──────────────────────────────────────────────────────────────

/**
 * The argument passed to the onInit callback.
 * Everything your app needs to start rendering.
 */
export interface InitContext {
  /** User's health context — only consented fields present */
  user:       UserContext;
  /** Short-lived JWT for Health Graph API — expires in 15 minutes */
  auth_token: string;
  /** Unique session ID */
  session_id: string;
  /** Platform theme, locale, currency, environment */
  platform:   PlatformContext;
  /** Your app's ID, name, and approved manifest version */
  app:        AppInfo;
}

// ─── Helper: parse JWT expiry ─────────────────────────────────────────────────

function parseTokenExpiry(jwt: string): number | undefined {
  try {
    const parts   = jwt.split(".");
    const payload = JSON.parse(atob(parts[1]));
    return payload.exp ? payload.exp * 1000 : undefined;
  } catch {
    return undefined;
  }
}
