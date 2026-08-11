export interface BrowserCapabilityReport {
  readonly supported: boolean;
  readonly missing: readonly string[];
  readonly userAgent: string;
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
  readonly navigator?: { readonly userAgent?: string };
}

export function inspectBrowserCapabilities(scope: BrowserCapabilityScope = globalThis): BrowserCapabilityReport {
  const required = ["WebSocket", "ReadableStream", "WritableStream", "VideoDecoder", "EncodedVideoChunk"] as const;
  const missing = required.filter((name) => typeof scope[name] === "undefined");
  const audio = ["AudioDecoder", "EncodedAudioChunk", "AudioContext"] as const;
  const missingAudio = audio.filter((name) => typeof scope[name] === "undefined");
  return {
    supported: missing.length === 0,
    missing,
    userAgent: scope.navigator?.userAgent ?? "unknown",
    audioSupported: missingAudio.length === 0,
    missingAudio,
  };
}
