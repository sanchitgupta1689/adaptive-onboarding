// ─── Protocol constants ───────────────────────────────────────────────────────

export const PROTOCOL_NAMESPACE = "HEALTHFIRST_EMBED" as const;
export const PROTOCOL_VERSION   = "1.0" as const;

// ─── Enums ────────────────────────────────────────────────────────────────────

export type HealthGoal =
  | "weight_loss"
  | "muscle_gain"
  | "better_sleep"
  | "more_energy"
  | "immunity"
  | "gut_health"
  | "stress_relief";

export type Persona =
  | "busy_professional"
  | "performance_athlete"
  | "chronic_condition"
  | "weight_loss_seeker"
  | "wellness_explorer";

export type HealthMaturity = "new" | "aware" | "committed" | "expert";

export type ActivityLevel =
  | "sedentary"
  | "lightly_active"
  | "moderate"
  | "very_active";

export type DietType =
  | "vegan"
  | "vegetarian"
  | "keto"
  | "paleo"
  | "no_preference";

export type BudgetRange = "value" | "mid" | "premium";

export type AgeRange = "18-24" | "25-34" | "35-44" | "45-54" | "55+";

export type Theme = "light" | "dark";

export type Environment = "production" | "sandbox";

export type BillingCycle = "one_time" | "monthly" | "quarterly" | "annual";

export type NavigationDestination =
  | "health_goals"
  | "health_profile"
  | "product_match"
  | "dashboard"
  | "back";

export type CloseReason = "completed" | "dismissed" | "error";

export type AppErrorCode =
  | "INIT_FAILED"
  | "HEALTH_GRAPH_UNAVAILABLE"
  | "RENDER_FAILED"
  | "UNEXPECTED_ERROR";

export type PaymentFailureCode =
  | "USER_CANCELLED"
  | "INSUFFICIENT_FUNDS"
  | "PAYMENT_GATEWAY_ERROR"
  | "SESSION_EXPIRED"
  | "DUPLICATE_REQUEST";

// ─── User Context ─────────────────────────────────────────────────────────────

/**
 * The user's health context injected by the platform on INIT.
 * Only fields the user consented to share are present.
 * All fields are optional — always check before accessing.
 */
export interface UserContext {
  /** HealthFirst platform user ID. Stable identifier — use as your user key. */
  user_id: string;

  // Explicitly declared by user
  goals?:          HealthGoal[];
  age_range?:      AgeRange;
  activity_level?: ActivityLevel;
  diet_type?:      DietType;
  conditions?:     string[];
  budget_range?:   BudgetRange;

  // Derived signals (available only with explicit user consent)
  persona?:         Persona;
  health_maturity?: HealthMaturity;
}

// ─── Platform Context ─────────────────────────────────────────────────────────

// ─── Design Tokens ────────────────────────────────────────────────────────────

/**
 * Platform design tokens injected by HealthFirst on INIT and updated on THEME_CHANGE.
 * The SDK writes these as CSS custom properties on :root automatically.
 *
 * Use in your CSS:
 *   background: var(--hf-color-surface);
 *   border-radius: var(--hf-radius-md);
 *   font-family: var(--hf-font-family);
 */
export interface DesignTokens {
  color: {
    /** Brand primary — use for CTAs, links, active states */
    primary:    string;
    /** Card / elevated surface background */
    surface:    string;
    /** Page / container background */
    background: string;
    /** Body text */
    text:       string;
    /** Secondary / placeholder text */
    muted:      string;
    /** Destructive actions, error states */
    error:      string;
    /** Positive confirmation, success states */
    success:    string;
  };
  typography: {
    /** Full font-family stack, e.g. "Inter, sans-serif" */
    fontFamily: string;
    /** Base font size in px — all rem values scale from this */
    scaleBase:  number;
  };
  radius: {
    sm: string;   // e.g. "6px"  — inputs, chips
    md: string;   // e.g. "12px" — cards
    lg: string;   // e.g. "20px" — sheets, modals
  };
  spacing: {
    /** Base spacing unit in px. All spacing = multiples of this. */
    unit: number;  // e.g. 4
  };
}

// ─── Platform Context ─────────────────────────────────────────────────────────

export interface PlatformContext {
  env:      Environment;
  locale:   string;
  currency: string;
  theme:    Theme;
  /** Design tokens — present when platform supports token injection (v1.1+) */
  tokens?:  DesignTokens;
}

// ─── App Info ─────────────────────────────────────────────────────────────────

export interface AppInfo {
  app_id:  string;
  name:    string;
  version: string;
}

// ─── Message Types ────────────────────────────────────────────────────────────

/** All message type identifiers — Platform → Guest */
export type HostMessageType =
  | "INIT"
  | "TOKEN_REFRESH"
  | "PAYMENT_RESULT"
  | "CLOSE_REQUEST"
  | "THEME_CHANGE";

/** All message type identifiers — Guest → Platform */
export type GuestMessageType =
  | "APP_READY"
  | "RESIZE"
  | "TRACK_EVENT"
  | "REQUEST_PAYMENT"
  | "TOKEN_REFRESH_REQUEST"
  | "NAVIGATE"
  | "CLOSE"
  | "ERROR";

