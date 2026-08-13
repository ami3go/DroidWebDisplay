import { BridgeApi } from "./api.js";
interface Elements {
    readonly device: HTMLSelectElement;
    readonly select: HTMLSelectElement;
    readonly refresh: HTMLButtonElement;
    readonly move: HTMLButtonElement;
    readonly status: HTMLElement;
}
export declare class RunningAppController {
    #private;
    constructor(elements: Elements, api?: BridgeApi);
    initialize(): Promise<void>;
    close(): void;
    refresh(silent?: boolean): Promise<void>;
    private render;
    private selectActiveVirtualSession;
    private updateTargetStatus;
    private selectedApp;
    private updateControls;
    private moveSelected;
}
export {};
