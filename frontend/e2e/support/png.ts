import { deflateSync, inflateSync } from "node:zlib";

/**
 * A minimal PNG encoder and decoder. The encoder hands MapLibre tiles of one
 * flat colour without touching the network. The decoder reads screenshots, so
 * tests can check what colour the map drew at a given pixel. Neither needs a
 * dependency.
 */

const CRC_TABLE = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = (CRC_TABLE[(crc ^ byte) & 0xff] as number) ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Uint8Array): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

/** A width by height PNG filled with one opaque RGB colour. */
export function solidPng(width: number, height: number, rgb: readonly [number, number, number]): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8; // bit depth
  header[9] = 2; // colour type: RGB
  const row = Buffer.alloc(1 + width * 3);
  for (let x = 0; x < width; x++) row.set(rgb, 1 + x * 3);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", new Uint8Array(0)),
  ]);
}

export class PngError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PngError";
  }
}

export interface DecodedImage {
  width: number;
  height: number;
  /** Bytes per pixel: 3 for RGB, 4 for RGBA. */
  channels: 3 | 4;
  data: Uint8Array;
}

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  return pb <= pc ? b : c;
}

/** Decode an 8-bit, non-interlaced RGB or RGBA PNG, which is what a browser screenshot is. */
export function decodePng(png: Uint8Array): DecodedImage {
  const buffer = Buffer.from(png.buffer, png.byteOffset, png.byteLength);
  if (buffer.readUInt32BE(0) !== 0x89504e47) throw new PngError("Not a PNG file");
  let width = 0;
  let height = 0;
  let channels: 3 | 4 = 4;
  const idat: Buffer[] = [];
  for (let offset = 8; offset < buffer.length; ) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const body = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = body.readUInt32BE(0);
      height = body.readUInt32BE(4);
      const [bitDepth, colourType, , , interlace] = [body[8], body[9], body[10], body[11], body[12]];
      if (bitDepth !== 8 || interlace !== 0 || (colourType !== 2 && colourType !== 6)) {
        throw new PngError(`Unsupported PNG: bit depth ${bitDepth}, colour type ${colourType}, interlace ${interlace}`);
      }
      channels = colourType === 2 ? 3 : 4;
    } else if (type === "IDAT") {
      idat.push(body);
    } else if (type === "IEND") {
      break;
    }
    offset += 12 + length;
  }
  if (width === 0 || height === 0) throw new PngError("PNG has no header");

  const raw = inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  if (raw.length !== (stride + 1) * height) throw new PngError("PNG data is the wrong length");
  const data = new Uint8Array(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)] as number;
    const input = y * (stride + 1) + 1;
    const output = y * stride;
    for (let x = 0; x < stride; x++) {
      const left = x >= channels ? (data[output + x - channels] as number) : 0;
      const up = y > 0 ? (data[output + x - stride] as number) : 0;
      const upLeft = y > 0 && x >= channels ? (data[output + x - stride - channels] as number) : 0;
      const value = raw[input + x] as number;
      let predicted: number;
      if (filter === 0) predicted = 0;
      else if (filter === 1) predicted = left;
      else if (filter === 2) predicted = up;
      else if (filter === 3) predicted = (left + up) >> 1;
      else if (filter === 4) predicted = paeth(left, up, upLeft);
      else throw new PngError(`Unknown PNG filter ${filter}`);
      data[output + x] = (value + predicted) & 0xff;
    }
  }
  return { width, height, channels, data };
}

export type Rgb = readonly [number, number, number];

/** The colour of one pixel. */
export function pixelAt(image: DecodedImage, x: number, y: number): Rgb {
  const px = Math.round(x);
  const py = Math.round(y);
  if (px < 0 || py < 0 || px >= image.width || py >= image.height) {
    throw new PngError(`Pixel ${px}, ${py} is outside the ${image.width} by ${image.height} image`);
  }
  const at = (py * image.width + px) * image.channels;
  return [image.data[at] as number, image.data[at + 1] as number, image.data[at + 2] as number];
}

export function hexToRgb(hex: string): Rgb {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new PngError(`"${hex}" is not a six-digit hex colour`);
  return [
    Number.parseInt(match[1] as string, 16),
    Number.parseInt(match[2] as string, 16),
    Number.parseInt(match[3] as string, 16),
  ];
}

/** The largest difference between two colours on any one channel. */
export function colourDistance(a: Rgb, b: Rgb): number {
  return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]), Math.abs(a[2] - b[2]));
}

/** How many pixels in a box are within `tolerance` of a colour. */
export function countColour(
  image: DecodedImage,
  box: { x: number; y: number; width: number; height: number },
  colour: Rgb,
  tolerance: number,
): number {
  let count = 0;
  for (let y = Math.max(0, Math.floor(box.y)); y < Math.min(image.height, box.y + box.height); y++) {
    for (let x = Math.max(0, Math.floor(box.x)); x < Math.min(image.width, box.x + box.width); x++) {
      if (colourDistance(pixelAt(image, x, y), colour) <= tolerance) count += 1;
    }
  }
  return count;
}
