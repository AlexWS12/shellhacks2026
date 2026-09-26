/** Web configuration. Components read settings from here, never hard-code them. */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** OpenFreeMap vector styles (no API key). */
export const BASEMAP_STYLE_URL = {
  light: process.env.NEXT_PUBLIC_BASEMAP_STYLE_LIGHT ?? "https://tiles.openfreemap.org/styles/positron",
  dark: process.env.NEXT_PUBLIC_BASEMAP_STYLE_DARK ?? "https://tiles.openfreemap.org/styles/dark",
} as const;

/** Savannah River, where South Carolina meets Georgia. [lon, lat] */
export const SC_GA_BORDER = { center: [-81.45, 32.7] as [number, number], zoom: 6.6 };
export const WHOLE_US = { center: [-96.5, 38.5] as [number, number], zoom: 3.2 };

/** Replay speed for the "Replay" button (API accepts 1 to 10). */
export const REPLAY_SPEED = 4;
