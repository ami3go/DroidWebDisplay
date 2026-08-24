/**
 * A patched scrcpy server answers an explicit Copy request directly while its
 * native clipboard listener may report the same Android change as well. Keep
 * that expected second message from overwriting the manual-copy result/status.
 */
export declare class ManualCopyDuplicateGuard {
    #private;
    private readonly windowMs;
    constructor(windowMs?: number);
    arm(text: string, now: number): void;
    consume(text: string, now: number): boolean;
    reset(): void;
}
