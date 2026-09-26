"use client";

import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";

import { BASEMAP_STYLE_URL, SC_GA_BORDER, WHOLE_US } from "@/lib/config";

interface Props {
  theme: "light" | "dark";
  showIntro: boolean;
  onRun: () => void;
  onReplay: () => void;
}

export function MapView({ theme, showIntro, onRun, onReplay }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const latestTheme = useRef(theme); // read when the map finishes loading
  const appliedTheme = useRef<"light" | "dark" | null>(null);
  useEffect(() => {
    latestTheme.current = theme;
  });

  useEffect(() => {
    let cancelled = false;
    void import("maplibre-gl").then(({ default: maplibregl }) => {
      if (cancelled || container.current === null) return;
      const { Map, NavigationControl } = maplibregl;
      appliedTheme.current = latestTheme.current;
      const instance = new Map({
        container: container.current,
        style: BASEMAP_STYLE_URL[latestTheme.current],
        center: SC_GA_BORDER.center,
        zoom: SC_GA_BORDER.zoom,
        attributionControl: { compact: true },
      });
      instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
      instance.getCanvas().setAttribute(
        "aria-label",
        "Map of the South Carolina and Georgia border. Use arrow keys to pan, plus and minus to zoom.",
      );
      map.current = instance;
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    if (map.current && theme !== appliedTheme.current) {
      map.current.setStyle(BASEMAP_STYLE_URL[theme]);
      appliedTheme.current = theme;
    }
  }, [theme]);

  const fly = (view: { center: [number, number]; zoom: number }) =>
    map.current?.flyTo({ ...view, essential: false });

  return (
    <section className="mapwrap" aria-label="Map">
      <div ref={container} className="map" />
      <div className="mapctl">
        <button type="button" onClick={() => fly(SC_GA_BORDER)}>
          SC–GA border
        </button>
        <button type="button" onClick={() => fly(WHOLE_US)}>
          Whole US
        </button>
      </div>
      {showIntro && (
        <div className="overlay">
          <div className="card">
            <h2>Two utilities. One river. Separate plans.</h2>
            <p>
              Tandem reads Dominion Energy South Carolina&apos;s and Georgia Power&apos;s public
              transmission plans, places each project, and finds pairs under 25 miles apart.
            </p>
            <div className="actions">
              <button type="button" className="primary" onClick={onRun}>
                Run pipeline
              </button>
              <button type="button" onClick={onReplay}>
                Replay recorded run
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
