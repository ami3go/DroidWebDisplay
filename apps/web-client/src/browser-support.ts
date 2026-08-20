export interface BrowserCapabilityReport {
  readonly supported: boolean;
  readonly missing: readonly string[];
  readonly userAgent: string;
  readonly browserName: string;
  readonly platform: string;
  readonly hardwareConcurrency: number | null;
  readonly audioSupported: boolean;
  readonly missingAudio: readonly string[];
}

export interface BrowserCapabilityScope {
  readonly WebSocket?: unknown;
  readonly ReadableStream?: unknown;
  readonly WritableStream?: unknown;
  readonly VideoDecoder?: unknown;
  readonly EncodedVideoChunk?: unknown;
  readonly AudioDecoder?: unknown;
  readonly EncodedAudioChunk?: unknown;
  readonly AudioContext?: unknown;
  readonly navigator?: {
    readonly userAgent?: string;
    readonly platform?: string;
    readonly hardwareConcurrency?: number;
  };
}

export function browserName(userAgent: string): string {
  const matchers: readonly [RegExp, string][] = [
    [/Edg\/([0-9.]+)/, "Edge"],
    [/Chrome\/([0-9.]+)/, "Chrome"],
    [/Firefox\/([0-9.]+)/, "Firefox"],
    [/Version\/([0-9.]+).*Safari\//, "Safari"],
  ];
  for (const [pattern, name] of matchers) {
    const match = pattern.exec(userAgent);
    if (match) return `${name} ${match[1]}`;
  }
  return userAgent === "unknown" ? "unknown" : "Other browser";
}

export function inspectBrowserCapabilities(scope: BrowserCapabilityScope = globalThis): BrowserCapabilityReport {
  const required = ["WebSocket", "ReadableStream", "WritableStream", "VideoDecoder", "EncodedVideoChunk"] as const;
  const missing = required.filter((name) => typeof scope[name] === "undefined");
  const audio = ["AudioDecoder", "EncodedAudioChunk", "AudioContext"] as const;
  const missingAudio = audio.filter((name) => typeof scope[name] === "undefined");
  const userAgent = scope.navigator?.userAgent ?? "unknown";
  const concurrency = scope.navigator?.hardwareConcurrency;
  return {
    supported: missing.length === 0,
    missing,
    userAgent,
    browserName: browserName(userAgent),
    platform: scope.navigator?.platform || "unknown",
    hardwareConcurrency: typeof concurrency === "number" && Number.isFinite(concurrency) ? concurrency : null,
    audioSupported: missingAudio.length === 0,
    missingAudio,
  };
}
