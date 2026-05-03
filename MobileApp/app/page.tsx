"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ArtworkPicker } from "@/components/ArtworkPicker";
import { CameraIdentifier } from "@/components/CameraIdentifier";
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

const STORAGE_KEY = "asu-museum:selected-artwork";

function friendlyError(e: unknown): string {
  if (e instanceof DOMException) {
    if (e.name === "NotFoundError") {
      return "No microphone detected. Connect AirPods, a USB mic, or test on a phone.";
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

export default function Page() {
  const [artworks, setArtworks] = useState<ArtworkInfo[]>([]);
  const [artworksLoading, setArtworksLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [state, setState] = useState<TalkState>("idle");
  const [transcript, setTranscript] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [micLevel, setMicLevel] = useState(0);
  const [cameraOpen, setCameraOpen] = useState(false);

  const sessionRef = useRef<VoiceSession | null>(null);
  const captureRef = useRef<MicCapture | null>(null);
  const playerRef = useRef<StreamingPlayer | null>(null);
  const turnStartedRef = useRef(false);
  // True between handlePressStart and handlePressEnd. Lets the (async)
  // start path detect a release that arrived before mic capture was wired
  // up, so it can tear down whatever it set up instead of leaving the app
  // stuck listening forever.
  const isPressingRef = useRef(false);

  // --- Boot: load artworks + restore last-selected from localStorage. ---
  useEffect(() => {
    let cancelled = false;
    fetchArtworks()
      .then((list) => {
        if (cancelled) return;
        setArtworks(list);
        setArtworksLoading(false);

        // Prefer the last-used artwork if still in the list; else fall back
        // to alphabetical first.
        const stored =
          typeof window !== "undefined"
            ? window.localStorage.getItem(STORAGE_KEY)
            : null;
        const restored = stored && list.find((a) => a.id === stored)?.id;
        if (restored) {
          setSelectedId(restored);
        } else if (list.length > 0) {
          const first = [...list].sort((a, b) =>
            a.title.localeCompare(b.title, undefined, { sensitivity: "base" }),
          )[0];
          setSelectedId(first.id);
        }
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setArtworksLoading(false);
        setErrMsg(`Couldn't load artworks: ${e.message}. Backend at ${BACKEND_BASE_URL}?`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Persist selection so refreshes don't drop the visitor's place.
  useEffect(() => {
    if (selectedId && typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, selectedId);
    }
  }, [selectedId]);

  // Tear down on unmount.
  useEffect(() => {
    return () => {
      sessionRef.current?.close();
      captureRef.current?.stop();
      playerRef.current?.stop();
    };
  }, []);

  // Reset session when the artwork changes — system instruction is bound
  // at connect time, so a fresh socket gets the right artwork line.
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
    isPressingRef.current = true;

    // Recover from prior error: drop stale session so we reconnect cleanly.
    if (state === "error") {
      sessionRef.current?.close();
      sessionRef.current = null;
    }
    setErrMsg(null);
    // Cut off any in-flight playback the moment the visitor speaks (true
    // barge-in: works whether we were idle, speaking, or thinking).
    playerRef.current?.flush();
    setTranscript("");

    try {
      // Phase 1 — open the WebSocket. May take a few hundred ms first time.
      await ensureConnected();
      if (!isPressingRef.current) {
        // Released before the socket was ready. Nothing was sent to Gemini
        // yet (no startTurn), so just bail.
        return;
      }
      setState("listening");

      // Phase 2 — open the turn. From this point on, we owe Gemini a
      // matching activity_end no matter what.
      sessionRef.current?.startTurn();

      // Phase 3 — wire the mic. getUserMedia + AudioWorklet load can race
      // with a fast release; check before flipping turnStarted=true.
      const cap = new MicCapture();
      await cap.start({
        onChunk: (chunk) => sessionRef.current?.sendAudio(chunk),
        onLevel: (rms) => setMicLevel(rms),
      });
      if (!isPressingRef.current) {
        // Released during mic setup. Tear down silently and commit the
        // (mostly empty) turn so Gemini's session state stays consistent.
        try {
          await cap.stop();
        } catch {
          /* ignore */
        }
        setMicLevel(0);
        sessionRef.current?.endTurn();
        setState("thinking");
        return;
      }
      captureRef.current = cap;
      turnStartedRef.current = true;
    } catch (e) {
      setErrMsg(friendlyError(e));
      setState("error");
      sessionRef.current?.close();
      sessionRef.current = null;
    }
  }, [ensureConnected, state]);

  const handlePressEnd = useCallback(async () => {
    isPressingRef.current = false;
    // If the start path is still mid-setup, it will see the cleared
    // isPressingRef on its next checkpoint and tear itself down. Nothing
    // for us to do here.
    if (!turnStartedRef.current) return;
    turnStartedRef.current = false;
    try {
      await captureRef.current?.stop();
    } catch {
      // ignore
    }
    captureRef.current = null;
    setMicLevel(0);
    sessionRef.current?.endTurn();
    setState("thinking");
  }, []);

  // The button is disabled while the system is mid-response ("thinking")
  // so the visitor doesn't accidentally queue duplicate turns. NOT disabled
  // during "connecting" — the press is already in flight by then, and
  // disabling would drop the matching release event in PushToTalkButton.
  // Listening and speaking remain interactive (release / barge-in).
  const buttonDisabled = !selectedId || state === "thinking";

  // --- Desktop convenience: hold space bar to talk. ---
  useEffect(() => {
    const isTypingTarget = (t: EventTarget | null) =>
      t instanceof HTMLElement &&
      (t.tagName === "INPUT" ||
        t.tagName === "TEXTAREA" ||
        t.isContentEditable);

    const onDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      if (isTypingTarget(e.target)) return;
      // Mirror the button's disabled gate. Without this, space would
      // start a fresh turn while one is already mid-response, overlapping
      // turns the UI explicitly prevents via pointer.
      if (buttonDisabled) return;
      e.preventDefault();
      handlePressStart();
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      if (isTypingTarget(e.target)) return;
      handlePressEnd();
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, [handlePressStart, handlePressEnd, buttonDisabled]);

  const currentArtwork = useMemo(
    () => artworks.find((x) => x.id === selectedId) ?? null,
    [artworks, selectedId],
  );

  return (
    <div className="min-h-[100dvh] flex flex-col">
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

      <main className="flex-1 px-5 pt-4 pb-48 max-w-md mx-auto w-full">
        <section className="mb-5">
          <TranscriptStream text={transcript} state={state} />
        </section>

        <section>
          <ArtworkPicker
            artworks={artworks}
            selectedId={selectedId}
            onSelect={setSelectedId}
            loading={artworksLoading}
            onOpenCamera={() => setCameraOpen(true)}
          />
        </section>

        {errMsg && (
          <div className="mt-4 text-sm text-terracotta bg-terracotta/10 rounded-xl px-3 py-2">
            {errMsg}
          </div>
        )}
      </main>

      <div className="fixed bottom-0 left-0 right-0 bg-gradient-to-t from-cream via-cream/95 to-cream/0 pt-6 pb-3 safe-bottom">
        <div className="max-w-md mx-auto flex justify-center">
          <PushToTalkButton
            state={state}
            level={micLevel}
            disabled={buttonDisabled}
            onPressStart={handlePressStart}
            onPressEnd={handlePressEnd}
          />
        </div>
      </div>

      <CameraIdentifier
        open={cameraOpen}
        artworks={artworks}
        onClose={() => setCameraOpen(false)}
        onSelect={(id) => {
          setSelectedId(id);
          setCameraOpen(false);
        }}
      />
    </div>
  );
}
