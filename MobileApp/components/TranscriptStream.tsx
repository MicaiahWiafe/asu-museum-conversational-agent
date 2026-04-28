"use client";

import { useEffect, useRef } from "react";

export interface TranscriptStreamProps {
  text: string;
}

/** Live captions of Gemini's spoken response. Empty space when idle. */
export function TranscriptStream({ text }: TranscriptStreamProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [text]);
  return (
    <div
      ref={ref}
      className="min-h-24 max-h-40 overflow-y-auto rounded-2xl bg-white/40 border border-clay/15 px-4 py-3 text-ink/85 leading-relaxed font-serif text-base"
      aria-live="polite"
    >
      {text || (
        <span className="text-clay/60 text-sm">
          Pick an artwork below, then hold the button and ask anything.
        </span>
      )}
    </div>
  );
}
