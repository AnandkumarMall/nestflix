// Streaming video player with adaptive play modes, resume, and VLC-style subtitles.
//
// Play modes (decided by the backend):
//   - direct    : native <video> seeking over an HTTP byte-range stream.
//   - remux/transcode : ffmpeg pipes a fresh stream starting at an input offset, so the
//     timeline has no seekable index. We track an absolute position = streamStart +
//     video.currentTime, and "seeking" means reloading the stream at a new offset.
//
// Custom controls (not native) unify both modes: the scrub bar maps to currentTime for
// direct play and to a stream reload for the ffmpeg modes.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  streamUrl,
  subtitleUrl,
  type PlaybackInfo,
} from "../api/client";

interface Props {
  mediaFileId: number;
  profileId: number;
}

interface ExtraTrack {
  label: string;
  src: string;
}

const SAVE_INTERVAL_SECONDS = 10;

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "0:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

export default function VideoPlayer({ mediaFileId, profileId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [info, setInfo] = useState<PlaybackInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [streamStart, setStreamStart] = useState(0); // ffmpeg input offset (seconds)
  const [position, setPosition] = useState(0); // absolute position (seconds)
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [activeTextTrack, setActiveTextTrack] = useState<string>("off");
  const [extraTracks, setExtraTracks] = useState<ExtraTrack[]>([]);

  const resumeRef = useRef(0); // resume position to apply once (direct mode)
  const resumeAppliedRef = useRef(false);
  const lastSavedRef = useRef(0);
  const playAfterLoadRef = useRef(false);

  const ffmpegMode =
    info?.play_mode === "remux" || info?.play_mode === "transcode";

  // --- Load playback info + saved resume position -------------------------
  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    setError(null);
    setStreamStart(0);
    setPosition(0);
    resumeAppliedRef.current = false;
    lastSavedRef.current = 0;

    Promise.all([
      api.playbackInfo(mediaFileId),
      api.readProgress(profileId, mediaFileId).catch(() => null),
    ])
      .then(([pi, prog]) => {
        if (cancelled) return;
        setInfo(pi);
        setDuration(pi.duration_seconds ?? 0);
        const resume = prog && !prog.completed ? prog.position_seconds : 0;
        resumeRef.current = resume;

        if (pi.play_mode === "unavailable") {
          setError(
            pi.ffmpeg_available
              ? "This file's format can't be played in the browser."
              : "This file needs ffmpeg on the server to play. Install ffmpeg, then reload.",
          );
        } else if (pi.play_mode === "remux" || pi.play_mode === "transcode") {
          // ffmpeg modes resume by starting the stream at the saved offset.
          setStreamStart(resume);
          setPosition(resume);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });

    return () => {
      cancelled = true;
    };
  }, [mediaFileId, profileId]);

  // --- Progress persistence ----------------------------------------------
  const saveProgress = useCallback(
    (event?: string, beacon = false) => {
      if (!info || info.play_mode === "unavailable") return;
      const body = {
        profile_id: profileId,
        media_file_id: mediaFileId,
        position_seconds: position,
        duration_seconds: duration || info.duration_seconds || 0,
        ...(event ? { event } : {}),
      };
      if (beacon && navigator.sendBeacon) {
        navigator.sendBeacon(
          "/api/playback/progress",
          new Blob([JSON.stringify(body)], { type: "application/json" }),
        );
      } else {
        api.saveProgress(body).catch(() => undefined);
      }
    },
    [info, profileId, mediaFileId, position, duration],
  );

  // Save on tab hide / unload so we don't lose the position.
  useEffect(() => {
    const onHide = () => saveProgress(undefined, true);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") onHide();
    });
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      saveProgress(); // save when navigating away from the player
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveProgress]);

  // --- Video element event wiring ----------------------------------------
  const onLoadedMetadata = () => {
    const v = videoRef.current;
    if (!v) return;
    if (!ffmpegMode) {
      if (!isFinite(duration) || duration === 0) setDuration(v.duration);
      if (!resumeAppliedRef.current && resumeRef.current > 0) {
        v.currentTime = resumeRef.current;
        resumeAppliedRef.current = true;
      }
    }
    if (playAfterLoadRef.current) {
      playAfterLoadRef.current = false;
      void v.play();
    }
  };

  const onTimeUpdate = () => {
    const v = videoRef.current;
    if (!v) return;
    const abs = ffmpegMode ? streamStart + v.currentTime : v.currentTime;
    setPosition(abs);
    if (abs - lastSavedRef.current >= SAVE_INTERVAL_SECONDS) {
      lastSavedRef.current = abs;
      saveProgress();
    }
  };

  const onEnded = () => {
    saveProgress("finish");
    setPlaying(false);
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  };

  const seekTo = (target: number) => {
    const v = videoRef.current;
    if (!v) return;
    const clamped = Math.max(0, Math.min(target, duration || target));
    if (ffmpegMode) {
      // Restart the ffmpeg stream at the new offset; play once it has loaded.
      playAfterLoadRef.current = !v.paused || playing;
      setStreamStart(clamped);
      setPosition(clamped);
    } else {
      v.currentTime = clamped;
    }
  };

  // Toggle which subtitle track is showing (native TextTrack API).
  const selectTextTrack = (value: string) => {
    setActiveTextTrack(value);
    const tracks = videoRef.current?.textTracks;
    if (!tracks) return;
    for (let i = 0; i < tracks.length; i++) {
      tracks[i].mode = tracks[i].label === value ? "showing" : "disabled";
    }
  };

  const addSubtitleFile = async (file: File) => {
    // Browsers only accept WebVTT for <track>, so convert .srt on the fly.
    let text = await file.text();
    if (file.name.toLowerCase().endsWith(".srt")) {
      text =
        "WEBVTT\n\n" +
        text.replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, "$1.$2");
    }
    const src = URL.createObjectURL(new Blob([text], { type: "text/vtt" }));
    setExtraTracks((prev) => [...prev, { label: file.name, src }]);
  };

  if (error) {
    return (
      <div className="player-error">
        <p>{error}</p>
        {info && (
          <p className="player-error-detail">
            {info.container?.toUpperCase()} · {info.video_codec ?? "?"} /{" "}
            {info.audio_codec ?? "?"}
          </p>
        )}
      </div>
    );
  }

  if (!info) return <div className="player-loading">Loading…</div>;

  const subtitleTracks = info.subtitles ?? [];
  const src = streamUrl(mediaFileId, ffmpegMode ? streamStart : 0);

  return (
    <div className="player">
      <video
        ref={videoRef}
        className="player-video"
        src={src}
        autoPlay
        onLoadedMetadata={onLoadedMetadata}
        onTimeUpdate={onTimeUpdate}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={onEnded}
        crossOrigin="anonymous"
        // key forces a reload of the element when the ffmpeg offset changes.
        key={src}
      >
        {subtitleTracks.map((t) => (
          <track
            key={t.track}
            kind="subtitles"
            label={t.label}
            srcLang={t.language ?? "und"}
            src={subtitleUrl(mediaFileId, t.track)}
          />
        ))}
        {extraTracks.map((t) => (
          <track key={t.src} kind="subtitles" label={t.label} src={t.src} />
        ))}
      </video>

      <div className="player-controls">
        <button className="player-btn" onClick={togglePlay}>
          {playing ? "❚❚" : "►"}
        </button>
        <span className="player-time">{formatTime(position)}</span>
        <input
          className="player-seek"
          type="range"
          min={0}
          max={duration || 0}
          step={1}
          value={Math.min(position, duration || position)}
          onChange={(e) => seekTo(Number(e.target.value))}
        />
        <span className="player-time">{formatTime(duration)}</span>

        <label className="player-subs">
          CC
          <select
            value={activeTextTrack}
            onChange={(e) => selectTextTrack(e.target.value)}
          >
            <option value="off">Off</option>
            {subtitleTracks.map((t) => (
              <option key={t.track} value={t.label}>
                {t.label}
              </option>
            ))}
            {extraTracks.map((t) => (
              <option key={t.src} value={t.label}>
                {t.label}
              </option>
            ))}
          </select>
        </label>

        <label className="player-btn player-addsub" title="Add subtitle file">
          ＋Sub
          <input
            type="file"
            accept=".vtt,.srt"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) addSubtitleFile(f);
            }}
          />
        </label>
      </div>

      {ffmpegMode && (
        <p className="player-mode-note">
          {info.play_mode === "transcode" ? "Transcoding" : "Remuxing"} ·{" "}
          {info.video_codec} {info.width ? `${info.width}×${info.height}` : ""}
        </p>
      )}
    </div>
  );
}
