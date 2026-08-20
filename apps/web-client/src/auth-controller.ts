import { BridgeApi, BridgeApiError, type AuthSessionDto, type AuthStatusDto } from "./api.js";

interface AuthElements {
  readonly gate: HTMLElement;
  readonly form: HTMLFormElement;
  readonly title: HTMLElement;
  readonly explanation: HTMLElement;
  readonly pin: HTMLInputElement;
  readonly confirmRow: HTMLElement;
  readonly confirmPin: HTMLInputElement;
  readonly duration: HTMLSelectElement;
  readonly customRow: HTMLElement;
  readonly customValue: HTMLInputElement;
  readonly customUnit: HTMLSelectElement;
  readonly label: HTMLInputElement;
  readonly error: HTMLElement;
  readonly submit: HTMLButtonElement;
  readonly securityCard: HTMLElement;
  readonly sessionSummary: HTMLElement;
  readonly sessionList: HTMLElement;
  readonly refreshSessions: HTMLButtonElement;
  readonly logout: HTMLButtonElement;
  readonly currentPin: HTMLInputElement;
  readonly newPin: HTMLInputElement;
  readonly confirmNewPin: HTMLInputElement;
  readonly changePin: HTMLButtonElement;
  readonly revokeAllPin: HTMLInputElement;
  readonly revokeAll: HTMLButtonElement;
  readonly securityStatus: HTMLElement;
}

function formatTimestamp(value: number | null): string {
  if (value === null) return "Until revoked";
  return new Date(value * 1000).toLocaleString();
}

function customSeconds(value: number, unit: string): number {
  const factor = unit === "minutes" ? 60 : (unit === "hours" ? 3600 : 86400);
  return Math.round(value * factor);
}

export class AuthController {
  readonly #api: BridgeApi;
  #status: AuthStatusDto | null = null;
  #reopening = false;

