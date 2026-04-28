"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

function friendlyError(e: unknown): string {
  if (e instanceof DOMException) {
    if (e.name === "NotFoundError") {
      return "No microphone detected. Mac mini has no built-in mic — connect AirPods, a USB mic, or test on a phone.";
    }
    if (e.name === "NotAllowedError") {
      return "Microphone access blocked. Check the page's mic permission and macOS Settings → Privacy → Microphone.";
    }
    if (e.name === "NotReadableError") {
      return "Microphone is busy in another app. Close apps that may be holding the mic and try again.";
    }
  }
  return e instanceof Error ? e.message : String(e);
}

import { ArtworkPicker } from "@/components/ArtworkPicker";
import {
  PushToTalkButton,
  type TalkState,
} from "@/components/PushToTalkButton";
import { TranscriptStream } from "@/components/TranscriptStream";
import {
  BACKEND_BASE_URL,
  fetchArtworks,
  type ArtworkInfo,
} from "@/lib/api";
import { MicCapture } from "@/lib/audio-capture";
import { StreamingPlayer } from "@/lib/audio-playback";
import {
  VoiceSession,
  type ServerEvent,
} from "@/lib/voice-session";

export default function Page() {
  const [artworks, setArtworks] = useState<ArtworkInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [state, setState] = useState<TalkState>("idle");
  const [transcript, setTranscript] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const sessionRef = useRef<VoiceSession | null>(null);
  const captureRef = useRef<MicCapture | null>(null);
  const playerRef = useRef<StreamingPlayer | null>(null);
  const turnStartedRef = useRef(false);

  // Load the artwork registry once at boot.
  useEffect(() => {
    let cancelled = false;
    fetchArtworks()
      .then((list) => {
        if (cancelled) return;
        setArtworks(list);
        if (list.length > 0) {
          // Pick the alphabetically first artwork as the default —
          // matches the picker's default sort so the visitor isn't
          // confused by "selected" being mid-list at boot.
          const first = [...list].sort((a, b) =>
            a.title.localeCompare(b.title, undefined, { sensitivity: "base" }),
          )[0];
          setSelectedId(first.id);
        }
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setErrMsg(`Couldn't load artworks: ${e.message}. Backend at ${BACKEND_BASE_URL}?`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Tear down on unmount.
  useEffect(() => {
    return () => {
      sessionRef.current?.close();
      captureRef.current?.stop();
      playerRef.current?.stop();
    };
  }, []);

  // When the visitor changes artwork, reset the session — system instruction
  // is bound at connect time, so a fresh socket gets the right artwork line.
  useEffect(() => {
    if (sessionRef.current) {
      sessionRef.current.close();
      sessionRef.current = null;
    }
    playerRef.current?.flush();
    setTranscript("");
    setErrMsg(null);
  }, [selectedId]);

  const ensureConnected = useCallback(async () => {
    if (sessionRef.current) return;
    setState("connecting");

    const player = new StreamingPlayer(24000);
    await player.start();
    playerRef.current = player;

    const session = new VoiceSession(BACKEND_BASE_URL, {
      onAudio: (pcm) => playerRef.current?.enqueue(pcm),
      onEvent: (evt: ServerEvent) => {
        switch (evt.type) {
          case "ready":
            break;
          case "transcript":
            setTranscript((t) => t + evt.text);
            setState("speaking");
            break;
          case "turn_complete":
            setState("idle");
            break;
          case "tool_call":
            setState("thinking");
            break;
          case "error":
            setErrMsg(evt.message);
            setState("error");
            // Close the dead session so the next press creates a fresh one.
            // Without this, ensureConnected() short-circuits because
            // sessionRef.current is still set, and the retry uses a broken
            // socket.
            sessionRef.current?.close();
            sessionRef.current = null;
            break;
        }
      },
      onClose: () => {
        sessionRef.current = null;
        setState((s) =>
          s === "listening" || s === "thinking" || s === "speaking"
            ? "idle"
            : s,
        );
      },
    });
    await session.connect(selectedId);
    sessionRef.current = session;
  }, [selectedId]);

  const handlePressStart = useCallback(async () => {
    // If we're recovering from an error, blow away whatever stale session
    // ref is hanging around so ensureConnected() actually reconnects.
    if (state === "error") {
      sessionRef.current?.close();
      sessionRef.current = null;
    }
    setErrMsg(null);
    setTranscript("");
    setState("listening");
    try {
      await ensureConnected();
      // Cut off any in-flight audio playback the moment the visitor speaks.
      playerRef.current?.flush();

      const cap = new MicCapture();
      captureRef.current = cap;
      turnStartedRef.current = true;
      await cap.start((chunk) => sessionRef.current?.sendAudio(chunk));
    } catch (e) {
      const friendly = friendlyError(e);
      setErrMsg(friendly);
      setState("error");
      sessionRef.current?.close();
      sessionRef.current = null;
    }
  }, [ensureConnected, state]);

  const handlePressEnd = useCallback(async () => {
    if (!turnStartedRef.current) return;
    turnStartedRef.current = false;
    try {
      await captureRef.current?.stop();
    } catch {
      // ignore
    }
    captureRef.current = null;
    sessionRef.current?.endTurn();
    setState("thinking");
  }, []);

  const handleInterrupt = useCallback(() => {
    // Visitor tapped the button while Gemini was speaking. Drop queued
    // audio so the next utterance doesn't play over their next question.
    playerRef.current?.flush();
    setState("idle");
  }, []);

  const currentArtwork = useMemo(
    () => artworks.find((x) => x.id === selectedId) ?? null,
    [artworks, selectedId],
  );

  return (
    <div className="min-h-[100dvh] flex flex-col">
      {/* Sticky header — keeps current artwork name visible while scrolling. */}
      <header className="sticky top-0 z-10 bg-cream/90 backdrop-blur border-b border-clay/15 px-5 pt-5 pb-3">
        <div className="max-w-md mx-auto">
          <p className="text-[10px] uppercase tracking-[0.2em] text-clay">
            ASU Museum · Carmen Lomas Garza
          </p>
          <h1 className="font-serif text-2xl mt-0.5 leading-snug truncate">
            {currentArtwork?.title ?? "Choose an artwork"}
          </h1>
          {currentArtwork && (
            <p className="text-xs text-clay mt-0.5">
              {currentArtwork.year || "n.d."}
              {currentArtwork.medium ? ` · ${currentArtwork.medium}` : ""}
            </p>
          )}
        </div>
      </header>

      {/* Scrollable content. Bottom padding leaves room for the action bar. */}
      <main className="flex-1 px-5 pt-4 pb-44 max-w-md mx-auto w-full">
        <section className="mb-5">
          <TranscriptStream text={transcript} />
        </section>

        <section>
          <ArtworkPicker
            artworks={artworks}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </section>

        {errMsg && (
          <div className="mt-4 text-sm text-terracotta bg-terracotta/10 rounded-xl px-3 py-2">
            {errMsg}
          </div>
        )}
      </main>

      {/* Sticky bottom action bar — talk button always reachable. */}
      <div className="fixed bottom-0 left-0 right-0 bg-gradient-to-t from-cream via-cream/95 to-cream/0 pt-6 pb-2 safe-bottom">
        <div className="max-w-md mx-auto flex justify-center">
          <PushToTalkButton
            state={state}
            disabled={!selectedId}
            onPressStart={handlePressStart}
            onPressEnd={handlePressEnd}
            onInterrupt={handleInterrupt}
          />
        </div>
      </div>
    </div>
  );
}
