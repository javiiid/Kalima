import { useCallback, useEffect, useState } from 'react'

/**
 * Density and motion, applied to `<html>` so every page follows them.
 *
 * ## Why these are not in `useTheme`
 *
 * Theme has a pre-paint requirement and a `matchMedia` subscription; density
 * and motion are a stored string and a stored flag. Keeping them separate keeps
 * `useTheme` readable, and both are still applied before first paint through
 * `applyStoredAppearance()` in `main.tsx`.
 *
 * ## What compact may not touch
 *
 * Compact trims spacing only. Persian joins its letters, so the type size and
 * the line height are the two things that must not move: at 1.7 the descenders
 * of one line already touch the ascenders of the next. The CSS in `ui.css`
 * enforces that; this hook only sets the attribute.
 */
export type Density = 'comfortable' | 'compact'

export const DENSITY_KEY = 'kalima-density'
export const MOTION_KEY = 'kalima-motion'

function readDensity(): Density {
  try {
    return localStorage.getItem(DENSITY_KEY) === 'compact' ? 'compact' : 'comfortable'
  } catch {
    return 'comfortable'
  }
}

function readAnimations(): boolean {
  try {
    return localStorage.getItem(MOTION_KEY) !== 'off'
  } catch {
    return true
  }
}

function applyDensity(density: Density): void {
  document.documentElement.dataset.density = density
}

function applyMotion(animations: boolean): void {
  document.documentElement.dataset.motion = animations ? 'on' : 'off'
}

/** Runs before the first paint, beside `applyStoredTheme()`. */
export function applyStoredAppearance(): void {
  applyDensity(readDensity())
  applyMotion(readAnimations())
}

export function useDensity() {
  const [density, setDensityState] = useState<Density>(readDensity)

  useEffect(() => {
    applyDensity(density)
  }, [density])

  const setDensity = useCallback((next: Density) => {
    setDensityState(next)
    try {
      localStorage.setItem(DENSITY_KEY, next)
    } catch {
      // Private mode: the choice lives in memory for this visit.
    }
  }, [])

  return { density, setDensity }
}

export function useMotion() {
  const [animations, setAnimationsState] = useState<boolean>(readAnimations)

  useEffect(() => {
    applyMotion(animations)
  }, [animations])

  const setAnimations = useCallback((next: boolean) => {
    setAnimationsState(next)
    try {
      localStorage.setItem(MOTION_KEY, next ? 'on' : 'off')
    } catch {
      // Private mode: the choice lives in memory for this visit.
    }
  }, [])

  return { animations, setAnimations }
}