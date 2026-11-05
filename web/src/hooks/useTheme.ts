import { useCallback, useEffect, useState } from 'react'
import { browserStore, readStored, STORAGE_KEYS, writeStored } from '../api/settings'

export type ThemeChoice = 'system' | 'light' | 'dark'

const CHOICES: ThemeChoice[] = ['system', 'light', 'dark']

export function parseThemeChoice(value: string | null | undefined): ThemeChoice {
  return CHOICES.includes(value as ThemeChoice) ? (value as ThemeChoice) : 'system'
}

export function nextThemeChoice(current: ThemeChoice): ThemeChoice {
  return CHOICES[(CHOICES.indexOf(current) + 1) % CHOICES.length]
}

/** Applies the explicit theme as `data-theme` on <html>; "system" removes it and defers to the OS. */
export function useTheme(): { theme: ThemeChoice; cycleTheme: () => void } {
  const [theme, setTheme] = useState<ThemeChoice>(() => parseThemeChoice(readStored(browserStore(), STORAGE_KEYS.theme)))

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    writeStored(browserStore(), STORAGE_KEYS.theme, theme === 'system' ? '' : theme)
  }, [theme])

  const cycleTheme = useCallback(() => setTheme((current) => nextThemeChoice(current)), [])
  return { theme, cycleTheme }
}
