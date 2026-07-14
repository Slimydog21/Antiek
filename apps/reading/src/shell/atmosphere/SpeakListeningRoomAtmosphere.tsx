import environment from "./speak_listening_room_environment_v1.webp";

/** Decorative Speak-world atmosphere; recording and oral-history state stay HTML. */
export function SpeakListeningRoomAtmosphere() {
  return (
    <div aria-hidden="true" data-speak-listening-room-atmosphere="" className="pointer-events-none absolute inset-0 overflow-hidden">
      <img src={environment} alt="" draggable={false} decoding="async" className="absolute inset-0 h-full w-full object-cover object-center" />
    </div>
  );
}

export default SpeakListeningRoomAtmosphere;
