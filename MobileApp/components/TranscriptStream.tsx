"use client";

import { useEffect, useRef } from "react";

import type { TalkState } from "@/components/PushToTalkButton";

export interface TranscriptStreamProps {
  text: string;
  state: TalkState;
}

/** Live captions of Gemini's spoken response. Empty space when idle. */
export function TranscriptStream({ text, state }: TranscriptStreamProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [text]);

  const showThinking = state === "thinking" && !text;
  const showHint = state === "idle" && !text;

  return (
    <div
      ref={ref}
      className="min-h-28 max-h-44 overflow-y-auto rounded-2xl bg-white/40 border border-clay/15 px-4 py-3 text-ink/85 leading-relaxed font-serif text-base"
      aria-live="polite"
    >
      {text && <span>{text}</span>}
      {showThinking && (
        <span className="text-clay/80 inline-flex items-center gap-2">
          <span className="dot bg-clay/70" />
          <span className="dot bg-clay/70" />
          <span className="dot bg-clay/70" />
          <span className="text-sm font-sans">Searching the gallery…</span>
        </span>
      )}
      {showHint && (
        <span className="text-clay/60 text-sm font-sans">
          Pick an artwork below, then hold the button and ask anything — try
          "What's happening in this painting?" or "Who is the artist?"
        </span>
      )}
    </div>
  );
}
