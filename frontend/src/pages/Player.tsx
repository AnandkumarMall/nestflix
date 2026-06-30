// Full-screen playback page. Resolves the media file id from the route and the active
// profile from context, then hands off to VideoPlayer.

import { useParams, useLocation } from 'react-router-dom';
import VideoPlayer from '../components/VideoPlayer';
import { useProfile } from '../profile';

interface LocationState {
  title?: string;
  subtitle?: string;
}

export default function Player() {
  const { mediaFileId } = useParams<{ mediaFileId: string }>();
  const { activeProfile } = useProfile();
  const location = useLocation();
  const state = (location.state || {}) as LocationState;

  const id = Number(mediaFileId);
  if (!mediaFileId || Number.isNaN(id)) {
    return <div className="page-error">Invalid media id.</div>;
  }
  if (!activeProfile) {
    return <div className="page-error">Choose a profile to start watching.</div>;
  }

  return (
    <div className="player-page">
      <VideoPlayer
        mediaFileId={id}
        profileId={activeProfile.id}
        title={state.title}
        subtitle={state.subtitle}
      />
    </div>
  );
}
