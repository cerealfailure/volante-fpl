// ──────────────────────────────────────────────────────────
// The Gaffer — event-triggered coach popup.
//
// Usage:
//   import { gaffer } from '$lib/coach';
//   gaffer.say('BOWEN IS ON FIRE! HE PUNCHED ABOVE HIS WEIGHT.');
//
// The CoachPopup component (rendered in +layout.svelte) subscribes
// to this store and slides in whenever a message is pushed. It
// auto-hides after a few seconds, unless the user dismisses it
// or another message arrives first.
//
// Phases:
//   hidden   — nothing on screen
//   thinking — gaffer is rubbing his chin; 3 pulsing dots
//   speaking — message types out char-by-char
//
// The flow for every `say()` call is: hidden → thinking (350ms) →
// speaking (types) → hold (remainder of TTL) → hidden.
// ──────────────────────────────────────────────────────────

import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';

export type GafferPhase = 'hidden' | 'thinking' | 'speaking';

export type GafferState = {
  phase: GafferPhase;
  text: string;
  id: number; // incremented on every push so components know to retype
};

const initial: GafferState = { phase: 'hidden', text: '', id: 0 };
const state = writable<GafferState>(initial);

let hideTimer: ReturnType<typeof setTimeout> | null = null;
let thinkTimer: ReturnType<typeof setTimeout> | null = null;
let nextId = 1;

function clearTimers() {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
  if (thinkTimer) { clearTimeout(thinkTimer); thinkTimer = null; }
}

function show(text: string, ttlMs = 5200) {
  if (!browser) return;
  if (!text) return;
  clearTimers();
  const id = nextId++;
  // Enter thinking phase immediately
  state.set({ phase: 'thinking', text, id });
  // After the thinking beat, switch to speaking
  thinkTimer = setTimeout(() => {
    const current = get(state);
    if (current.id !== id) return; // superseded by a newer message
    state.set({ phase: 'speaking', text, id });
  }, 350);
  // Auto-hide after TTL
  hideTimer = setTimeout(() => {
    const current = get(state);
    if (current.id !== id) return;
    state.set({ phase: 'hidden', text: '', id });
  }, ttlMs);
}

function hide() {
  clearTimers();
  state.set({ ...get(state), phase: 'hidden', text: '' });
}

export const gaffer = {
  subscribe: state.subscribe,
  /** Pop the gaffer up with a message. Auto-hides after ~5s. */
  say: (text: string, ttlMs?: number) => show(text, ttlMs),
  /** Dismiss the popup immediately. */
  hide,
};

export const GAFFER_NAME = 'THE GAFFER';
