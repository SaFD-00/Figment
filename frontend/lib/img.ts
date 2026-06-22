import type { SyntheticEvent } from "react";

// Hide a thumbnail whose asset file 404s (the DB row outlived its file on disk) so a missing
// output renders as an empty slot instead of the browser's broken-image icon.
export function hideBrokenImage(e: SyntheticEvent<HTMLImageElement>) {
  e.currentTarget.style.visibility = "hidden";
}
