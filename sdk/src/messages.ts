import {
  PROTOCOL_NAMESPACE,
  PROTOCOL_VERSION,
  MessageType,
  MessageEnvelope,
  GuestMessageType,
  HostMessageType,
} from "./types";

// ─── Message builder ──────────────────────────────────────────────────────────

/**
 * Builds a valid message envelope for Guest → Host messages.
 * Automatically fills namespace, version, message_id, and sent_at.
 */
export function buildMessage<T extends GuestMessageType, P extends object>(
  type: T,
  payload: P
): MessageEnvelope<T, P> {
  return {
    namespace:  PROTOCOL_NAMESPACE,
    version:    PROTOCOL_VERSION,
    message_id: generateId(),
    type,
    payload,
    sent_at:    Date.now(),
  };
}

// ─── Message validators ───────────────────────────────────────────────────────

/**
 * Returns true if the raw postMessage event looks like a HealthFirst protocol
 * message. Does NOT validate payload shape — caller must do that per type.
 *
 * Rules from spec Section 11:
 *   - event.origin must match the expected host origin
 *   - namespace must be HEALTHFIRST_EMBED
 *   - version must be present and compatible
 *   - type must be a known Host → Guest message type
 */
export function isValidHostMessage(
  event: MessageEvent,
  expectedOrigin: string
): event is MessageEvent & { data: MessageEnvelope<HostMessageType, object> } {
  if (event.origin !== expectedOrigin)             return false;
  if (typeof event.data !== "object")              return false;
  if (event.data?.namespace !== PROTOCOL_NAMESPACE) return false;
  if (!isCompatibleVersion(event.data?.version))  return false;
  if (!isHostMessageType(event.data?.type))        return false;
  return true;
}

/**
 * Checks whether the protocol version in the message is compatible
 * with this SDK version. Uses MAJOR version compatibility only.
 */
export function isCompatibleVersion(version: unknown): boolean {
  if (typeof version !== "string") return false;
  const incomingMajor = parseInt(version.split(".")[0], 10);
  const sdkMajor      = parseInt(PROTOCOL_VERSION.split(".")[0], 10);
  return incomingMajor === sdkMajor;
}

// ─── Type guards ──────────────────────────────────────────────────────────────

const HOST_MESSAGE_TYPES: HostMessageType[] = [
  "INIT",
  "TOKEN_REFRESH",
  "PAYMENT_RESULT",
  "CLOSE_REQUEST",
  "THEME_CHANGE",
];

export function isHostMessageType(type: unknown): type is HostMessageType {
  return HOST_MESSAGE_TYPES.includes(type as HostMessageType);
}

// ─── Signature verification ───────────────────────────────────────────────────

/**
 * Verifies the HMAC-SHA256 signature on a Host → Guest message.
 *
 * The signature covers: message_id + type + sent_at
 * Key: app's secret key (from developer portal)
 *
 * Uses the Web Crypto API (available in all modern browsers).
 * Returns true if signature is valid, false otherwise.
 *
 * In development/sandbox, secret_key may be omitted to skip verification.
 * NEVER skip verification in production.
 */
export async function verifySignature(
  message: MessageEnvelope<MessageType, object>,
  secretKey: string
): Promise<boolean> {
  if (!message.signature) return false;

  try {
    const data     = `${message.message_id}${message.type}${message.sent_at}`;
    const encoder  = new TextEncoder();
    const keyData  = encoder.encode(secretKey);
    const msgData  = encoder.encode(data);

    const cryptoKey = await crypto.subtle.importKey(
      "raw", keyData,
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    );

    const sigBytes = hexToBytes(message.signature);
    return await crypto.subtle.verify("HMAC", cryptoKey, sigBytes, msgData);
  } catch {
    return false;
  }
}

// ─── Rate limiter ─────────────────────────────────────────────────────────────

/**
 * Simple token bucket rate limiter used for RESIZE and TRACK_EVENT.
 * maxCount messages allowed per windowMs milliseconds.
 */
export class RateLimiter {
  private timestamps: number[] = [];

  constructor(
    private maxCount:  number,
    private windowMs:  number
  ) {}

  isAllowed(): boolean {
    const now    = Date.now();
    const cutoff = now - this.windowMs;

    // Remove timestamps outside the window
    this.timestamps = this.timestamps.filter(t => t > cutoff);

    if (this.timestamps.length >= this.maxCount) return false;

    this.timestamps.push(now);
    return true;
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateId(): string {
  // Use crypto.randomUUID if available, fallback for older environments
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}
