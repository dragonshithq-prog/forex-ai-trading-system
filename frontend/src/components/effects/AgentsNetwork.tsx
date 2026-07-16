'use client'

import { useEffect, useRef, memo } from 'react'

interface AgentNode {
  label: string
  color: string
  signal: 'buy' | 'sell' | 'neutral'
  confidence: number
}

const agents: AgentNode[] = [
  { label: 'Trend', color: '#3b82f6', signal: 'buy', confidence: 0.85 },
  { label: 'Momentum', color: '#8b5cf6', signal: 'buy', confidence: 0.72 },
  { label: 'RSI', color: '#10b981', signal: 'sell', confidence: 0.31 },
  { label: 'Bollinger', color: '#f59e0b', signal: 'buy', confidence: 0.64 },
  { label: 'Volume', color: '#ef4444', signal: 'sell', confidence: 0.28 },
  { label: 'Sentiment', color: '#06b6d4', signal: 'buy', confidence: 0.91 },
  { label: 'News', color: '#ec4899', signal: 'neutral', confidence: 0.50 },
  { label: 'Pattern', color: '#84cc16', signal: 'buy', confidence: 0.78 },
]

const centerX = 200
const centerY = 150
const radius = 110

function getSignalColor(signal: string, conf: number) {
  if (signal === 'buy') return `rgba(16, 185, 129, ${0.3 + conf * 0.5})`
  if (signal === 'sell') return `rgba(239, 68, 68, ${0.3 + conf * 0.5})`
  return 'rgba(148, 163, 184, 0.5)'
}

function getSignalGlow(signal: string) {
  if (signal === 'buy') return '0 0 12px rgba(16, 185, 129, 0.5)'
  if (signal === 'sell') return '0 0 12px rgba(239, 68, 68, 0.5)'
  return 'none'
}

export const AgentsNetwork = memo(function AgentsNetwork() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const raf = useRef(0)
  const time = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width = 400
    canvas.height = 300

    const animate = () => {
      time.current += 0.005
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // Draw connections
      for (let i = 0; i < agents.length; i++) {
        const angleA = (2 * Math.PI * i) / agents.length - Math.PI / 2
        const xA = centerX + radius * Math.cos(angleA)
        const yA = centerY + radius * Math.sin(angleA)

        for (let j = i + 1; j < agents.length; j++) {
          const angleB = (2 * Math.PI * j) / agents.length - Math.PI / 2
          const xB = centerX + radius * Math.cos(angleB)
          const yB = centerY + radius * Math.sin(angleB)

          const sameSignal = agents[i].signal === agents[j].signal
          const alpha = sameSignal ? 0.15 : 0.05
          const pulse = 0.5 + 0.5 * Math.sin(time.current * 2 + i + j)

          ctx.beginPath()
          ctx.moveTo(xA, yA)
          ctx.lineTo(xB, yB)
          ctx.strokeStyle = sameSignal
            ? `rgba(16, 185, 129, ${alpha * pulse})`
            : `rgba(239, 68, 68, ${alpha * pulse})`
          ctx.lineWidth = 1 + pulse * 0.5
          ctx.stroke()
        }
      }

      // Draw central consensus core
      const consensusGradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, 30)
      consensusGradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)')
      consensusGradient.addColorStop(0.5, 'rgba(59, 130, 246, 0.1)')
      consensusGradient.addColorStop(1, 'rgba(59, 130, 246, 0)')
      ctx.fillStyle = consensusGradient
      ctx.beginPath()
      ctx.arc(centerX, centerY, 30 + 5 * Math.sin(time.current * 2), 0, Math.PI * 2)
      ctx.fill()

      ctx.fillStyle = 'rgba(59, 130, 246, 0.6)'
      ctx.beginPath()
      ctx.arc(centerX, centerY, 4, 0, Math.PI * 2)
      ctx.fill()

      // Draw agent nodes
      for (let i = 0; i < agents.length; i++) {
        const agent = agents[i]
        const angle = (2 * Math.PI * i) / agents.length - Math.PI / 2
        const orbitOffset = 4 * Math.sin(time.current * 1.5 + i)
        const x = centerX + (radius + orbitOffset) * Math.cos(angle)
        const y = centerY + (radius + orbitOffset) * Math.sin(angle)

        const pulse = 1 + 0.15 * Math.sin(time.current * 3 + i * 1.2)
        const nodeRadius = 12 + agent.confidence * 8

        // Glow
        ctx.shadowColor = getSignalColor(agent.signal, 1)
        ctx.shadowBlur = 15

        // Node background
        const grad = ctx.createRadialGradient(x, y, 0, x, y, nodeRadius * pulse)
        grad.addColorStop(0, agent.color)
        grad.addColorStop(0.7, agent.color + 'aa')
        grad.addColorStop(1, agent.color + '00')
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.arc(x, y, nodeRadius * pulse, 0, Math.PI * 2)
        ctx.fill()

        ctx.shadowBlur = 0

        // Inner dot
        ctx.fillStyle = agent.color
        ctx.beginPath()
        ctx.arc(x, y, 4, 0, Math.PI * 2)
        ctx.fill()

        // Label
        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'
        ctx.font = '9px Inter, sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText(agent.label, x, y + nodeRadius * pulse + 12)
      }

      raf.current = requestAnimationFrame(animate)
    }

    raf.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf.current)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="w-full max-w-[400px] h-[300px] mx-auto"
      aria-label="AI Agents network visualization"
    />
  )
})
