import { BridgeApi } from "./api.js";
export interface NetworkElements {
    readonly card: HTMLElement;
    readonly badge: HTMLElement;
    readonly warning: HTMLElement;
    readonly mode: HTMLSelectElement;
    readonly lanFields: HTMLElement;
    readonly interfaceSelect: HTMLSelectElement;
    readonly bindAddress: HTMLInputElement;
    readonly allowedNetworks: HTMLInputElement;
    readonly hostname: HTMLInputElement;
    readonly certificateSource: HTMLSelectElement;
    readonly existingCertificate: HTMLElement;
    readonly certificatePath: HTMLInputElement;
    readonly privateKeyPath: HTMLInputElement;
    readonly validityRow: HTMLElement;
    readonly certificateValidity: HTMLSelectElement;
    readonly manageFirewall: HTMLInputElement;
    readonly port: HTMLInputElement;
    readonly currentPin: HTMLInputElement;
    readonly validate: HTMLButtonElement;
    readonly apply: HTMLButtonElement;
    readonly disable: HTMLButtonElement;
    readonly copyUrl: HTMLButtonElement;
    readonly downloadCertificate: HTMLAnchorElement;
    readonly url: HTMLElement;
    readonly status: HTMLElement;
}
export declare class NetworkAccessController {
    #private;
    private readonly elements;
    constructor(elements: NetworkElements, api?: BridgeApi);
    initialize(): Promise<void>;
}
