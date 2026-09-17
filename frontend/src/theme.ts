import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark'

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggle: () => void
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme
}

export const useTheme = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'light',
      setTheme: (theme) => {
        apply(theme)
        set({ theme })
      },
      toggle: () => get().setTheme(get().theme === 'light' ? 'dark' : 'light'),
    }),
    {
      name: 'prompilot.theme',
      onRehydrateStorage: () => (state) => apply(state?.theme ?? 'light'),
    },
  ),
)

/** Per-theme values that canvas charts need as literals (CSS variables don't reach ECharts). */
export const CHART_THEMES: Record<Theme, { text: string; line: string; tooltipBg: string; tooltipLine: string; tooltipText: string; series: string[] }> = {
  light: {
    text: '#74777f',
    line: '#e5e3dc',
    tooltipBg: '#ffffff',
    tooltipLine: '#cfcdc4',
    tooltipText: '#17181a',
    series: ['#c8541a', '#0969da', '#1a7f37', '#8250df', '#bf3989', '#0e8a8a', '#9a6700', '#cf222e', '#57606a', '#1f6feb'],
  },
  dark: {
    text: '#80848d',
    line: '#262930',
    tooltipBg: '#1e2025',
    tooltipLine: '#363a43',
    tooltipText: '#ececee',
    series: ['#f0883e', '#58a6ff', '#3fb950', '#d2a8ff', '#f778ba', '#56d4dd', '#e3b341', '#ff7b72', '#a5d6ff', '#79c0ff'],
  },
}

export const THRESHOLD_COLORS: Record<Theme, Record<'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'purple', string>> = {
  light: { green: '#1a7f37', yellow: '#9a6700', orange: '#c8541a', red: '#cf222e', blue: '#0969da', purple: '#8250df' },
  dark: { green: '#3fb950', yellow: '#d29922', orange: '#f0883e', red: '#f47067', blue: '#58a6ff', purple: '#d2a8ff' },
}
