import { BridgeApi } from "./api.js";
interface Elements {
    readonly device: HTMLSelectElement;
    readonly select: HTMLSelectElement;
    readonly icon: HTMLButtonElement;
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
    private beginDropdownInteraction;
    private finishDropdownInteraction;
    private handleSelectionChange;
    private render;
    private currentVirtualApp;
    private selectedApp;
    private updateSelectionStatus;
    private moveSelected;
    private renderDiagnostics;
}
export {};
