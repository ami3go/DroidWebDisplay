import type { ScrcpyV41Session } from "@gpt-bridge/scrcpy-protocol";

export interface AudioStatistics {
  readonly codec: string;
  readonly packetsDecoded: number;
  readonly framesPlayed: number;
  readonly decoderQueue: number;
  readonly bufferedMilliseconds: number;
  readonly muted: boolean;
  readonly volume: number;
}

export type AudioStatisticsListener = (statistics: AudioStatistics) => void;

export class WebCodecsAudioPlayer {
  #decoder: AudioDecoder | null = null;
  #context: AudioContext | null = null;
  #gain: GainNode | null = null;
  #stopped = false;
  #nextStartTime = 0;
  #packetsDecoded = 0;
  #framesPlayed = 0;
  #codec = "disabled";
  #muted = false;
  #volume = 1;

  public constructor(private readonly onStatistics: AudioStatisticsListener = () => undefined) {}

  public get supported(): boolean {
    return typeof AudioDecoder !== "undefined" && typeof EncodedAudioChunk !== "undefined" && typeof AudioContext !== "undefined";
  }

  public async run(session: ScrcpyV41Session): Promise<void> {
    const header = session.audioHeader;
    if (!header) throw new Error("Android audio capture is unavailable for this session");
    if (!this.supported) throw new Error("This browser does not provide WebCodecs audio decoding");
    if (header.codec !== "opus") throw new Error(`Browser audio currently supports Opus; Android selected ${header.codec}`);

    this.#codec = header.codec;
    this.#stopped = false;
    this.#context = new AudioContext({ latencyHint: "interactive", sampleRate: 48_000 });
    this.#gain = this.#context.createGain();
    this.#gain.connect(this.#context.destination);
    this.applyGain();
    await this.#context.resume();

    const config: AudioDecoderConfig = { codec: "opus", sampleRate: 48_000, numberOfChannels: 2 };
    const support = await AudioDecoder.isConfigSupported(config);
    if (!support.supported) throw new Error("This browser cannot decode the Opus stream produced by scrcpy");
    this.#decoder = new AudioDecoder({
      output: (data) => this.play(data),
      error: (error) => console.warn("AudioDecoder error", error),
    });
    this.#decoder.configure(support.config ?? config);

    while (!this.#stopped) {
      const packet = await session.readAudioPacket();
      if (packet.configuration || packet.data.byteLength === 0) continue;
      const timestamp = packet.pts === null ? this.#packetsDecoded * 20_000 : Number(packet.pts);
      this.#decoder.decode(new EncodedAudioChunk({ type: "key", timestamp, data: packet.data }));
      this.#packetsDecoded += 1;
      this.emitStatistics();
    }
  }

  public setMuted(value: boolean): void {
    this.#muted = value;
    this.applyGain();
    this.emitStatistics();
  }

  public setVolume(value: number): void {
    this.#volume = Math.max(0, Math.min(1, value));
    this.applyGain();
    this.emitStatistics();
  }

  public async resume(): Promise<void> {
    await this.#context?.resume();
  }

  public stop(): void {
    this.#stopped = true;
    if (this.#decoder && this.#decoder.state !== "closed") this.#decoder.close();
    this.#decoder = null;
    const context = this.#context;
    this.#context = null;
    this.#gain = null;
    this.#nextStartTime = 0;
    if (context && context.state !== "closed") void context.close();
    this.emitStatistics();
  }

  private play(data: AudioData): void {
    try {
      const context = this.#context;
      const gain = this.#gain;
      if (!context || !gain || this.#stopped) return;
      const channels = data.numberOfChannels;
      const buffer = context.createBuffer(channels, data.numberOfFrames, data.sampleRate);
      for (let channel = 0; channel < channels; channel += 1) {
        const samples = new Float32Array(data.numberOfFrames);
        data.copyTo(samples, { planeIndex: channel, format: "f32-planar" });
        buffer.copyToChannel(samples, channel);
      }
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(gain);
      const now = context.currentTime;
      if (this.#nextStartTime < now || this.#nextStartTime - now > 0.25) this.#nextStartTime = now + 0.02;
      source.start(this.#nextStartTime);
      this.#nextStartTime += buffer.duration;
      this.#framesPlayed += data.numberOfFrames;
      this.emitStatistics();
    } finally {
      data.close();
    }
  }

  private applyGain(): void {
    if (this.#gain) this.#gain.gain.value = this.#muted ? 0 : this.#volume;
  }

  private emitStatistics(): void {
    const now = this.#context?.currentTime ?? 0;
    this.onStatistics({
      codec: this.#codec,
      packetsDecoded: this.#packetsDecoded,
      framesPlayed: this.#framesPlayed,
      decoderQueue: this.#decoder?.decodeQueueSize ?? 0,
      bufferedMilliseconds: Math.max(0, Math.round((this.#nextStartTime - now) * 1000)),
      muted: this.#muted,
      volume: this.#volume,
    });
  }
}
