'use client'

import { useEffect, useRef, useCallback } from 'react'

const AudioCtx = typeof window !== 'undefined'
  ? (window.AudioContext || (window as any).webkitAudioContext)
  : null

let _ctx: AudioContext | null = null

function getCtx() {
  if (!AudioCtx) return null
  if (!_ctx) _ctx = new AudioCtx()
  if (_ctx.state === 'suspended') _ctx.resume()
  return _ctx
}

function playTone(freq: number, duration: number, type: OscillatorType, volume: number) {
  const ctx = getCtx()
  if (!ctx) return
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = type
  osc.frequency.value = freq
  gain.gain.setValueAtTime(volume, ctx.currentTime)
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(ctx.currentTime)
  osc.stop(ctx.currentTime + duration)
}

export function useTradingSounds() {
  const playTrade = useCallback(() => {
    playTone(880, 0.15, 'sine', 0.08)
    setTimeout(() => playTone(1320, 0.1, 'sine', 0.06), 60)
  }, [])

  const playAlert = useCallback(() => {
    playTone(660, 0.2, 'square', 0.06)
    setTimeout(() => playTone(880, 0.2, 'square', 0.06), 150)
    setTimeout(() => playTone(1100, 0.25, 'square', 0.06), 300)
  }, [])

  const playError = useCallback(() => {
    playTone(220, 0.3, 'sawtooth', 0.05)
    setTimeout(() => playTone(180, 0.4, 'sawtooth', 0.05), 200)
  }, [])

  const playSignal = useCallback(() => {
    playTone(520, 0.1, 'sine', 0.04)
    setTimeout(() => playTone(780, 0.1, 'sine', 0.04), 100)
    setTimeout(() => playTone(1040, 0.15, 'sine', 0.04), 200)
  }, [])

  return { playTrade, playAlert, playError, playSignal }
}

export function AudioManager({ enabled = true }: { enabled?: boolean }) {
  const inited = useRef(false)

  useEffect(() => {
    if (!enabled || inited.current) return
    const handler = () => {
      getCtx()
      document.removeEventListener('click', handler)
    }
    document.addEventListener('click', handler)
    inited.current = true
    return () => document.removeEventListener('click', handler)
  }, [enabled])

  return null
}
