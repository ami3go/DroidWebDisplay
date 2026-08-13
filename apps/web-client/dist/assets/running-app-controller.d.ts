import { BridgeApi } from "./api.js";
interface Elements {
    readonly device: HTMLSelectElement;
    readonly select: HTMLSelectElement;
    readonly refresh: HTMLButtonElement;
    readonly count: HTMLElement;
    readonly status: HTMLElement;
    readonly diagnosticDisplay: HTMLElement;
    readonly diagnosticRam: HTMLElement;
}
export declare class RunningAppController {
    #private;
    constructor(elements: Elements, api?: BridgeApi);
    initialize(): Promise<void>;
    close(): void;
    refresh(silent?: boolean): Promise<void>;
    private render;
    private selectedApp;
    private updateSelectionStatus;
    private moveSelected;
    private renderDiagnostics;
}
export {};
