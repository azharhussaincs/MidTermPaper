/**
 * Suggests one-tap answers for the interviewer's latest question.
 *
 * The backend asks questions in free text, so the answer format is inferred from the wording
 * (the questionnaire guide's phrasing: "how often…over the last two weeks", "from 0 to 10", …).
 * Tapping a chip sends it immediately; the patient can always type a fuller answer instead.
 */

export type QuickReplyKind = 'frequency' | 'scale' | 'hours' | 'quality' | 'impact' | 'yesno' | 'opener'

export interface QuickReplySet {
  kind: QuickReplyKind
  label: string
  options: { label: string; value: string }[]
}

export const FREQUENCY_OPTIONS = ['Not at all', 'Several days', 'More than half the days', 'Nearly every day']

function scale(from: number, to: number, suffix: string): QuickReplySet['options'] {
  return Array.from({ length: to - from + 1 }, (_, i) => {
    const n = from + i
    return { label: String(n), value: `${n} out of ${to}${suffix}` }
  })
}

const asOptions = (labels: string[]) => labels.map((label) => ({ label, value: label }))

/**
 * The part of the message that asks: the last sentence ending in "?" (with any bracketed options).
 * Preamble is ignored, so "you said more than half the days. Could you tell me more?" is an open
 * question, not a frequency item.
 */
function askedPart(message: string): string {
  const end = message.lastIndexOf('?')
  if (end < 0) return ''
  const before = message.slice(0, end)
  // Start after the last sentence end that is not inside the question's own brackets.
  const start = Math.max(before.lastIndexOf('. '), before.lastIndexOf('! '), before.lastIndexOf('\n'))
  let asked = message.slice(start + 1, end + 1).trim()
  // "...how often...? (Not at all, several days, ...?)": the options belong to the previous question.
  if (asked.startsWith('(')) {
    const prev = message.slice(0, message.lastIndexOf('(')).trim()
    asked = `${askedPart(prev)} ${asked}`
  }
  return asked
}

export function detectQuickReplies(question: string | null | undefined): QuickReplySet | null {
  if (!question) return null
  const text = askedPart(question).toLowerCase()
  if (!text) return null

  // Open questions first: "How have you been feeling over the last two weeks?" mentions the time
  // window but is not a frequency item, and frequency chips there get stored as a screening answer.
  if (/how have you been feeling|how are you feeling/.test(text)) {
    return {
      kind: 'opener',
      label: 'Start with a few words, or type your own',
      options: asOptions(['Mostly okay', 'Up and down', "I've been struggling", 'Not sure how to describe it']),
    }
  }
  if (/how often|several days|nearly every day|more than half/.test(text)) {
    return { kind: 'frequency', label: 'How often, over the last 2 weeks', options: asOptions(FREQUENCY_OPTIONS) }
  }
  const range = /\b(0|1)\b[^.?]{0,24}\bto\s*10\b|out of 10|\/10/.exec(text)
  if (range) {
    const from = range[1] === '1' ? 1 : 0
    return { kind: 'scale', label: `Choose a number from ${from} to 10`, options: scale(from, 10, '') }
  }
  if (/how many hours/.test(text)) {
    return {
      kind: 'hours',
      label: 'Typical night',
      options: asOptions(['Under 4 hours', '4–5 hours', '6 hours', '7 hours', '8 hours', '9+ hours']),
    }
  }
  if (/quality of your sleep|sleep quality|rate your sleep/.test(text)) {
    return { kind: 'quality', label: 'Sleep quality', options: asOptions(['Very poor', 'Poor', 'Fair', 'Good', 'Very good']) }
  }
  if (/(affect|impact)\w*[^?]{0,60}\b(work|stud)/.test(text)) {
    return {
      kind: 'impact',
      label: 'Impact on daily life',
      options: asOptions(['Not at all', 'A little', 'Moderately', 'Severely']),
    }
  }
  if (/^(do|did|have|has|are|is|were|was) you\b/.test(text) && !/anything else/.test(text)) {
    return { kind: 'yesno', label: 'Quick answer', options: asOptions(['Yes', 'No', 'Sometimes', 'Not sure']) }
  }
  return null
}
