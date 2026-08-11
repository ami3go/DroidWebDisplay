import { InvalidProtocolValueError } from "../../common/errors.js";

export interface H264DecoderConfiguration {
  readonly codec: string;
  readonly format: "annexb";
  readonly sequenceParameterSets: readonly Uint8Array[];
  readonly pictureParameterSets: readonly Uint8Array[];
}

export function extractH264DecoderConfiguration(data: Uint8Array): H264DecoderConfiguration {
  const nalUnits = splitAnnexBNalUnits(data);
  const sps = nalUnits.filter((nal) => (nal[0]! & 0x1f) === 7);
  const pps = nalUnits.filter((nal) => (nal[0]! & 0x1f) === 8);
  if (!sps.length || !pps.length) {
    throw new InvalidProtocolValueError("H.264 configuration packet does not contain both SPS and PPS NAL units");
  }
  const firstSps = sps[0]!;
  if (firstSps.byteLength < 4) {
    throw new InvalidProtocolValueError("H.264 SPS is too short to derive codec profile");
  }
  const profile = firstSps[1]!.toString(16).padStart(2, "0");
  const compatibility = firstSps[2]!.toString(16).padStart(2, "0");
  const level = firstSps[3]!.toString(16).padStart(2, "0");
  return {
    codec: `avc1.${profile}${compatibility}${level}`,
    format: "annexb",
    sequenceParameterSets: sps,
    pictureParameterSets: pps,
  };
}

export function splitAnnexBNalUnits(data: Uint8Array): Uint8Array[] {
  const starts: Array<{ offset: number; prefixLength: number }> = [];
  for (let index = 0; index + 3 <= data.byteLength; index += 1) {
    if (data[index] !== 0 || data[index + 1] !== 0) continue;
    if (data[index + 2] === 1) {
      starts.push({ offset: index, prefixLength: 3 });
      index += 2;
    } else if (index + 4 <= data.byteLength && data[index + 2] === 0 && data[index + 3] === 1) {
      starts.push({ offset: index, prefixLength: 4 });
      index += 3;
    }
  }
  if (!starts.length) {
    throw new InvalidProtocolValueError("H.264 packet is not Annex B formatted");
  }

  const units: Uint8Array[] = [];
  for (let index = 0; index < starts.length; index += 1) {
    const start = starts[index]!;
    const payloadStart = start.offset + start.prefixLength;
    const payloadEnd = starts[index + 1]?.offset ?? data.byteLength;
    if (payloadEnd > payloadStart) {
      units.push(data.slice(payloadStart, payloadEnd));
    }
  }
  if (!units.length) {
    throw new InvalidProtocolValueError("H.264 Annex B packet contains no NAL units");
  }
  return units;
}
