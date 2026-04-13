// Approximate PL kit primary/secondary colors for use in
// jerseys, exposure bars, and player chips. Fallback = neutral.

type KitColors = { primary: string; secondary: string };

export const TEAM_KITS: Record<string, KitColors> = {
  ARS: { primary: '#ef0107', secondary: '#ffffff' },
  AVL: { primary: '#670e36', secondary: '#95bfe5' },
  BHA: { primary: '#0057b8', secondary: '#ffffff' },
  BOU: { primary: '#da291c', secondary: '#000000' },
  BRE: { primary: '#e30613', secondary: '#ffffff' },
  BUR: { primary: '#6c1d45', secondary: '#99d6ea' },
  CHE: { primary: '#034694', secondary: '#ffffff' },
  CRY: { primary: '#1b458f', secondary: '#c4122e' },
  EVE: { primary: '#003399', secondary: '#ffffff' },
  FUL: { primary: '#000000', secondary: '#ffffff' },
  IPS: { primary: '#0033a0', secondary: '#ffffff' },
  LEE: { primary: '#1d428a', secondary: '#ffffff' },
  LEI: { primary: '#003090', secondary: '#fdbe11' },
  LIV: { primary: '#c8102e', secondary: '#ffffff' },
  LUT: { primary: '#f78f1e', secondary: '#1d2f5f' },
  MCI: { primary: '#6cabdd', secondary: '#ffffff' },
  MUN: { primary: '#da291c', secondary: '#fbe122' },
  NEW: { primary: '#241f20', secondary: '#ffffff' },
  NFO: { primary: '#dd0000', secondary: '#ffffff' },
  SHU: { primary: '#ee2737', secondary: '#000000' },
  SOU: { primary: '#d71920', secondary: '#ffffff' },
  TOT: { primary: '#132257', secondary: '#ffffff' },
  WHU: { primary: '#7a263a', secondary: '#1bb1e7' },
  WOL: { primary: '#fdb913', secondary: '#231f20' },
};

export function kitFor(short: string | undefined | null): KitColors {
  if (!short) return { primary: '#56776b', secondary: '#e8fff1' };
  return TEAM_KITS[short] ?? { primary: '#56776b', secondary: '#e8fff1' };
}
