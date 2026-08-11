import { AsyncByteReader } from "../../common/async-byte-reader.js";
import type { DeviceInfo } from "../../common/types.js";
export declare function readDummyByte(reader: AsyncByteReader): Promise<void>;
export declare function readDeviceInfo(reader: AsyncByteReader): Promise<DeviceInfo>;
