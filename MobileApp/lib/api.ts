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
