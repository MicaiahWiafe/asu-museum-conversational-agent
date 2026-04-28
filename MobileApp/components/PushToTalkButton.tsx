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
  disabled?: boolean;
  onPressStart: () => void;
  onPressEnd: () => void;
  onInterrupt: () => void;
}

const LABELS: Record<TalkState, string> = {
  idle: "Hold to ask",
  connecting: "Connecting…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Tap to interrupt",
  error: "Tap to retry",
};

export function PushToTalkButton({
  state,
  disabled,
  onPressStart,
  onPressEnd,
  onInterrupt,
}: PushToTalkButtonProps) {
  // Track whether we've fired onPressStart so we always fire onPressEnd to
  // match — necessary because pointercancel can land before pointerup if
  // the system steals the gesture.
  const armed = useRef(false);

  const handleDown = (e: React.PointerEvent) => {
    if (disabled) return;
    e.preventDefault();
    // Speaking → tap interrupts (do NOT start mic capture from this tap).
    if (state === "speaking") {
      onInterrupt();
      return;
    }
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

  useEffect(() => {
    if (state !== "listening") armed.current = false;
  }, [state]);

  const isListening = state === "listening";
  const ring = isListening ? "pulse-talk" : "";
  const tone =
    state === "error"
      ? "bg-clay"
      : state === "speaking"
        ? "bg-terracotta/80"
        : "bg-terracotta active:bg-terracotta/90";

  return (
    <div className="flex flex-col items-center gap-2 select-none touch-none">
      <button
        type="button"
        disabled={disabled}
        onPointerDown={handleDown}
        onPointerUp={handleUpOrCancel}
        onPointerCancel={handleUpOrCancel}
        onPointerLeave={handleUpOrCancel}
        className={[
          "h-24 w-24 rounded-full flex items-center justify-center text-white shadow-lg",
          "disabled:opacity-40 disabled:bg-clay",
          tone,
          ring,
        ].join(" ")}
        aria-label="Push to talk"
      >
        {state === "speaking" ? <StopGlyph /> : <MicGlyph />}
      </button>
      <div className="text-xs text-ink/70 font-medium tracking-wider uppercase">
        {LABELS[state]}
      </div>
    </div>
  );
}

function MicGlyph() {
  return (
    <svg
      width="32"
      height="32"
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

function StopGlyph() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}
