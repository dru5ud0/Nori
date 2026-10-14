import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { api } from '../api'
import { Search, Globe, Plus, ExternalLink, Loader2, Send } from 'lucide-react'
import { toast } from 'sonner'
import { QuickApplyDialog } from '../components/QuickApplyDialog'

export function LinkedIn() {
  const [keywords, setKeywords] = useState('')
  const [location, setLocation] = useState('')
  const [pages, setPages] = useState(1)
  const [detail, setDetail] = useState(0)
  const [cards, setCards] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [harvesting, setHarvesting] = useState(false)
  const [selected, setSelected] = useState<any | null>(null)
  const queryClient = useQueryClient()
  const resolvedCards = cards.filter(card => {
    try { return card.url && !new URL(card.url).hostname.toLowerCase().endsWith('linkedin.com') }
    catch { return false }
  })

  const handleSearch = async () => {
    if (!keywords.trim()) return
    setLoading(true)
    try {
      const data = await api.linkedinSearch(keywords, location, pages, detail)
      if (data.ok) setCards(data.cards || [])
    } catch (e: any) {
      toast.error(e.message)
    }
    setLoading(false)
  }

  const handleHarvest = async () => {
    const entries = resolvedCards
      .map(c => ({ jobId: c.jobId, title: c.title, url: c.url }))
    if (entries.length === 0) return
    setHarvesting(true)
    try {
      const result = await api.linkedinHarvest(entries)
      queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
      toast.success(`Imported ${result.created}; skipped ${result.skipped}`)
    } catch (e: any) {
      toast.error(e.message)
    }
    setHarvesting(false)
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">LinkedIn Harvest</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Guest search is discovery-only. The browser companion resolves authenticated external apply URLs and queues only eligible jobs.
        </p>
      </div>

      {/* Search */}
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Keywords</label>
          <input
            type="text"
            value={keywords}
            onChange={e => setKeywords(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="e.g. security engineer"
            className="w-full h-9 px-3 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="w-48">
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Location</label>
          <input
            type="text"
            value={location}
            onChange={e => setLocation(e.target.value)}
            placeholder="e.g. United States"
            className="w-full h-9 px-3 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="w-20">
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Pages</label>
          <input
            type="number"
            value={pages}
            onChange={e => setPages(Number(e.target.value))}
            min={1}
            max={5}
            className="w-full h-9 px-3 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="w-20">
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Detail</label>
          <input
            type="number"
            value={detail}
            onChange={e => setDetail(Number(e.target.value))}
            min={0}
            max={10}
            className="w-full h-9 px-3 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading || !keywords.trim()}
          className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          Search
        </button>
      </div>

      {/* Harvest all */}
      {cards.length > 0 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">{cards.length} cards found</span>
          <button
            onClick={handleHarvest}
            disabled={harvesting || resolvedCards.length === 0}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-sm font-medium hover:bg-primary/20 disabled:opacity-50"
          >
            {harvesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {resolvedCards.length ? `Import ${resolvedCards.length} resolved` : 'Resolution required'}
          </button>
        </div>
      )}

      <div className="space-y-2">
        {cards.map((card, i) => (
          <motion.div
            key={card.jobId || i}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.02 }}
            className="flex items-center gap-4 rounded-xl border border-border bg-card p-4"
          >
            <Globe className="w-5 h-5 text-blue-500 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{card.title || 'Untitled'}</div>
              <div className="text-xs text-muted-foreground truncate mt-0.5">
                {card.company} · {card.location}
                {card.external_apply && ' · External Apply'}
                {card.easy_apply && ' · Easy Apply'}
              </div>
              <div className="mt-2"><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${resolvedCards.includes(card) ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>{resolvedCards.includes(card) ? 'Resolved ATS URL' : 'Discovery only · open with extension'}</span></div>
              {card.description && (
                <div className="text-xs text-muted-foreground mt-1 line-clamp-2">{card.description}</div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <a
                href={card.url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-lg hover:bg-secondary transition-colors"
              >
                <ExternalLink className="w-4 h-4 text-muted-foreground" />
              </a>
              <button
                onClick={() => { if (resolvedCards.includes(card)) setSelected(card) }}
                disabled={!resolvedCards.includes(card)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Plus className="w-3 h-3" /> {resolvedCards.includes(card) ? 'Queue' : 'Needs extension'}
              </button>
            </div>
          </motion.div>
        ))}
        {cards.length === 0 && !loading && (
          <div className="text-center py-16 text-muted-foreground">
            <Globe className="w-12 h-12 mx-auto mb-4 opacity-20" />
            <p className="text-lg">No LinkedIn results</p>
            <p className="text-sm mt-1">Search for jobs to get started</p>
          </div>
        )}
      </div>
      <QuickApplyDialog open={Boolean(selected)} onOpenChange={open => { if (!open) setSelected(null) }} initialUrl={selected?.url || ''} identity={{ companyName: selected?.company, jobTitle: selected?.title }} />
    </div>
  )
}
