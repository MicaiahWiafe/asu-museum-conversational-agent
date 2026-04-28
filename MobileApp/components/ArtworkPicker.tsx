"use client";

import { useMemo, useState } from "react";

import type { ArtworkInfo } from "@/lib/api";

export type SortMode = "title" | "year";

export interface ArtworkPickerProps {
  artworks: ArtworkInfo[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading?: boolean;
}

function parseYear(year: string | null | undefined): number {
  if (!year) return Number.POSITIVE_INFINITY;
  // Match the first 4-digit run; handles "1987", "c. 1989", "1990–92".
  const m = year.match(/\d{4}/);
  return m ? parseInt(m[0], 10) : Number.POSITIVE_INFINITY;
}

export function ArtworkPicker({
  artworks,
  selectedId,
  onSelect,
  loading = false,
}: ArtworkPickerProps) {
  const [sortMode, setSortMode] = useState<SortMode>("title");
  const [filter, setFilter] = useState("");

  if (loading && artworks.length === 0) {
    return (
      <div className="grid grid-cols-1 gap-2">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-2xl border border-clay/15 px-4 py-3"
          >
            <div className="skeleton h-5 w-2/3 rounded" />
            <div className="skeleton h-3 w-1/3 rounded mt-2" />
          </div>
        ))}
      </div>
    );
  }

  const sorted = useMemo(() => {
    const list = [...artworks];
    list.sort((a, b) => {
      if (sortMode === "year") {
        const ay = parseYear(a.year);
        const by = parseYear(b.year);
        if (ay !== by) return ay - by;
      }
      return a.title.localeCompare(b.title, undefined, { sensitivity: "base" });
    });

    // Pin the currently selected artwork to the top so the visitor never
    // has to scroll-hunt to see what they're talking about.
    if (selectedId) {
      const idx = list.findIndex((x) => x.id === selectedId);
      if (idx > 0) {
        const [sel] = list.splice(idx, 1);
        list.unshift(sel);
      }
    }
    return list;
  }, [artworks, sortMode, selectedId]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        (a.medium ?? "").toLowerCase().includes(q) ||
        (a.year ?? "").toLowerCase().includes(q),
    );
  }, [sorted, filter]);

  if (artworks.length === 0) {
    return (
      <p className="text-clay text-sm">
        No artworks loaded. Check the backend and{" "}
        <code className="text-xs bg-cream/60 px-1 rounded">artworks.json</code>.
      </p>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-2">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search…"
          className="flex-1 min-w-0 rounded-full border border-clay/25 bg-white/60 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-terracotta/40"
        />
        <div className="flex rounded-full border border-clay/25 bg-white/60 text-xs overflow-hidden shrink-0">
          {(["title", "year"] as SortMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setSortMode(m)}
              className={[
                "px-3 py-2 transition",
                sortMode === m
                  ? "bg-terracotta text-white"
                  : "text-ink/70 active:bg-white/80",
              ].join(" ")}
            >
              {m === "title" ? "A→Z" : "Year"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2">
        {filtered.map((a) => {
          const active = a.id === selectedId;
          return (
            <button
              key={a.id}
              type="button"
              onClick={() => onSelect(a.id)}
              className={[
                "text-left rounded-2xl border px-4 py-3 transition",
                active
                  ? "border-terracotta bg-terracotta/5 ring-1 ring-terracotta/40"
                  : "border-clay/20 bg-white/40 active:bg-white/60",
              ].join(" ")}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="font-serif text-lg leading-tight">
                  {a.title}
                </div>
                {active && (
                  <span className="text-[10px] uppercase tracking-widest text-terracotta mt-1 shrink-0">
                    selected
                  </span>
                )}
              </div>
              <div className="text-xs text-clay mt-0.5">
                {a.year || "n.d."}
                {a.medium ? ` · ${a.medium}` : ""}
              </div>
            </button>
          );
        })}
        {filtered.length === 0 && (
          <p className="text-clay/70 text-sm py-4">
            No matches for "{filter}".
          </p>
        )}
      </div>
    </div>
  );
}
