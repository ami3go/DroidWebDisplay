/**
 * A patched scrcpy server answers an explicit Copy request directly while its
 * native clipboard listener may report the same Android change as well. Keep
 * that expected second message from overwriting the manual-copy result/status.
 */
export class ManualCopyDuplicateGuard {
  #text: string | null = null;
  #expiresAt = 0;

  public constructor(private readonly windowMs = 750) {
    if (!Number.isFinite(windowMs) || windowMs <= 0) throw new Error("windowMs must be positive");
  }

  public arm(text: string, now: number): void {
    this.#text = text;
    this.#expiresAt = now + this.windowMs;
  }

  public consume(text: string, now: number): boolean {
    const matches = this.#text === text && now <= this.#expiresAt;
    if (matches || now > this.#expiresAt) this.reset();
    return matches;
  }

  public reset(): void {
    this.#text = null;
    this.#expiresAt = 0;
  }
}
