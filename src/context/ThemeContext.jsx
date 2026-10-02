import { useEffect, useState, createContext, useContext, useCallback } from 'react';

const ThemeContext = createContext({ theme: 'light', toggleTheme: () => {} });
const STORAGE_KEY = 'fet_theme';

function readInitialTheme() {
  if (typeof document === 'undefined') return 'light';
  if (document.documentElement.getAttribute('data-theme') === 'dark') return 'dark';
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dark' || saved === 'light') return saved;
  } catch (e) { /* private mode */ }
  return 'light';
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(readInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') root.setAttribute('data-theme', 'dark');
    else root.removeAttribute('data-theme');
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) { /* ignore */ }
  }, [theme]);

  // Follow the system setting only while the user has not made a choice.
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e) => {
      let hasChoice = false;
      try { hasChoice = !!localStorage.getItem(STORAGE_KEY); } catch (err) { hasChoice = false; }
      if (!hasChoice) setTheme(e.matches ? 'dark' : 'light');
    };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    return () => { if (mq.removeEventListener) mq.removeEventListener('change', onChange); };
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'));
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
