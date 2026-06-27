// Full-screen playback page. Resolves the media file id from the route and the active
// profile from context, then hands off to VideoPlayer.

import { useNavigate, useParams } from "react-router-dom";
import VideoPlayer from "../components/VideoPlayer";
import { useProfile } from "../profile";

export default function Player() {
  const { mediaFileId } = useParams<{ mediaFileId: string }>();
  const { activeProfile } = useProfile();
  const navigate = useNavigate();

  const id = Number(mediaFileId);
  if (!mediaFileId || Number.isNaN(id)) {
    return <div className="page-error">Invalid media id.</div>;
  }
  if (!activeProfile) {
    return <div className="page-error">Choose a profile to start watching.</div>;
  }

  return (
    <div className="player-page">
      <button className="player-back" onClick={() => navigate(-1)}>
        ‹ Back
      </button>
      <VideoPlayer mediaFileId={id} profileId={activeProfile.id} />
    </div>
  );
}
