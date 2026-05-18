export { HealthFirstSDK } from "./sdk";

export { fetchHealthGraph } from "./health-graph";

export {
  buildMessage,
  isValidHostMessage,
  isCompatibleVersion,
  isHostMessageType,
  verifySignature,
  RateLimiter,
} from "./messages";

export {
  PROTOCOL_NAMESPACE,
  PROTOCOL_VERSION,
} from "./types";

export type {
  // Enums / value types
  HealthGoal,
  Persona,
  HealthMaturity,
  ActivityLevel,
  DietType,
  BudgetRange,
  AgeRange,
  Theme,
  Environment,
  BillingCycle,
  NavigationDestination,
  CloseReason,
  AppErrorCode,
  PaymentFailureCode,

  // Context objects
  UserContext,
  PlatformContext,
  AppInfo,
  DesignTokens,

  // Message envelope + types
  MessageType,
  HostMessageType,
  GuestMessageType,
  MessageEnvelope,

  // Host → Guest payloads
  InitPayload,
  TokenRefreshPayload,
  PaymentResultPayload,
  CloseRequestPayload,
  ThemeChangePayload,

  // Guest → Host payloads
  AppReadyPayload,
  ResizePayload,
  TrackEventPayload,
  RequestPaymentPayload,
  NavigatePayload,
  ClosePayload,
  ErrorPayload,

  // Typed message aliases — Host → Guest
  InitMessage,
  TokenRefreshMessage,
  PaymentResultMessage,
  CloseRequestMessage,
  ThemeChangeMessage,

  // Typed message aliases — Guest → Host
  AppReadyMessage,
  ResizeMessage,
  TrackEventMessage,
  RequestPaymentMessage,
  TokenRefreshRequestMessage,
  NavigateMessage,
  CloseMessage,
  ErrorMessage,

  // SDK
  SDKOptions,

  // Health Graph API
  HealthGraphResponse,
  HealthGraphError,
} from "./types";
