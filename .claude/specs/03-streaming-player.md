# Spec: Streaming Player

## Overview
Turn the enriched library into something the user can actually watch. This feature adds
in-browser video playback for the local library: an adaptive streaming backend that plays
**any** container/codec the user owns (native byte-range for browser-friendly files,
ffmpeg **remux** for H.264-in-mkv, ffmpeg **transcode** for HEVC/4K/incompatible media),
VLC-style subtitles (embedded track extraction + sidecar files + load-your-own), resume
("Continue Watching"), and a Netflix-style browse UI (hero, poster rows, detail, player)
to reach it. Before this feature the library is browseable via API only; after it, the
user opens Nestflix, picks a title, and it plays with the right codec path chosen
automatically and their position remembered.

## Depends on
- **01 Library Scanner** — `media_files`, `movies`, `shows`, `episodes` rows and
  `container`/`path` columns.
- **02 TMDB Enrichment** — posters/backdrops/metadata + `/api/images` and `/api/discovery`
  for the browse UI.

## Network / environment constraints
- The user's real library is ~100% `.mkv`, mixed codecs (x264 1080p **and** HEVC/H.265 4K),
  varied audio. They expect "plays like VLC" for everything.
- **ffmpeg + ffprobe** (Gyan build 8.1.1) are installed via winget and on PATH for new
  processes. They are an **optional system dependency** — the app must degrade gracefully
  if absent (native-compatible files still play; everything else surfaces a clear
  "ffmpeg required" state rather than crashing).
- Browsers natively play mp4/m4v (H.264+AAC) and webm; they do **not** reliably play the
  mkv container, HEVC, or AC3/DTS audio — hence the remux/transcode tiers.

## API routes
All under the existing `/api/playback` router unless noted. Profile-scoped routes take a
`profile_id` (the active local profile).
- `GET  /api/playback/{media_file_id}/info` — play decision + metadata for the player:
  `{play_mode: 'direct'|'remux'|'transcode'|'unavailable', container, video_codec,
  audio_codec, duration_seconds, width, height, subtitles: [...], title, kind,
  ffmpeg_available}`. Local action.
- `GET  /api/playback/{media_file_id}/stream?t=<seconds>` — stream the video. `direct`
  honors HTTP `Range` (206 partial content, true seek). `remux`/`transcode` pipe a
  fragmented MP4 from ffmpeg starting at `t` seconds (seek = client re-requests with a new
  `t`). Local action.
- `GET  /api/playback/{media_file_id}/subtitles` — list available subtitle tracks
  (embedded via ffprobe + sidecar `.srt/.vtt` next to the file).
- `GET  /api/playback/{media_file_id}/subtitles/{track}.vtt` — return one track as WebVTT
  (ffmpeg-extract embedded text subs, or convert a sidecar `.srt`→`.vtt`). Path-guarded.
- `GET  /api/playback/progress?profile_id=&media_file_id=` — current resume position for a
  title (`{position_seconds, duration_seconds, completed}` or empty).
- `POST /api/playback/progress` — upsert resume position; body
  `{profile_id, media_file_id, position_seconds, duration_seconds, event?}`. Writes
  `watch_progress` and a `watch_events` row (`start|progress|finish|abandon`). Local action.
- `GET  /api/playback/continue?profile_id=` — replace the stub; real "Continue Watching"
  (in-progress, not-completed titles joined to movie/episode display data).

## Database changes
**No schema changes.** `watch_progress` (position/duration/completed, `UNIQUE(profile_id,
media_file_id)`) and `watch_events` already exist from the base schema. We only add `db.py`
helpers and a small in-memory probe cache (no table).

