import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function safeHostname(url: unknown, fallback = 'Application') {
  try {
    const value = String(url || '').trim()
    return value ? new URL(value).hostname.replace(/^www\./, '') || fallback : fallback
  } catch {
    return fallback
  }
}
