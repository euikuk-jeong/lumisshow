const KEY = 'lumisshow_theme';

export const THEMES = [
  { id: 'dark',  label: 'Dark',       bg: '#0d0d18', accent: '#7c8cf8' },
  { id: 'oled',  label: 'OLED Black', bg: '#000000', accent: '#818cf8' },
  { id: 'slate', label: 'Slate',      bg: '#0c0e12', accent: '#7c8cf8' },
  { id: 'warm',  label: 'Warm Dark',  bg: '#0e0c0a', accent: '#e8a44a' },
  { id: 'light', label: 'Light',      bg: '#f0f2f5', accent: '#5c6bc0' },
  { id: 'sepia', label: 'Sepia',      bg: '#f5f0e6', accent: '#8b6f47' },
  { id: 'sky',   label: 'Sky',        bg: '#eef2f7', accent: '#3b82f6' },
  { id: 'rose',  label: 'Rose',       bg: '#fdf2f4', accent: '#db2777' },
];

export const getTheme = () => localStorage.getItem(KEY) || 'dark';

export const setTheme = t => {
  localStorage.setItem(KEY, t);
  document.documentElement.dataset.theme = t;
};
