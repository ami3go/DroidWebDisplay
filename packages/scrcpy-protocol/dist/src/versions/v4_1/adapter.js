import { AsyncByteReader } from "../../common/async-byte-reader.js";
import { InvalidProtocolValueError, StreamDisabledError, VersionMismatchError } from "../../common/errors.js";
import { ADAPTER_ID, SCRCPY_VERSION } from "./constants.js";
import { ControlMessageType, serializeControlMessage } from "./control.js";
import { DeviceMessageParser } from "./device.js";
import { readDeviceInfo, readDummyByte } from "./handshake.js";
import { ScrcpyMediaStreamParser } from "./media.js";
const TOUCH_MOVE_ACTION = 2;
const TOUCH_MOVE_INTERVAL_MS = 8;
function metrics() {
    const root = globalThis;
    return root.__dwdLatencyMetrics ??= {};
}
function monotonicNow() {
    return globalThis.performance?.now?.() ?? Date.now();
}
function isTouchMove(message) {
    return message.type === ControlMessageType.InjectTouchEvent && message.action === TOUCH_MOVE_ACTION;
}
class LowLatencyControlScheduler {
    writer;
    #pendingMoves = new Map();
    #moveTimer = null;
    #moveSequence = 0;
    #tail = Promise.resolve();
    #closed = false;
    constructor(writer) {
        this.writer = writer;
    }
    send(message) {
        if (this.#closed)
            return Promise.reject(new Error("control scheduler is closed"));
        if (isTouchMove(message)) {
            const current = metrics();
            if (this.#pendingMoves.has(message.pointerId)) {
                current.controlMovesCoalesced = Number(current.controlMovesCoalesced ?? 0) + 1;
            }
            this.#moveSequence += 1;
            this.#pendingMoves.set(message.pointerId, { message, sequence: this.#moveSequence });
            current.controlPendingMovePointers = this.#pendingMoves.size;
            this.scheduleMoves();
            // Pointer MOVE handlers never wait behind stale MOVE traffic. The newest
            // position is retained independently for each active pointer and written
            // at most once per ~8 ms.
            return Promise.resolve();
        }
        // DOWN/UP/CANCEL, keys, clipboard and other controls are ordering barriers.
        // Flush the newest MOVE for every pointer first so Android observes each
        // pointer's final position without receiving the intermediate backlog.
        this.flushPendingMoves();
        return this.enqueue(message);
    }
    async close() {
        if (this.#closed)
            return;
        if (this.#moveTimer !== null) {
            clearTimeout(this.#moveTimer);
            this.#moveTimer = null;
        }
        this.flushPendingMoves();
        this.#closed = true;
        await this.#tail;
        metrics().controlPendingMovePointers = 0;
    }
    scheduleMoves() {
        if (this.#moveTimer !== null)
            return;
        this.#moveTimer = setTimeout(() => {
            this.#moveTimer = null;
            if (this.#closed)
                return;
            this.flushPendingMoves();
        }, TOUCH_MOVE_INTERVAL_MS);
    }
    takePendingMoves() {
        const moves = [...this.#pendingMoves.values()]
            .sort((left, right) => left.sequence - right.sequence)
            .map((item) => item.message);
        this.#pendingMoves.clear();
        metrics().controlPendingMovePointers = 0;
        return moves;
    }
    flushPendingMoves() {
        if (this.#moveTimer !== null) {
            clearTimeout(this.#moveTimer);
            this.#moveTimer = null;
        }
        for (const move of this.takePendingMoves()) {
            void this.enqueue(move).catch((error) => {
                metrics().controlLastError = error instanceof Error ? error.message : String(error);
            });
        }
    }
    enqueue(message) {
        const current = metrics();
        current.controlPendingWrites = Number(current.controlPendingWrites ?? 0) + 1;
        const queuedAt = monotonicNow();
        const write = this.#tail.then(async () => {
            const startedAt = monotonicNow();
            current.controlQueueDelayMs = Math.max(0, startedAt - queuedAt);
            await this.writer.write(serializeControlMessage(message));
            current.controlLastWriteMs = Math.max(0, monotonicNow() - startedAt);
            current.controlMessagesSent = Number(current.controlMessagesSent ?? 0) + 1;
        });
        this.#tail = write.catch(() => undefined);
        return write.finally(() => {
            current.controlPendingWrites = Math.max(0, Number(current.controlPendingWrites ?? 1) - 1);
        });
    }
}
export class ScrcpyV41Adapter {
    adapterId = ADAPTER_ID;
    scrcpyVersion = SCRCPY_VERSION;
    validateServer(serverInfo) {
        if (serverInfo.scrcpyVersion !== SCRCPY_VERSION) {
            return { compatible: false, reason: `expected scrcpy ${SCRCPY_VERSION}, got ${serverInfo.scrcpyVersion}` };
        }
        if (serverInfo.adapterId !== ADAPTER_ID) {
            return { compatible: false, reason: `expected adapter ${ADAPTER_ID}, got ${serverInfo.adapterId}` };
        }
        return { compatible: true };
    }
    async connect(transport, options) {
        if (!options.video && !options.audio && !options.control) {
            throw new InvalidProtocolValueError("at least one scrcpy channel must be enabled");
        }
        const videoStream = options.video ? await transport.openVideoChannel() : null;
        const audioStream = options.audio ? await transport.openAudioChannel() : null;
        const controlPair = options.control ? await transport.openControlChannel() : null;
        const firstReader = videoStream
            ? new AsyncByteReader(videoStream, { label: "scrcpy video" })
            : audioStream
                ? new AsyncByteReader(audioStream, { label: "scrcpy audio" })
                : controlPair
                    ? new AsyncByteReader(controlPair.readable, { label: "scrcpy control" })
                    : null;
        if (!firstReader) {
            throw new VersionMismatchError("unable to select first scrcpy channel");
        }
        if (options.expectDummyByte ?? true) {
            await readDummyByte(firstReader);
        }
        const device = (options.expectDeviceMeta ?? true) ? await readDeviceInfo(firstReader) : null;
        const videoReader = videoStream ? firstReader : null;
        const audioReader = audioStream
            ? (videoStream ? new AsyncByteReader(audioStream, { label: "scrcpy audio" }) : firstReader)
            : null;
        const controlReader = controlPair
            ? (videoStream || audioStream ? new AsyncByteReader(controlPair.readable, { label: "scrcpy control" }) : firstReader)
            : null;
        const videoParser = videoReader
            ? new ScrcpyMediaStreamParser(videoReader, { kind: "video", expectStreamMeta: options.expectStreamMeta ?? true })
            : null;
        let audioParser = audioReader
            ? new ScrcpyMediaStreamParser(audioReader, { kind: "audio", expectStreamMeta: options.expectStreamMeta ?? true })
            : null;
        const deviceParser = controlReader ? new DeviceMessageParser(controlReader) : null;
        const controlWriter = controlPair?.writable.getWriter() ?? null;
        const controlScheduler = controlWriter ? new LowLatencyControlScheduler(controlWriter) : null;
        const videoHeader = videoParser ? await videoParser.readHeader() : null;
        let audioHeader = null;
        if (audioParser) {
            try {
                audioHeader = await audioParser.readHeader();
            }
            catch (error) {
                if (error instanceof StreamDisabledError) {
                    // Audio is optional. A capture or encoder configuration failure must
                    // not terminate video/control; the UI reports audio as unavailable.
                    audioParser = null;
                }
                else {
                    throw error;
                }
            }
        }
        return {
            device,
            videoHeader,
            audioHeader,
            readVideoPacket: async () => {
                if (!videoParser)
                    throw new VersionMismatchError("video channel is disabled");
                return videoParser.readPacket();
            },
            readAudioPacket: async () => {
                if (!audioParser)
                    throw new VersionMismatchError("audio channel is disabled");
                return audioParser.readPacket();
            },
            readDeviceMessage: async () => {
                if (!deviceParser)
                    throw new VersionMismatchError("control channel is disabled");
                return deviceParser.read();
            },
            sendControl: async (message) => {
                if (!controlScheduler)
                    throw new VersionMismatchError("control channel is disabled");
                await controlScheduler.send(message);
            },
            close: async () => {
                try {
                    await controlScheduler?.close();
                    await controlWriter?.close();
                }
                finally {
                    await transport.close();
                }
            },
        };
    }
}
//# sourceMappingURL=adapter.js.map