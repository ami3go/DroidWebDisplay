interface AutoDownloadElements {
    readonly device: HTMLSelectElement;
    readonly enabled: HTMLInputElement;
    readonly pcToAndroidEnabled: HTMLInputElement;
    readonly source: HTMLSelectElement;
    readonly destination: HTMLSelectElement;
    readonly uploadDuplicatePolicy: HTMLSelectElement;
    readonly scanInterval: HTMLInputElement;
    readonly stabilitySeconds: HTMLInputElement;
    readonly stabilityObservations: HTMLInputElement;
    readonly includeExisting: HTMLInputElement;
    readonly includeExistingPc: HTMLInputElement;
    readonly deleteAfterVerified: HTMLInputElement;
    readonly notifications: HTMLInputElement;
    readonly save: HTMLButtonElement;
    readonly scanNow: HTMLButtonElement;
    readonly reset: HTMLButtonElement;
    readonly status: HTMLElement;
    readonly summary: HTMLElement;
    readonly events: HTMLElement;
}
export declare class AutoDownloadController {
    #private;
    private readonly elements;
    constructor(elements: AutoDownloadElements);
    initialize(): Promise<void>;
    private bindEvents;
    private refreshRoots;
    private save;
    private filesDrawerVisible;
    private refreshDelay;
    private scheduleRefresh;
    private refresh;
    private applySnapshot;
    private renderEvents;
    private configureNotifications;
    private notifyNewEvents;
    private runAction;
}
export {};
