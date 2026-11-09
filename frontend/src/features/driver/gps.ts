/** GPS stays off until the backend exposes per-driver, version-bound notice/ack,
 * official duty and active-trip authorization. Market GPS_NOTICE is insufficient.
 * No device point is collected or queued through this module. */
export type GpsCollectionStatus = "off_unverified";
export function collectionStatus(): GpsCollectionStatus { return "off_unverified"; }
export function startTracking(_tripId: number): () => void {
  void _tripId;
  return () => undefined;
}
