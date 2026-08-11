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
export declare class WebCodecsAudioPlayer {
    #private;
    private readonly onStatistics;
    constructor(onStatistics?: AudioStatisticsListener);
    get supported(): boolean;
    run(session: ScrcpyV41Session): Promise<void>;
    setMuted(value: boolean): void;
    setVolume(value: number): void;
    resume(): Promise<void>;
    stop(): void;
    private play;
    private applyGain;
    private emitStatistics;
}