## Backend modules
- **Create `backend/media_probe.py`** — ffmpeg/ffprobe wrapper:
  - `ffmpeg_available() -> bool`, `ffprobe_path()/ffmpeg_path()` via `config` + `shutil.which`.
  - `probe(path) -> MediaInfo` (video_codec, audio_codec, duration, width, height, subtitle
    streams) using `ffprobe -v quiet -print_format json -show_format -show_streams`.
    Results cached in-process keyed by (path, mtime).
  - `decide_play_mode(container, video_codec, audio_codec) -> 'direct'|'remux'|'transcode'`.
    Browser-safe container+codec → `direct`; mkv/avi/mov with H.264 + safe audio → `remux`
    (copy video, AAC audio if needed); HEVC/other → `transcode` (H.264+AAC). No ffmpeg and
    not natively safe → `unavailable`.
- **Create `backend/streaming.py`** — the streaming engine:
  - `range_response(path, request, content_type) -> Response` — HTTP Range/byte-serving
    (200 full or 206 partial with `Content-Range`/`Accept-Ranges`), reused image-route
    path-containment guard.
  - `ffmpeg_stream(path, mode, start_seconds) -> StreamingResponse` — spawn ffmpeg to
    fragmented MP4 on stdout (`-movflags frag_keyframe+empty_moov+default_base_moof`),
    `-ss <start>` before `-i` for fast seek; `remux` = `-c:v copy -c:a aac`, `transcode` =
    `-c:v libx264 -preset veryfast -crf 23 -c:a aac`. Stream stdout in chunks; **kill the
    ffmpeg process on client disconnect** (background task / try-finally).
  - `subtitle_tracks(path)` + `extract_subtitle_vtt(path, track)` /
    `sidecar_to_vtt(path)` — list & return WebVTT; skip image-based subs (PGS/VOBSUB) that
    can't convert to text.
- **Modify `backend/config.py`** — add `ffmpeg_path`, `ffprobe_path` (env override),
  `ffmpeg_enabled` detection, and a `transcode` tunable or two. Secrets/paths from `.env`.
- **Modify `backend/db.py`** — add (conn-first, parameterized, caller commits):
  `get_media_file(conn, id)`, `get_watch_progress(conn, profile_id, media_file_id)`,
  `upsert_watch_progress(conn, profile_id, media_file_id, position, duration, completed)`,
  `record_watch_event(conn, profile_id, media_file_id, event, pct)`,
  `get_continue_watching(conn, profile_id)` (join `watch_progress`→`media_files`→
  movies/episodes, exclude completed, newest first).
- **Modify `backend/routes/playback.py`** — replace stubs with the routes above; parse
  input → call helper → return; `HTTPException` on bad ids / missing files / ffmpeg-needed.

## Frontend
Pull in just enough Netflix-style UI to browse and play (the fuller UI is feature 05).
- **Create:**
  - `frontend/src/api/client.ts` additions (types + calls) — keep all URLs here, incl.
    `streamUrl()`, `subtitleUrl()`, `imageUrl()` helpers.
  - `frontend/src/components/NavBar.tsx`, `PosterRow.tsx`, `PosterCard.tsx`, `Hero.tsx`,
    `VideoPlayer.tsx`, `ProfileGate.tsx`.
  - `frontend/src/pages/Home.tsx` (hero + rows: Continue Watching, My Movies, My Shows,
    Trending, New Releases), `Detail.tsx` (backdrop, metadata, Play/Resume, episode list),
    `Player.tsx` (full-screen `VideoPlayer`).
  - `frontend/src/profile.tsx` — minimal active-profile context (persisted to
    `localStorage`) so progress calls have a `profile_id`.
- **Modify:** `frontend/src/main.tsx` / `App.tsx` — wire `BrowserRouter` + routes:
  `/` Home, `/title/:kind/:id` Detail, `/watch/:mediaFileId` Player; gate on a chosen
  profile. `frontend/src/styles.css` — rows/cards/player styles using existing theme vars.
