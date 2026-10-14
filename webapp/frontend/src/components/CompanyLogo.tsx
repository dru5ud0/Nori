import { useEffect, useState } from 'react'

type CompanyLogoProps = {
  name?: string
  domain?: string
  logoUrl?: string
  className?: string
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return (parts.slice(0, 2).map(part => part[0]).join('') || '?').toUpperCase()
}

export function CompanyLogo({ name = '', domain = '', logoUrl = '', className = '' }: CompanyLogoProps) {
  const src = logoUrl || (domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128` : '')
  const [failed, setFailed] = useState(false)

  useEffect(() => setFailed(false), [src])

  return <div className={`grid shrink-0 place-items-center overflow-hidden rounded-xl border-2 border-foreground bg-white font-mono text-xs font-black text-foreground shadow-[2px_2px_0_#111] ${className}`} aria-label={`${name || 'Company'} logo`}>
    {src && !failed
      ? <img src={src} alt="" className="h-full w-full object-contain p-1.5" onError={() => setFailed(true)} />
      : <span aria-hidden="true">{initials(name || domain)}</span>}
  </div>
}
