'use client'

import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Trophy, Star, TrendingUp, Zap } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

interface Achievement {
  id: string
  title: string
  description: string
  icon: 'trophy' | 'star' | 'trending' | 'zap'
}

const icons = { trophy: Trophy, star: Star, trending: TrendingUp, zap: Zap }

export function AchievementToast() {
  const [achievement, setAchievement] = useState<Achievement | null>(null)
  const [visible, setVisible] = useState(false)

  const show = useCallback((a: Achievement) => {
    setAchievement(a)
    setVisible(true)
    setTimeout(() => setVisible(false), 4000)
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<Achievement>
      show(custom.detail)
    }
    window.addEventListener('show-achievement', handler as EventListener)
    return () => window.removeEventListener('show-achievement', handler as EventListener)
  }, [show])

  const Icon = achievement ? icons[achievement.icon] : null

  return (
    <AnimatePresence>
      {visible && achievement && (
        <motion.div
          initial={{ opacity: 0, y: 50, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -20, scale: 0.9 }}
          transition={{ type: 'spring', damping: 20, stiffness: 300 }}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-4 bg-card border border-border rounded-xl p-4 shadow-2xl max-w-sm"
        >
          <div className="relative">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-yellow-400/20 to-orange-400/20 flex items-center justify-center">
              {Icon && <Icon className="w-6 h-6 text-yellow-400" />}
            </div>
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: [0, 1.5, 1] }}
              transition={{ delay: 0.2, duration: 0.5 }}
              className="absolute -top-1 -right-1 w-4 h-4 bg-yellow-400 rounded-full flex items-center justify-center"
            >
              <Star className="w-2.5 h-2.5 text-black" />
            </motion.div>
          </div>
          <div>
            <p className="text-sm font-bold text-foreground">{achievement.title}</p>
            <p className="text-xs text-muted-foreground">{achievement.description}</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
