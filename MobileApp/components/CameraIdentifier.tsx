"use client";

import { useEffect, useRef, useState } from "react";

import { identifyArtwork, type ArtworkInfo } from "@/lib/api";
import { CameraCapture } from "@/lib/camera";

type Stage =
  | { kind: "preview" }
  | { kind: "identifying" }
  | {
      kind: "matched";
      artworkId: string;
      title: string;
      confidence: number;
      reason: string;
    }
  | { kind: "no-match"; reason: string }
  | { kind: "error"; message: string };

export interface CameraIdentifierProps {
  open: boolean;
  artworks: ArtworkInfo[];
  onClose: () => void;
  /** Called when the visitor confirms the matched artwork. Closes the dialog. */
  onSelect: (artworkId: string) => void;
}

/** Friendlier mapping for getUserMedia DOMException names. */
function friendlyCamError(e: unknown): string {
  if (e instanceof DOMException) {
    if (e.name === "NotFoundError") {
      return "No camera detected. On a Mac mini, open this on your phone — desktop has no rear camera.";
    }
    if (e.name === "NotAllowedError") {
      return "Camera access blocked. Allow camera permission for this page.";
    }
    if (e.name === "NotReadableError") {
      return "Camera is busy in another app. Close it and try again.";
    }
    if (e.name === "OverconstrainedError") {
      return "Couldn't find a compatible camera mode. Try a different device.";
    }
  }
  return e instanceof Error ? e.message : String(e);
}

