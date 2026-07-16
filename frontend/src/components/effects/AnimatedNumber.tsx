'use client'

import { useEffect, useRef, useState } from 'react'
import { useInView } from 'react-intersection-observer'

interface AnimatedNumberProps {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
  duration?: number
  className?: string
  formatter?: (v: number) => string
}

export function AnimatedNumber({
  value,
  decimals = 2,
  prefix = '',
  suffix = '',
  duration = 1.2,
  className = '',
  formatter,
}: AnimatedNumberProps) {
  const { ref, inView } = useInView({ triggerOnce: true, threshold: 0.1 })
  const [display, setDisplay] = useState(0)
  const startTime = useRef(0)
  const raf = useRef(0)
  const startVal = useRef(0)

  useEffect(() => {
    if (!inView) return

    const start = display
    const startTime = performance.now()

    const animate = (now: number) => {
      const elapsed = (now - startTime) / 1000
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = start + (value - start) * eased
      setDisplay(current)

      if (progress < 1) {
        raf.current = requestAnimationFrame(animate)
      }
    }

    raf.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf.current)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, inView, duration])

  if (formatter) {
    return <span ref={ref} className={className}>{formatter(display)}</span>
  }

  return (
    <span ref={ref} className={className}>
      {prefix}{display.toFixed(decimals)}{suffix}
    </span>
  )
}