  public constructor(private readonly elements: AuthElements, api = new BridgeApi()) {
    this.#api = api;
    elements.duration.addEventListener("change", () => this.#syncCustomVisibility());
    elements.form.addEventListener("submit", (event) => { event.preventDefault(); void this.#submit(); });
    elements.refreshSessions.addEventListener("click", () => { void this.refreshSessions(); });
    elements.logout.addEventListener("click", () => { void this.logout(); });
    elements.changePin.addEventListener("click", () => { void this.changePin(); });
    elements.revokeAll.addEventListener("click", () => { void this.revokeAll(); });
    globalThis.addEventListener("droidwebdisplay-auth-required", () => { void this.#reopenGate(); });
  }

  public async ensureAuthenticated(): Promise<AuthStatusDto> {
    const status = await this.#api.authStatus();
    this.#status = status;
    if (status.authenticated) {
      this.#showAuthenticated(status);
      return status;
    }
    this.#renderGate(status.configured);
    return new Promise<AuthStatusDto>((resolve) => {
      const listener = (event: Event): void => {
        const value = (event as CustomEvent<AuthStatusDto>).detail;
        globalThis.removeEventListener("droidwebdisplay-authenticated", listener);
        resolve(value);
      };
      globalThis.addEventListener("droidwebdisplay-authenticated", listener);
    });
  }

  public async refreshSessions(): Promise<void> {
    try {
      const response = await this.#api.authSessions();
      this.elements.sessionList.replaceChildren(...response.sessions.map((session) => this.#sessionRow(session)));
      if (!response.sessions.length) this.elements.sessionList.textContent = "No trusted browser sessions.";
      this.elements.securityStatus.textContent = "Trusted sessions refreshed.";
    } catch (error) {
      this.#showSecurityError(error);
    }
  }

  public async logout(): Promise<void> {
    try {
      await this.#api.authLogout();
      globalThis.location.reload();
    } catch (error) {
      this.#showSecurityError(error);
    }
  }

  public async changePin(): Promise<void> {
    const currentPin = this.elements.currentPin.value;
    const newPin = this.elements.newPin.value;
    const confirmPin = this.elements.confirmNewPin.value;
    try {
      await this.#api.changeAuthPin(currentPin, newPin, confirmPin);
      this.elements.securityStatus.textContent = "PIN changed. All trusted sessions were revoked.";
      globalThis.location.reload();
    } catch (error) {
      this.#showSecurityError(error);
    }
  }

  public async revokeAll(): Promise<void> {
    try {
      const result = await this.#api.revokeAllAuthSessions(this.elements.revokeAllPin.value);
      this.elements.securityStatus.textContent = `Revoked ${result.revoked} trusted session(s).`;
      globalThis.location.reload();
    } catch (error) {
      this.#showSecurityError(error);
    }
  }

  /** Re-open the gate after a session expires or is revoked.

      This used to only unhide the gate, which left whatever form was rendered
      last on screen. After first-run setup that is the setup form, so a lock
      later in the same page session showed "Create bridge PIN" with the
      Confirm PIN box still visible, even though the PIN already exists and the
      submit would perform a login. The server is the authority on whether a
      PIN is configured, so re-read it. */
  async #reopenGate(): Promise<void> {
    this.elements.securityStatus.textContent = "Session expired or revoked. Authenticate again.";
    // Several in-flight requests can each answer 401 at once. Re-rendering per
    // event would clear the PIN field under someone already typing into it.
    if (!this.elements.gate.hidden || this.#reopening) return;
    this.#reopening = true;
    try {
      let configured = this.#status?.configured ?? false;
      try {
        const status = await this.#api.authStatus();
        this.#status = status;
        if (status.authenticated) {
          this.#showAuthenticated(status);
          return;
        }
        configured = status.configured;
      } catch {
        // Status is unreachable; fall back to the last known value rather than
        // leaving the user with no way back in.
      }
      this.#renderGate(configured);
    } finally {
      this.#reopening = false;
    }
  }

  #renderGate(configured: boolean): void {
    this.elements.gate.hidden = false;
    this.elements.title.textContent = configured ? "Unlock DroidWebDisplay" : "Create bridge PIN";
    this.elements.explanation.textContent = configured
      ? "Enter the PIN configured on this PC. Android does not remember or authorize this browser."
      : "Create a PIN for this PC-local bridge. It protects the local web service; it is not stored on the Android phone.";
    this.elements.confirmRow.hidden = configured;
    this.elements.submit.textContent = configured ? "Unlock" : "Create PIN and unlock";
    this.elements.error.textContent = "";
    this.elements.pin.value = "";
    this.elements.confirmPin.value = "";
    this.#syncCustomVisibility();
    queueMicrotask(() => this.elements.pin.focus());
  }

  async #submit(): Promise<void> {
    this.elements.submit.disabled = true;
    this.elements.error.textContent = "";
    const configured = this.#status?.configured ?? false;
    const duration = this.elements.duration.value;
    const custom = duration === "custom"
      ? customSeconds(Number(this.elements.customValue.value), this.elements.customUnit.value)
      : undefined;
    try {
      const optional = {
        ...(custom === undefined ? {} : { customSeconds: custom }),
        ...(this.elements.label.value ? { label: this.elements.label.value } : {}),
      };
      const status = configured
        ? await this.#api.authLogin({
          pin: this.elements.pin.value,
          duration,
          ...optional,
        })
        : await this.#api.authSetup({
          pin: this.elements.pin.value,
          confirmPin: this.elements.confirmPin.value,
          duration,
          ...optional,
        });
      this.#status = status;
      this.#showAuthenticated(status);
      globalThis.dispatchEvent(new CustomEvent("droidwebdisplay-authenticated", { detail: status }));
    } catch (error) {
      this.elements.error.textContent = error instanceof BridgeApiError ? error.message : String(error);
    } finally {
      this.elements.submit.disabled = false;
    }
  }

  #showAuthenticated(status: AuthStatusDto): void {
    this.elements.gate.hidden = true;
    this.elements.securityCard.hidden = false;
    const session = status.currentSession;
    this.elements.sessionSummary.textContent = session
      ? `${session.label} · trusted until ${formatTimestamp(session.expiresAt)}`
      : "Authenticated PC-local session";
    void this.refreshSessions();
  }

  #sessionRow(session: AuthSessionDto): HTMLElement {
    const row = document.createElement("div");
    row.className = `trusted-session-row${session.revokedAt ? " revoked" : ""}`;
    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${session.label}${session.current ? " · Current" : ""}`;
    const details = document.createElement("small");
    details.textContent = session.revokedAt
      ? `Revoked: ${session.revocationReason ?? "yes"}`
      : `Expires: ${formatTimestamp(session.expiresAt)}`;
    info.append(title, details);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary compact";
    button.textContent = "Revoke";
    button.disabled = session.revokedAt !== null;
    button.addEventListener("click", () => {
      void this.#api.revokeAuthSession(session.sessionId).then((result) => {
        if (result.currentSessionRevoked) globalThis.location.reload();
        else void this.refreshSessions();
      }).catch((error) => this.#showSecurityError(error));
    });
    row.append(info, button);
    return row;
  }

  #syncCustomVisibility(): void {
    this.elements.customRow.hidden = this.elements.duration.value !== "custom";
  }

  #showSecurityError(error: unknown): void {
    this.elements.securityStatus.textContent = error instanceof BridgeApiError ? error.message : String(error);
  }
}