export function CameraIdentifier({
  open,
  artworks,
  onClose,
  onSelect,
}: CameraIdentifierProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const camRef = useRef<CameraCapture | null>(null);
  const [stage, setStage] = useState<Stage>({ kind: "preview" });

  // Spin the camera up when the dialog opens, tear down when it closes.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const cam = new CameraCapture();
    camRef.current = cam;
    setStage({ kind: "preview" });
    (async () => {
      try {
        if (!videoRef.current) return;
        await cam.start(videoRef.current);
        if (cancelled) await cam.stop();
      } catch (e) {
        setStage({ kind: "error", message: friendlyCamError(e) });
      }
    })();
    return () => {
      cancelled = true;
      cam.stop();
      camRef.current = null;
    };
  }, [open]);

  const handleShutter = async () => {
    if (!videoRef.current || !camRef.current) return;
    let jpegB64: string;
    try {
      jpegB64 = camRef.current.snapshot(videoRef.current);
    } catch (e) {
      setStage({ kind: "error", message: friendlyCamError(e) });
      return;
    }
    setStage({ kind: "identifying" });
    try {
      const result = await identifyArtwork(jpegB64);
      if (result.artwork_id) {
        const match = artworks.find((a) => a.id === result.artwork_id);
        setStage({
          kind: "matched",
          artworkId: result.artwork_id,
          title: match?.title ?? result.artwork_id,
          confidence: result.confidence,
          reason: result.reason,
        });
      } else {
        setStage({
          kind: "no-match",
          reason: result.reason || "No confident match. Try a clearer shot.",
        });
      }
    } catch (e) {
      setStage({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const handleConfirm = () => {
    if (stage.kind !== "matched") return;
    onSelect(stage.artworkId);
  };

  const handleRetake = () => {
    setStage({ kind: "preview" });
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black flex flex-col"
      role="dialog"
      aria-modal="true"
      aria-label="Identify artwork by camera"
    >
      <div className="relative flex-1 overflow-hidden">
        <video
          ref={videoRef}
          className="absolute inset-0 w-full h-full object-cover"
          playsInline
          muted
          autoPlay
        />

        {/* viewfinder reticle to suggest framing */}
        {stage.kind === "preview" && (
          <div
            aria-hidden
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
          >
            <div className="border-2 border-white/40 rounded-2xl w-3/4 max-w-[420px] aspect-[4/5]" />
          </div>
        )}

        {/* Top bar */}
        <div className="absolute top-0 left-0 right-0 flex items-center justify-between p-4 bg-gradient-to-b from-black/60 to-transparent text-white">
          <button
            type="button"
            onClick={onClose}
            className="text-sm font-medium px-3 py-1.5 rounded-full bg-white/15 backdrop-blur active:bg-white/25"
            aria-label="Close camera"
          >
            ← Close
          </button>
          <p className="text-xs uppercase tracking-widest opacity-80">
            Point at the artwork
          </p>
          <span className="w-[68px]" /> {/* spacer to balance back button */}
        </div>

        {/* Result overlays */}
        {stage.kind === "identifying" && (
          <Banner>
            <span className="dot bg-white" />
            <span className="dot bg-white" />
            <span className="dot bg-white" />
            <span className="ml-2">Identifying…</span>
          </Banner>
        )}

        {stage.kind === "matched" && (
          <Banner>
            <div className="flex flex-col items-center gap-1">
              <p className="text-[10px] uppercase tracking-widest opacity-80">
                Match · {(stage.confidence * 100).toFixed(0)}% confident
              </p>
              <p className="font-serif text-xl">{stage.title}</p>
              {stage.reason && (
                <p className="text-xs opacity-80 max-w-[80%] text-center">
                  {stage.reason}
                </p>
              )}
            </div>
          </Banner>
        )}

        {stage.kind === "no-match" && (
          <Banner>
            <div className="flex flex-col items-center gap-1">
              <p className="font-serif text-lg">No confident match</p>
              <p className="text-xs opacity-80 max-w-[80%] text-center">
                {stage.reason}
              </p>
            </div>
          </Banner>
        )}

        {stage.kind === "error" && (
          <Banner tone="error">
            <p className="text-sm max-w-[80%] text-center">{stage.message}</p>
          </Banner>
        )}
      </div>

      {/* Bottom action bar */}
      <div className="bg-black text-white px-6 pt-4 pb-6 safe-bottom">
        <div className="flex items-center justify-center gap-6">
          {stage.kind === "preview" && (
            <ShutterButton onClick={handleShutter} />
          )}

          {stage.kind === "identifying" && (
            <button
              disabled
              className="h-16 w-16 rounded-full bg-white/40 flex items-center justify-center"
            >
              <span className="dot bg-white" />
              <span className="dot bg-white" />
              <span className="dot bg-white" />
            </button>
          )}

          {stage.kind === "matched" && (
            <>
              <SecondaryAction onClick={handleRetake}>Retake</SecondaryAction>
              <PrimaryAction onClick={handleConfirm}>
                Use this artwork
              </PrimaryAction>
            </>
          )}

          {(stage.kind === "no-match" || stage.kind === "error") && (
            <>
              <SecondaryAction onClick={onClose}>Pick manually</SecondaryAction>
              <PrimaryAction onClick={handleRetake}>Try again</PrimaryAction>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Banner({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "error";
}) {
  return (
    <div className="absolute inset-x-0 bottom-0 p-6 flex items-center justify-center">
      <div
        className={[
          "px-5 py-3 rounded-2xl backdrop-blur-md text-white inline-flex items-center gap-2",
          tone === "error" ? "bg-terracotta/80" : "bg-black/60",
        ].join(" ")}
      >
        {children}
      </div>
    </div>
  );
}

function ShutterButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Capture photo"
      className="h-20 w-20 rounded-full border-4 border-white flex items-center justify-center active:scale-95 transition"
    >
      <span className="h-14 w-14 rounded-full bg-white" />
    </button>
  );
}

function PrimaryAction({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full bg-terracotta text-white px-6 py-3 font-medium active:bg-terracotta/90"
    >
      {children}
    </button>
  );
}

function SecondaryAction({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full bg-white/15 text-white px-5 py-3 font-medium active:bg-white/25"
    >
      {children}
    </button>
  );
}
