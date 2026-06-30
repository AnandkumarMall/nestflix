// Streaming video player with adaptive play modes, resume, and VLC-style subtitles.
//
// Play modes (decided by the backend):
//   - direct    : native <video> seeking over an HTTP byte-range stream.
//   - remux/transcode : ffmpeg pipes a fresh stream starting at an input offset, so the
//     timeline has no seekable index. We track an absolute position = streamStart +
//     video.currentTime, and "seeking" means reloading the stream at a new offset.
//
// Custom controls (not native) unify both modes: the scrub bar maps to currentTime for
// direct play and to a stream reload for the ffmpeg modes. The chrome (top bar, center
// play, control bar, settings menus) mirrors the Netflix-style nestflix.html reference.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, streamUrl, subtitleUrl, type PlaybackInfo } from '../api/client';

interface Props {
  mediaFileId: number;
  profileId: number;
  /** Fallback title/subtitle (the backend's playback info is preferred when present). */
  title?: string;
  subtitle?: string;
}

interface ExtraTrack {
  label: string;
  src: string;
}

type SubtitlePosition = 'bottom' | 'center' | 'top';

const SAVE_INTERVAL_SECONDS = 10;
const CONTROLS_HIDE_MS = 3000;

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  return `${h > 0 ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}

/** Human runtime, e.g. 134 min -> "2h 14m". */
function formatRuntime(seconds: number): string {
  if (!isFinite(seconds) || seconds <= 0) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function VideoPlayer({
  mediaFileId,
  profileId,
  title: fallbackTitle,
  subtitle: fallbackSubtitle,
}: Props) {
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const hideControlsRef = useRef<number>();

  const [info, setInfo] = useState<PlaybackInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [streamStart, setStreamStart] = useState(0); // ffmpeg input offset (seconds)
  const [position, setPosition] = useState(0); // absolute position (seconds)
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [activeTextTrack, setActiveTextTrack] = useState<string>('off');
  const [extraTracks, setExtraTracks] = useState<ExtraTrack[]>([]);
  const [subtitlePosition, setSubtitlePosition] = useState<SubtitlePosition>('bottom');

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [volume, setVolume] = useState(1); // 0..1
  const [muted, setMuted] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [hover, setHover] = useState<{ pct: number; time: number } | null>(null);
  const [subtitleMenuOpen, setSubtitleMenuOpen] = useState(false);

  const resumeRef = useRef(0); // resume position to apply once (direct mode)
  const resumeAppliedRef = useRef(false);
  const lastSavedRef = useRef(0);
  const playAfterLoadRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const ffmpegMode = info?.play_mode === 'remux' || info?.play_mode === 'transcode';

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

        if (pi.play_mode === 'unavailable') {
          setError(
            pi.ffmpeg_available
              ? "This file's format can't be played in the browser."
              : 'This file needs ffmpeg on the server to play. Install ffmpeg, then reload.'
          );
        } else if (pi.play_mode === 'remux' || pi.play_mode === 'transcode') {
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
      if (!info || info.play_mode === 'unavailable') return;
      const body = {
        profile_id: profileId,
        media_file_id: mediaFileId,
        position_seconds: position,
        duration_seconds: duration || info.duration_seconds || 0,
        ...(event ? { event } : {}),
      };
      if (beacon && typeof navigator.sendBeacon === 'function') {
        api.saveProgressBeacon(body);
      } else {
        api.saveProgress(body).catch(() => undefined);
      }
    },
    [info, profileId, mediaFileId, position, duration]
  );

  // Save on tab hide / unload so we don't lose the position.
  useEffect(() => {
    const onHide = () => saveProgress(undefined, true);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') onHide();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onHide);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', onHide);
      saveProgress(); // save when navigating away from the player
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveProgress]);

  // --- Volume / mute syncing ---------------------------------------------
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.volume = volume;
    v.muted = muted;
  }, [volume, muted]);

  // --- Fullscreen ---------------------------------------------------------
  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      void el.requestFullscreen?.();
    } else {
      void document.exitFullscreen?.();
    }
  }, []);

  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  // --- Auto-hiding controls ----------------------------------------------
  const revealControls = useCallback(() => {
    setControlsVisible(true);
    if (hideControlsRef.current) window.clearTimeout(hideControlsRef.current);
    hideControlsRef.current = window.setTimeout(() => {
      // Keep controls up while a menu is open or the video is paused.
      setControlsVisible((prev) => {
        if (!videoRef.current || videoRef.current.paused) return prev;
        if (subtitleMenuOpen) return prev;
        return false;
      });
    }, CONTROLS_HIDE_MS);
  }, [subtitleMenuOpen]);

  // --- Video element event wiring ----------------------------------------
  const onLoadedMetadata = () => {
    const v = videoRef.current;
    if (!v) return;
    v.volume = volume;
    v.muted = muted;
    if (!ffmpegMode) {
      if (!isFinite(duration) || duration === 0) setDuration(v.duration);
      if (!resumeAppliedRef.current && resumeRef.current > 0) {
        v.currentTime = resumeRef.current;
        resumeAppliedRef.current = true;
      }
    }
    applySubtitlePosition(subtitlePosition);
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
    saveProgress('finish');
    setPlaying(false);
  };

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
    revealControls();
  }, [revealControls]);

  const seekTo = useCallback(
    (target: number) => {
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
    },
    [duration, ffmpegMode, playing]
  );

  // --- Subtitles ----------------------------------------------------------
  // Reposition native cues (top/center/bottom) by setting their line value.
  const applySubtitlePosition = (pos: SubtitlePosition) => {
    const tracks = videoRef.current?.textTracks;
    if (!tracks) return;
    const line = pos === 'top' ? 0 : pos === 'center' ? 8 : undefined;
    for (let i = 0; i < tracks.length; i++) {
      const cues = tracks[i].cues;
      if (!cues) continue;
      for (let j = 0; j < cues.length; j++) {
        const cue = cues[j] as VTTCue;
        if (line === undefined) {
          cue.snapToLines = true;
          cue.line = 'auto';
        } else {
          cue.snapToLines = true;
          cue.line = line;
        }
      }
    }
  };

  // Toggle which subtitle track is showing (native TextTrack API).
  const selectTextTrack = (value: string) => {
    setActiveTextTrack(value);
    const tracks = videoRef.current?.textTracks;
    if (!tracks) return;
    for (let i = 0; i < tracks.length; i++) {
      tracks[i].mode = tracks[i].label === value ? 'showing' : 'disabled';
    }
    applySubtitlePosition(subtitlePosition);
  };

  const changeSubtitlePosition = (pos: SubtitlePosition) => {
    setSubtitlePosition(pos);
    applySubtitlePosition(pos);
  };

  const addSubtitleFile = async (file: File) => {
    // Browsers only accept WebVTT for <track>, so convert .srt on the fly.
    let text = await file.text();
    if (file.name.toLowerCase().endsWith('.srt')) {
      text = 'WEBVTT\n\n' + text.replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, '$1.$2');
    }
    const src = URL.createObjectURL(new Blob([text], { type: 'text/vtt' }));
    setExtraTracks((prev) => [...prev, { label: file.name, src }]);
    // Auto-enable the freshly added track.
    setTimeout(() => selectTextTrack(file.name), 0);
  };

  // --- Keyboard shortcuts (Netflix-style) --------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const v = videoRef.current;
      if (!v) return;
      switch (e.code) {
        case 'Space':
        case 'KeyK':
          e.preventDefault();
          togglePlay();
          break;
        case 'ArrowRight':
          seekTo(position + 5);
          revealControls();
          break;
        case 'ArrowLeft':
          seekTo(position - 5);
          revealControls();
          break;
        case 'ArrowUp':
          e.preventDefault();
          setVolume((vol) => Math.min(1, +(vol + 0.1).toFixed(2)));
          setMuted(false);
          revealControls();
          break;
        case 'ArrowDown':
          e.preventDefault();
          setVolume((vol) => Math.max(0, +(vol - 0.1).toFixed(2)));
          revealControls();
          break;
        case 'KeyF':
          toggleFullscreen();
          break;
        case 'KeyM':
          setMuted((m) => !m);
          revealControls();
          break;
        case 'Escape':
          if (!document.fullscreenElement) navigate(-1);
          break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [position, togglePlay, seekTo, toggleFullscreen, revealControls, navigate]);

  if (error) {
    return (
      <div className="player-error">
        <p>{error}</p>
        {info && (
          <p className="player-error-detail">
            {info.container?.toUpperCase()} · {info.video_codec ?? '?'} / {info.audio_codec ?? '?'}
          </p>
        )}
      </div>
    );
  }

  if (!info) return <div className="player-loading">Loading…</div>;

  const subtitleTracks = info.subtitles ?? [];
  const src = streamUrl(mediaFileId, ffmpegMode ? streamStart : 0);
  const hasAnySubtitle = subtitleTracks.length > 0 || extraTracks.length > 0;

  // Prefer backend display metadata; fall back to props passed via route state.
  const displayTitle = info.title || fallbackTitle || 'Now Playing';
  const displaySubtitle =
    info.kind === 'episode' && info.season != null
      ? `S${info.season}:E${info.episode}${info.episode_title ? ` "${info.episode_title}"` : ''}`
      : fallbackSubtitle ||
        [info.year ? String(info.year) : null, formatRuntime(duration)].filter(Boolean).join(' · ');

  const progressPct = duration > 0 ? (position / duration) * 100 : 0;

  return (
    <div
      ref={containerRef}
      className={`player ${isFullscreen ? 'is-fullscreen' : ''} ${
        controlsVisible ? 'controls-on' : 'controls-off'
      }`}
      onMouseMove={revealControls}
      onMouseLeave={() => playing && setControlsVisible(false)}
    >
      <div
        className="player-video-container"
        onClick={(e) => {
          if (e.target === e.currentTarget) togglePlay();
        }}
      >
        <video
          ref={videoRef}
          className="player-video"
          src={src}
          autoPlay
          onLoadedMetadata={onLoadedMetadata}
          onTimeUpdate={onTimeUpdate}
          onPlay={() => {
            setPlaying(true);
            revealControls();
          }}
          onPause={() => {
            setPlaying(false);
            setControlsVisible(true);
          }}
          onEnded={onEnded}
          onClick={togglePlay}
          crossOrigin="anonymous"
          // key forces a reload of the element when the ffmpeg offset changes.
          key={src}
        >
          {subtitleTracks.map((t) => (
            <track
              key={t.track}
              kind="subtitles"
              label={t.label}
              srcLang={t.language ?? 'und'}
              src={subtitleUrl(mediaFileId, t.track)}
            />
          ))}
          {extraTracks.map((t) => (
            <track key={t.src} kind="subtitles" label={t.label} src={t.src} />
          ))}
        </video>

        {/* Center play / pause */}
        <div className="player-center">
          <button className="center-play" onClick={togglePlay} aria-label="Play/Pause">
            {playing ? (
              <svg width="36" height="36" viewBox="0 0 24 24" fill="white">
                <path d="M6 4h4v16H6zm8 0h4v16h-4z" />
              </svg>
            ) : (
              <svg width="36" height="36" viewBox="0 0 24 24" fill="white">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Top overlay: back + title/subtitle */}
      <div className={`player-top ${controlsVisible ? 'visible' : ''}`}>
        <button className="player-back" onClick={() => navigate(-1)} aria-label="Back">
          ←
        </button>
        <div>
          <div className="player-title">{displayTitle}</div>
          {displaySubtitle && <div className="player-subtitle">{displaySubtitle}</div>}
        </div>
      </div>

      {/* Control bar */}
      <div className={`controls ${controlsVisible ? 'visible' : ''}`}>
        <div
          className="progress-area"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            seekTo(((e.clientX - rect.left) / rect.width) * (duration || 0));
          }}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            setHover({ pct: pct * 100, time: pct * (duration || 0) });
          }}
          onMouseLeave={() => setHover(null)}
        >
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          {hover && (
            <div className="progress-time" style={{ left: `${hover.pct}%` }}>
              {formatTime(hover.time)}
            </div>
          )}
        </div>

        <div className="controls-row">
          <div className="controls-left">
            <button className="ctrl-btn" onClick={togglePlay} title={playing ? 'Pause' : 'Play'}>
              {playing ? (
                <svg viewBox="0 0 24 24" fill="white">
                  <path d="M6 4h4v16H6zm8 0h4v16h-4z" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="white">
                  <path d="M8 5v14l11-7z" />
                </svg>
              )}
            </button>

            <button className="ctrl-btn" onClick={() => seekTo(position - 10)} title="Back 10s">
              <svg viewBox="0 0 24 24" fill="white">
                <path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z" />
              </svg>
            </button>

            <button className="ctrl-btn" onClick={() => seekTo(position + 10)} title="Forward 10s">
              <svg viewBox="0 0 24 24" fill="white">
                <path d="M13 6v12l8.5-6L13 6zm-.5 6L4 6v12l8.5-6z" />
              </svg>
            </button>

            <div className="volume-container">
              <button
                className="ctrl-btn"
                onClick={() => setMuted((m) => !m)}
                title={muted ? 'Unmute' : 'Mute'}
              >
                {muted || volume === 0 ? (
                  <svg viewBox="0 0 24 24" fill="white">
                    <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73 4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" fill="white">
                    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
                  </svg>
                )}
              </button>
              <input
                type="range"
                className="volume-slider"
                min={0}
                max={100}
                value={muted ? 0 : Math.round(volume * 100)}
                onChange={(e) => {
                  const val = Number(e.target.value) / 100;
                  setVolume(val);
                  setMuted(val === 0);
                }}
              />
            </div>

            <span className="time-display">
              {formatTime(position)} / {formatTime(duration)}
            </span>
          </div>

          <div className="controls-right">
            {/* Subtitles / captions */}
            <div className="settings-anchor">
              <button
                className={`ctrl-btn ${activeTextTrack !== 'off' ? 'active' : ''}`}
                onClick={() => setSubtitleMenuOpen((o) => !o)}
                title="Subtitles & captions"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </button>

              {subtitleMenuOpen && (
                <div className="settings-menu show">
                  <div className="settings-label">Subtitles</div>
                  <div
                    className={`settings-item ${activeTextTrack === 'off' ? 'active' : ''}`}
                    onClick={() => selectTextTrack('off')}
                  >
                    Off {activeTextTrack === 'off' && <span>✓</span>}
                  </div>

                  {hasAnySubtitle && <div className="settings-divider" />}

                  {subtitleTracks.map((t) => (
                    <div
                      key={t.track}
                      className={`settings-item ${activeTextTrack === t.label ? 'active' : ''}`}
                      onClick={() => selectTextTrack(t.label)}
                    >
                      {t.label} {activeTextTrack === t.label && <span>✓</span>}
                    </div>
                  ))}
                  {extraTracks.map((t) => (
                    <div
                      key={t.src}
                      className={`settings-item ${activeTextTrack === t.label ? 'active' : ''}`}
                      onClick={() => selectTextTrack(t.label)}
                    >
                      {t.label} {activeTextTrack === t.label && <span>✓</span>}
                    </div>
                  ))}

                  <div className="settings-divider" />
                  <div className="settings-label">Position</div>
                  {(['bottom', 'center', 'top'] as SubtitlePosition[]).map((pos) => (
                    <div
                      key={pos}
                      className={`settings-item ${subtitlePosition === pos ? 'active' : ''}`}
                      onClick={() => changeSubtitlePosition(pos)}
                    >
                      {pos === 'bottom' ? 'Bottom (Default)' : pos[0].toUpperCase() + pos.slice(1)}
                      {subtitlePosition === pos && <span>✓</span>}
                    </div>
                  ))}

                  <div className="settings-divider" />
                  <div className="settings-item" onClick={() => fileInputRef.current?.click()}>
                    ＋ Add subtitle file…
                  </div>
                </div>
              )}
            </div>

            {/* Add subtitle file (hidden input, opened from the menu) */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".vtt,.srt"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) addSubtitleFile(f);
                e.target.value = '';
              }}
            />

            {/* Fullscreen */}
            <button
              className="ctrl-btn"
              onClick={toggleFullscreen}
              title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? (
                <svg viewBox="0 0 24 24" fill="white">
                  <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="white">
                  <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>

      {ffmpegMode && (
        <p className="player-mode-note">
          {info.play_mode === 'transcode' ? 'Transcoding' : 'Remuxing'} · {info.video_codec}{' '}
          {info.width ? `${info.width}×${info.height}` : ''}
        </p>
      )}
    </div>
  );
}
