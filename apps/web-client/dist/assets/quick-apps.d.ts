import type { LaunchableAppDto } from "./types.js";
export declare const MAX_QUICK_APP_BUTTONS = 12;
export type QuickAppsByDevice = Readonly<Record<string, readonly string[]>>;
export declare function normalizeQuickAppPackages(value: unknown): readonly string[];
export declare function normalizeQuickAppsByDevice(value: unknown): QuickAppsByDevice;
export declare function nextQuickAppPackage(configured: readonly string[], catalog: readonly LaunchableAppDto[]): string | null;
export declare function moveQuickApp(configured: readonly string[], index: number, offset: -1 | 1): readonly string[];
