'use client'

import { useEffect, useState, useRef } from 'react'

export function MarketPulse() {
  const [bars, setBars] = useState<number[]>(Array.from({ length: 40 }, () => 2))
  const raf = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    const update = () => {
      setBars(prev => {
        const next = [...prev]
        next.shift()
        next.push(Math.random() * 60 + 2)
        return next
      })
      raf.current = setTimeout(update, 200 + Math.random() * 400)
    }
    raf.current = setTimeout(update, 200)
    return () => clearTimeout(raf.current)
  }, [])

  return (
    <div className="flex items-end gap-[2px] h-8" aria-hidden="true">
      {bars.map((h, i) => (
        <div
          key={i}
          className="w-[3px] rounded-full transition-all duration-200"
          style={{
            height: `${h}%`,
            background: `linear-gradient(to top, hsl(var(--primary) / 0.3), hsl(var(--primary) / 0.8))`,
          }}
        />
      ))}
    </div>
  )
}
