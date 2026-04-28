"use client";

import { useEffect, useRef } from "react";

export type TalkState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

export interface PushToTalkButtonProps {
  state: TalkState;
  /** 0..1 RMS — only meaningful when state === "listening". */
  level: number;
  disabled?: boolean;
  onPressStart: () => void;
  onPressEnd: () => void;
}

const LABELS: Record<TalkState, string> = {
  idle: "Hold to ask",
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Hold to interrupt",
  error: "Tap to retry",
};

const HINTS: Record<TalkState, string> = {
  idle: "Press and hold · release to send",
  connecting: "",
  listening: "Release when you're done",
  thinking: "",
  speaking: "Hold to cut off and ask a follow-up",
  error: "",
};

export function PushToTalkButton({
  state,
  level,
  disabled,
  onPressStart,
  onPressEnd,
}: PushToTalkButtonProps) {
  const armed = useRef(false);

  // Press-and-hold no matter what state we're in. The page handler decides
  // whether this is a fresh ask, a barge-in, or a retry — by the time the
  // user holds the button we always want to start listening to them.
  const handleDown = (e: React.PointerEvent) => {
    if (disabled) return;
    e.preventDefault();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    if (armed.current) return;
    armed.current = true;
    onPressStart();
  };

  const handleUpOrCancel = (e: React.PointerEvent) => {
    if (disabled) return;
    e.preventDefault();
    if (!armed.current) return;
    armed.current = false;
    onPressEnd();
  };

  // If the state machine externally falls back to idle/error mid-press
  // (e.g. server error), drop the armed flag so the next press starts fresh.
  useEffect(() => {
    if (state !== "listening" && state !== "thinking") armed.current = false;
  }, [state]);

  const isListening = state === "listening";
  const isThinking = state === "thinking";

  // Map RMS to a 0..1 ring scale. Floor at a low threshold so quiet rooms
  // don't show pure 0; clamp at a comfortable ceiling.
  const meterScale = isListening
    ? Math.min(1, Math.max(0.05, level * 6))
    : 0;

  const tone =
    state === "error"
      ? "bg-clay"
      : state === "speaking"
        ? "bg-terracotta/85"
        : "bg-terracotta active:bg-terracotta/90";

  return (
    <div className="flex flex-col items-center gap-1.5 select-none touch-none">
      <div className="relative">
        {/* Live mic-level halo — grows with RMS while listening. */}
        {isListening && (
          <div
            aria-hidden
            className="absolute inset-0 rounded-full bg-terracotta/30 transition-transform duration-75 ease-out"
            style={{ transform: `scale(${1 + meterScale * 0.45})` }}
          />
        )}
        <button
          type="button"
          disabled={disabled}
          onPointerDown={handleDown}
          onPointerUp={handleUpOrCancel}
          onPointerCancel={handleUpOrCancel}
          onPointerLeave={handleUpOrCancel}
          className={[
            "relative h-28 w-28 rounded-full flex items-center justify-center text-white shadow-lg",
            "disabled:opacity-40 disabled:bg-clay disabled:cursor-not-allowed",
            tone,
            isListening ? "pulse-talk" : "",
          ].join(" ")}
          aria-label="Push to talk"
        >
          {isThinking ? <ThinkingDots /> : <MicGlyph />}
        </button>
      </div>
      <div className="text-xs text-ink/80 font-medium tracking-wider uppercase mt-1">
        {LABELS[state]}
      </div>
      {HINTS[state] && (
        <div className="text-[11px] text-clay/80">{HINTS[state]}</div>
      )}
    </div>
  );
}

function MicGlyph() {
  return (
    <svg
      width="34"
      height="34"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="9" y="3" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <line x1="12" y1="18" x2="12" y2="22" />
      <line x1="8" y1="22" x2="16" y2="22" />
    </svg>
  );
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1.5 text-white" aria-hidden="true">
      <span className="dot" />
      <span className="dot" />
      <span className="dot" />
    </div>
  );
}
