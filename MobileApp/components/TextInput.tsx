"use client";

import { useState } from "react";

export interface TextInputProps {
  disabled?: boolean;
  placeholder?: string;
  onSubmit: (text: string) => void;
}

/**
 * Compact text-question input for visitors who prefer typing over
 * push-to-talk. Submitting hands the text off to the parent (page.tsx),
 * which forwards it through the same WebSocket so the typed turn shares
 * conversation memory with prior voice turns.
 */
export function TextInput({
  disabled = false,
  placeholder = "or type a question…",
  onSubmit,
}: TextInputProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSubmit(text);
    setValue("");
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex items-center gap-2 rounded-full border border-clay/25 bg-white/70 backdrop-blur px-3 py-1.5 shadow-sm"
    >
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        // Use enterkeyhint=send so iOS shows a "Send" key. inputMode=text
        // and autoCorrect=on are mobile-default; keep them implicit.
        enterKeyHint="send"
        className="flex-1 min-w-0 bg-transparent text-sm placeholder:text-clay/60 focus:outline-none disabled:opacity-50"
        aria-label="Type a question"
      />
      <button
        type="submit"
        disabled={disabled || value.trim().length === 0}
        className="shrink-0 h-8 w-8 rounded-full bg-terracotta text-white flex items-center justify-center disabled:opacity-30 disabled:bg-clay active:bg-terracotta/90"
        aria-label="Send question"
      >
        <SendGlyph />
      </button>
    </form>
  );
}

function SendGlyph() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}
