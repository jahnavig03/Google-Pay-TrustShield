/** QR decoding on the device (jsQR). Images never leave the browser. */
import jsQR from "jsqr";

const MAX_SIDE = 1280;
export const MAX_QR_IMAGE_BYTES = 8 * 1024 * 1024;

export function decodeImageData(data: ImageData): string | null {
  const result = jsQR(data.data, data.width, data.height, { inversionAttempts: "attemptBoth" });
  return result?.data ?? null;
}

function drawToCanvas(source: CanvasImageSource, width: number, height: number): ImageData {
  const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("Canvas is not available in this browser.");
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

/** Decode a QR from an uploaded or fetched image. Returns null if no QR was found. */
export async function decodeBlob(blob: Blob): Promise<string | null> {
  if (blob.size > MAX_QR_IMAGE_BYTES) throw new Error("That image is larger than 8 MB.");
  const bitmap = await createImageBitmap(blob);
  try {
    return decodeImageData(drawToCanvas(bitmap, bitmap.width, bitmap.height));
  } finally {
    bitmap.close();
  }
}

/** Decode one camera frame. */
export function decodeVideoFrame(video: HTMLVideoElement): string | null {
  if (!video.videoWidth || !video.videoHeight) return null;
  return decodeImageData(drawToCanvas(video, video.videoWidth, video.videoHeight));
}