export type MessageType = HostMessageType | GuestMessageType;

// ─── Message Envelope ─────────────────────────────────────────────────────────

/**
 * Every postMessage in both directions uses this envelope.
 * Messages not matching this shape must be silently ignored.
 */
export interface MessageEnvelope<T extends MessageType, P extends object> {
  namespace:  typeof PROTOCOL_NAMESPACE;
  version:    string;
  message_id: string;
  type:       T;
  payload:    P;
  sent_at:    number;
  signature?: string;   // Present on Host → Guest messages only
}

// ─── Host → Guest Payloads ────────────────────────────────────────────────────

export interface InitPayload {
  session_id:       string;
  auth_token:       string;
  user_context:     UserContext;
  platform:         PlatformContext;
  app:              AppInfo;
}

export interface TokenRefreshPayload {
  auth_token:  string;
  expires_at:  number;
}

export interface PaymentResultPayload {
  request_id:    string;
  success:       boolean;
  transaction?:  {
    transaction_id: string;
    amount:         number;
    currency:       string;
    plan_id:        string;
    charged_at:     number;
  };
  failure?: {
    code:    PaymentFailureCode;
    message: string;
  };
}

export interface CloseRequestPayload {
  reason: "user_dismissed" | "session_timeout" | "platform_close";
}

export interface ThemeChangePayload {
  theme:    Theme;
  /** Updated design tokens for the new theme — apply with sdk.applyTokens() */
  tokens?: DesignTokens;
}

// ─── Guest → Host Payloads ────────────────────────────────────────────────────

export interface AppReadyPayload {
  initial_height: number;
}

export interface ResizePayload {
  height: number;
}

export interface TrackEventPayload {
  event_name:  string;
  properties?: Record<string, string | number | boolean>;
}

export interface RequestPaymentPayload {
  plan_id:       string;
  amount:        number;
  currency:      "INR";
  billing_cycle: BillingCycle;
  description:   string;
  trial?: {
    duration_days: number;
  };
}

export interface NavigatePayload {
  destination: NavigationDestination;
}

export interface ClosePayload {
  reason:   CloseReason;
  outcome?: {
    converted:       boolean;
    plan_selected?:  string;
    goal_achieved?:  string;
  };
}

export interface ErrorPayload {
  code:    AppErrorCode;
  message: string;
  fatal:   boolean;
}

// ─── Typed Message Aliases ────────────────────────────────────────────────────

// Host → Guest
export type InitMessage          = MessageEnvelope<"INIT", InitPayload>;
export type TokenRefreshMessage  = MessageEnvelope<"TOKEN_REFRESH", TokenRefreshPayload>;
export type PaymentResultMessage = MessageEnvelope<"PAYMENT_RESULT", PaymentResultPayload>;
export type CloseRequestMessage  = MessageEnvelope<"CLOSE_REQUEST", CloseRequestPayload>;
export type ThemeChangeMessage   = MessageEnvelope<"THEME_CHANGE", ThemeChangePayload>;

// Guest → Host
export type AppReadyMessage             = MessageEnvelope<"APP_READY", AppReadyPayload>;
export type ResizeMessage               = MessageEnvelope<"RESIZE", ResizePayload>;
export type TrackEventMessage           = MessageEnvelope<"TRACK_EVENT", TrackEventPayload>;
export type RequestPaymentMessage       = MessageEnvelope<"REQUEST_PAYMENT", RequestPaymentPayload>;
export type TokenRefreshRequestMessage  = MessageEnvelope<"TOKEN_REFRESH_REQUEST", object>;
export type NavigateMessage             = MessageEnvelope<"NAVIGATE", NavigatePayload>;
export type CloseMessage                = MessageEnvelope<"CLOSE", ClosePayload>;
export type ErrorMessage                = MessageEnvelope<"ERROR", ErrorPayload>;

// ─── SDK Options ──────────────────────────────────────────────────────────────

export interface SDKOptions {
  /**
   * Override the expected Host origin.
   * Default: "https://app.healthfirst.in"
   * Set to "https://sandbox.healthfirst.in" for sandbox testing.
   */
  hostOrigin?: string;

  /**
   * How long (ms) to wait for INIT message before timing out.
   * Default: 10000 (10 seconds)
   */
  initTimeout?: number;

  /**
   * Enable debug logging to console.
   * Default: false
   */
  debug?: boolean;
}

// ─── Health Graph API Types ───────────────────────────────────────────────────

/**
 * Response from GET /v1/users/{user_id}/health-graph
 * Only consented fields are returned — non-consented fields are absent.
 */
export interface HealthGraphResponse {
  user_id:          string;
  goals?:           HealthGoal[];
  age_range?:       AgeRange;
  activity_level?:  ActivityLevel;
  diet_type?:       DietType;
  conditions?:      string[];
  budget_range?:    BudgetRange;
  persona?:         Persona;
  health_maturity?: HealthMaturity;
}

export interface HealthGraphError {
  code:    "UNAUTHORIZED" | "FORBIDDEN" | "NOT_FOUND" | "RATE_LIMITED" | "SERVER_ERROR";
  message: string;
}
