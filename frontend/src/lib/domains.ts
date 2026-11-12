import { Activity, Briefcase, CloudSun, MessageCircleHeart, Moon, Wind, type LucideIcon } from 'lucide-react'
import type { AssessmentDomain } from '../types/api'

export interface DomainMeta {
  short: string
  title: string
  icon: LucideIcon
}

export const DOMAIN_META: Record<AssessmentDomain, DomainMeta> = {
  mood: { short: 'Mood', title: 'Mood & Emotional Wellbeing', icon: CloudSun },
  stress: { short: 'Stress', title: 'Stress Levels', icon: Activity },
  sleep: { short: 'Sleep', title: 'Sleep Patterns', icon: Moon },
  anxiety: { short: 'Anxiety', title: 'Anxiety Experiences', icon: Wind },
  functioning: { short: 'Daily Life', title: 'Daily Functioning', icon: Briefcase },
  concerns: { short: 'Goals', title: 'Personal Concerns & Goals', icon: MessageCircleHeart },
}
