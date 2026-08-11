import { BridgeApi, type AuthStatusDto } from "./api.js";
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
export declare class AuthController {
    #private;
    private readonly elements;
    constructor(elements: AuthElements, api?: BridgeApi);
    ensureAuthenticated(): Promise<AuthStatusDto>;
    refreshSessions(): Promise<void>;
    logout(): Promise<void>;
    changePin(): Promise<void>;
    revokeAll(): Promise<void>;
}
export {};
