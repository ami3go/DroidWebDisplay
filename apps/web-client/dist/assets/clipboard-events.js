/**
 * A patched scrcpy server answers an explicit Copy request directly while its
 * native clipboard listener may report the same Android change as well. Keep
 * that expected second message from overwriting the manual-copy result/status.
 */
export class ManualCopyDuplicateGuard {
    windowMs;
    #text = null;
    #expiresAt = 0;
    constructor(windowMs = 750) {
        this.windowMs = windowMs;
        if (!Number.isFinite(windowMs) || windowMs <= 0)
            throw new Error("windowMs must be positive");
    }
    arm(text, now) {
        this.#text = text;
        this.#expiresAt = now + this.windowMs;
    }
    consume(text, now) {
        const matches = this.#text === text && now <= this.#expiresAt;
        if (matches || now > this.#expiresAt)
            this.reset();
        return matches;
    }
    reset() {
        this.#text = null;
        this.#expiresAt = 0;
    }
}
//# sourceMappingURL=clipboard-events.js.map