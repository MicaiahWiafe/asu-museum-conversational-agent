export interface ArtworkInfo {
  id: string;
  title: string;
  artist: string;
  year: string | null;
  medium: string | null;
  description: string | null;
}

export const BACKEND_BASE_URL =
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "http://localhost:8000";

export async function fetchArtworks(): Promise<ArtworkInfo[]> {
  const res = await fetch(`${BACKEND_BASE_URL}/artworks`);
  if (!res.ok) throw new Error(`/artworks ${res.status}`);
  const json = (await res.json()) as { artworks: ArtworkInfo[] };
  return json.artworks ?? [];
}

export interface IdentifyResult {
  artwork_id: string | null;
  confidence: number;
  reason: string;
}

export async function identifyArtwork(
  imageBase64Jpeg: string,
): Promise<IdentifyResult> {
  const res = await fetch(`${BACKEND_BASE_URL}/identify-artwork`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ image_base64: imageBase64Jpeg }),
  });
  if (!res.ok) {
    let detail = `/identify-artwork ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as IdentifyResult;
}