- **VideoPlayer**: native `<video>`; on `info` choose `direct` (set `src` to `/stream`,
  rely on native seek) vs `remux`/`transcode` (set `src` to `/stream?t=`, map seeks to a
  new `t` and reload); seek to saved resume position on load; POST progress every ~10s and
  on pause/`visibilitychange`/`pagehide` (via `navigator.sendBeacon`); subtitle `<track>`
  menu (server tracks + "Add subtitle file…" using `URL.createObjectURL`); clear
  error/"install ffmpeg" messaging for `unavailable`.

## Files to change / create
- Create: `backend/media_probe.py`, `backend/streaming.py`,
  `tests/test_streaming.py`, `tests/test_media_probe.py`, `tests/test_playback.py`,
  and the frontend files listed above.
- Change: `backend/config.py`, `backend/db.py`, `backend/routes/playback.py`,
  `backend/main.py` (only if a new mount/import is needed),
  `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/api/client.ts`,
  `frontend/src/styles.css`, `frontend/package.json` (if a dep is added),
  `requirements.txt` (note the ffmpeg system dependency in a comment).

## New dependencies
- **System (not pip/npm):** `ffmpeg` + `ffprobe` — already installed via winget
  (Gyan.FFmpeg 8.1.1). Optional; documented in CLAUDE.md/README.
- **pip:** none required (subprocess + stdlib). 
- **npm:** none for the chosen progressive-MP4 transport (native `<video>`). If HLS is
  later adopted, `hls.js` would be added then — out of scope here.

## Rules for implementation
- DB logic lives in `backend/db.py` — **no SQL in route handlers**. Parameterized (`?`/`:x`)
  only.
- All TMDB access stays in `backend/tmdb.py`; the browse UI uses existing
  `/api/discovery` + `/api/images`.
- Frontend talks to the backend only through `frontend/src/api/`. No raw `fetch`/hardcoded
  URLs in components.
- ffmpeg/ffprobe paths come from `config.py` (env-overridable) — never hardcode absolute
  user paths.
- **Path-containment guard** every filesystem access (stream + subtitle sidecar): the
  resolved file must be inside a configured library path; 403/404 otherwise.
- Always **terminate ffmpeg** on client disconnect to avoid orphaned processes.
- Backend I/O stays `async`; long ffmpeg reads use streaming/threads so the event loop
  isn't blocked.
- Errors raise `HTTPException`, never bare strings.

## Definition of done
- [ ] `GET /api/playback/{id}/info` returns the correct `play_mode` per file: a real
      H.264 mp4 → `direct`; an H.264 mkv → `remux`; an HEVC file → `transcode`; and
      `unavailable` (with `ffmpeg_available:false`) when ffmpeg is missing and the file
      isn't natively playable.
- [ ] `GET /api/playback/{id}/stream` on a direct file honors `Range`: returns **206**
      with correct `Content-Range`/`Accept-Ranges` and the requested byte slice.
- [ ] A `.mkv` from the real library **plays in the browser** (remux or transcode path),
      and seeking works (via `?t=` reload for the ffmpeg tiers).
- [ ] Subtitles: embedded text tracks are listed and toggle on/off as WebVTT; a sidecar
      `.srt` is converted and shown; the user can load a local subtitle file in the player.
- [ ] Resume: playing past a few seconds then reopening the title seeks to the saved
      position; finishing marks it `completed`; `GET /api/playback/continue` lists
      in-progress (non-completed) titles with poster/title/position.
- [ ] ffmpeg processes are killed on disconnect (no orphaned `ffmpeg.exe` after closing
      the tab).
- [ ] Netflix-style UI: Home shows a hero + poster rows (incl. Continue Watching); a poster
      opens Detail; Detail’s Play/Resume opens the Player and starts playback.
- [ ] Graceful degradation: with ffmpeg removed/disabled, the app still loads, browses, and
      plays native-compatible files; non-playable titles show a clear message, no crash.
- [ ] `pytest` passes, including new tests for range (206) streaming, play-mode decision
      (mocked ffprobe), progress upsert + continue-watching, srt→vtt conversion, and the
      ffmpeg-absent path. No SQL in `routes/playback.py`.
</content>
</invoke>
