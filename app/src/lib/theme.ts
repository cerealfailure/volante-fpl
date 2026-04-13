import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type Theme = 'clean' | 'pixel';

const stored = browser ? (localStorage.getItem('volante-theme') as Theme) || 'clean' : 'clean';

export const theme = writable<Theme>(stored);

theme.subscribe((value) => {
  if (browser) {
    document.documentElement.setAttribute('data-theme', value);
    localStorage.setItem('volante-theme', value);
  }
});
