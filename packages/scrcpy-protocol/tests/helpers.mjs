export function streamFromChunks(...chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

export function concat(...parts) {
  const result = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

export function u32(value) {
  const data = new Uint8Array(4);
  new DataView(data.buffer).setUint32(0, value, false);
  return data;
}

export function u64(value) {
  const data = new Uint8Array(8);
  new DataView(data.buffer).setBigUint64(0, BigInt(value), false);
  return data;
}
