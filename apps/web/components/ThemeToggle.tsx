"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

type Choice = "system" | "light" | "dark";
const ORDER: Choice[] = ["system", "light", "dark"];
const STORAGE_KEY = "tandem-theme";
const CHANGED = "tandem-theme-change";

export interface Theme {
  choice: Choice;
  effective: "light" | "dark";
  cycle: () => void;
}

// The stored choice is an external store: localStorage plus a same-tab change event.
function subscribeToChoice(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGED, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGED, onChange);
  };
}

function readChoice(): Choice {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system"; // storage can be unavailable (private mode)
  }
}

function writeChoice(choice: Choice): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Without storage the choice still applies until the next reload.
  }
  window.dispatchEvent(new Event(CHANGED));
}

function subscribeToSystem(onChange: () => void): () => void {
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function useTheme(): Theme {
  const choice = useSyncExternalStore(subscribeToChoice, readChoice, () => "system" as const);
  const systemDark = useSyncExternalStore(
    subscribeToSystem,
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
    () => false,
  );

  useEffect(() => {
    const root = document.documentElement;
    if (choice === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", choice);
  }, [choice]);

  const cycle = useCallback(() => writeChoice(ORDER[(ORDER.indexOf(readChoice()) + 1) % 3]), []);
  const effective = choice === "system" ? (systemDark ? "dark" : "light") : choice;
  return { choice, effective, cycle };
}

export function ThemeToggle({ theme }: { theme: Theme }) {
  return (
    <button type="button" onClick={theme.cycle} aria-label={`Theme: ${theme.choice}. Change theme`}>
      Theme: {theme.choice}
    </button>
  );
}
