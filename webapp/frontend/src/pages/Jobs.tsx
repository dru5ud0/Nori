import { useQuery, useQueryClient } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import {
  Briefcase, Calendar, ExternalLink, FileSearch, Filter, Loader2,
  MapPin, Search, Sparkles, X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api, type JobFeedItem } from '../api'
import { CompanyLogo } from '../components/CompanyLogo'
import { QuickApplyDialog } from '../components/QuickApplyDialog'

function companyLabel(job: JobFeedItem) {
  if (job.companyName) return job.companyName
  try { return new URL(job.url).hostname.replace('www.', '') }
  catch { return 'Unknown company' }
}

export function Jobs() {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const { data: saved } = useQuery({ queryKey: ['feed', 'saved'], queryFn: api.loadFeed })
  const { data: monitor } = useQuery({ queryKey: ['monitor'], queryFn: api.getMonitor })
  const [roleQuery, setRoleQuery] = useState('Cybersecurity Analyst')
  const [location, setLocation] = useState('Chicago, IL')
  const [remoteOnly, setRemoteOnly] = useState(false)
  const [filter, setFilter] = useState('')
  const [limit, setLimit] = useState(50)
  const [jobs, setJobs] = useState<JobFeedItem[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<JobFeedItem | null>(null)
  const [quickJob, setQuickJob] = useState<JobFeedItem | null>(null)
  const [quickOpen, setQuickOpen] = useState(false)
  const [seeded, setSeeded] = useState(false)

  useEffect(() => {
    if (monitor && !seeded) {
      setRoleQuery(monitor.query || 'Cybersecurity Analyst')
      setLocation(monitor.location || '')
      setRemoteOnly(Boolean(monitor.remoteOnly))
      setLimit(monitor.limit || 50)
      setSeeded(true)
    }
  }, [monitor, seeded])

  const prepareUrl = params.get('prepare') || ''
  const prepareTitle = params.get('title') || 'Job from notification'
  const prepareCompany = params.get('company') || ''
  useEffect(() => {
    if (!prepareUrl) return
    const job: JobFeedItem = {
      id: `notification-${Date.now()}`,
      url: prepareUrl,
      title: prepareTitle,
      companyName: prepareCompany,
    }
    setQuickJob(job)
    setQuickOpen(true)
    setParams({}, { replace: true })
  }, [prepareCompany, prepareTitle, prepareUrl, setParams])

  const results = useMemo(() => jobs ?? saved?.jobs ?? [], [jobs, saved?.jobs])
  const visible = useMemo(() => {
    const needle = filter.toLowerCase().trim()
    return (results as JobFeedItem[]).filter(job => !needle ||
      `${job.title} ${job.companyName || ''} ${job.location || ''}`.toLowerCase().includes(needle))
  }, [results, filter])

  const searchJobs = async () => {
    if (!roleQuery.trim()) return
    setLoading(true)
    try {
      const data = await api.searchJobs(roleQuery.trim(), location.trim(), remoteOnly, limit)
      setJobs(data.jobs || [])
      queryClient.setQueryData(['feed', 'saved'], data)
      await queryClient.invalidateQueries({ queryKey: ['feed', 'top'] })
      toast.success(`${data.count} HiringCafe jobs ranked for you`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'HiringCafe search failed')
    } finally {
      setLoading(false)
    }
  }

  const prepare = (job: JobFeedItem) => {
    setQuickJob(job)
    setQuickOpen(true)
  }

  return <div className="space-y-6">
    <section className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
      <div><p className="text-xs font-semibold uppercase tracking-[.18em] text-primary">HiringCafe discovery</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Browse jobs</h1><p className="mt-2 max-w-2xl text-sm text-muted-foreground">Search the wider market, rank roles against your local profile, and send a promising posting to Nori AI for a review draft.</p></div>
      <a href="https://hiringcafe.com/" target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 self-start rounded-xl border-2 border-border bg-card px-3 py-2.5 text-xs font-semibold shadow-sm"><ExternalLink className="h-4 w-4" />Open HiringCafe</a>
    </section>

    <section className="surface p-4">
      <p className="mb-4 text-xs text-muted-foreground">Saved HiringCafe filters, excluded titles, and salary preferences also apply here. <Link to="/auto-apply" className="font-semibold text-primary underline">Edit search preferences</Link></p>
      <div className="grid gap-3 lg:grid-cols-[minmax(260px,1fr)_220px_auto_auto]">
        <label htmlFor="job-role-query" className="space-y-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Role or keywords<div className="relative mt-1"><Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2" /><input id="job-role-query" value={roleQuery} onChange={event => setRoleQuery(event.target.value)} onKeyDown={event => event.key === 'Enter' && searchJobs()} placeholder="Cybersecurity analyst, GRC, TPRM…" className="field w-full pl-10 text-sm normal-case tracking-normal outline-none focus:border-primary" /></div></label>
        <label htmlFor="job-location-query" className="space-y-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Preferred location<input id="job-location-query" value={location} onChange={event => setLocation(event.target.value)} placeholder="Chicago, IL" className="field mt-1 w-full text-sm normal-case tracking-normal outline-none focus:border-primary" /></label>
        <label className="flex min-h-11 items-center gap-2 self-end border-2 border-border bg-card px-3 text-xs font-semibold"><input type="checkbox" checked={remoteOnly} onChange={event => setRemoteOnly(event.target.checked)} />Remote only</label>
        <button onClick={searchJobs} disabled={loading || !roleQuery.trim()} className="inline-flex min-h-11 items-center justify-center gap-2 self-end border-2 border-border bg-primary px-5 text-sm font-bold text-white shadow-sm disabled:opacity-40">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}{loading ? 'Searching…' : 'Search & rank'}</button>
      </div>
      <div className="mt-3 flex flex-col gap-3 border-t border-border pt-3 sm:flex-row sm:items-center sm:justify-between"><div className="relative w-full sm:max-w-sm"><Filter className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" /><input value={filter} onChange={event => setFilter(event.target.value)} placeholder="Filter these results" className="field w-full pl-9 text-xs outline-none" /></div><label className="flex items-center gap-2 text-xs text-muted-foreground">Results<input type="number" min={1} max={150} value={limit} onChange={event => setLimit(Number(event.target.value))} className="field w-20 text-xs" /></label></div>
    </section>

    <div className="flex items-center justify-between"><p className="text-sm text-muted-foreground"><b className="text-foreground">{visible.length}</b> ranked roles</p><span className="text-xs text-muted-foreground">Highest match first · direct employer links</span></div>

    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {visible.map(job => <article key={job.id || job.url} className="group flex min-h-64 flex-col rounded-2xl border-2 border-border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
        <div className="flex items-start justify-between"><CompanyLogo name={job.companyName} domain={job.companyDomain} logoUrl={job.logoUrl} className="h-10 w-10" /><span className="border-2 border-border bg-accent px-2 py-1 font-mono text-[10px] font-bold text-black">{job.matchScore ?? 0}% MATCH</span></div>
        <button onClick={() => setSelected(job)} className="mt-5 text-left"><h2 className="line-clamp-2 text-sm font-semibold leading-5 group-hover:text-primary">{job.title || 'Open role'}</h2><p className="mt-2 truncate text-xs text-muted-foreground">{companyLabel(job)}</p></button>
        <div className="mt-4 flex flex-wrap gap-2 text-[10px] text-muted-foreground">{job.location && <span className="rounded-full bg-secondary px-2 py-1"><MapPin className="mr-1 inline h-3 w-3" />{job.location}</span>}{job.remote && <span className="rounded-full bg-secondary px-2 py-1">Remote</span>}{job.updated_at && <span className="rounded-full bg-secondary px-2 py-1"><Calendar className="mr-1 inline h-3 w-3" />Recent</span>}</div>
        {job.matchReasons?.[0] && <p className="mt-3 line-clamp-2 text-xs leading-5 text-muted-foreground">{job.matchReasons[0]}</p>}
        {job.matchWarnings?.[0] && <p className="mt-2 line-clamp-2 text-xs leading-5 text-amber-700 dark:text-amber-400">Review: {job.matchWarnings[0]}</p>}
        <div className="mt-auto flex gap-2 pt-5"><button onClick={() => setSelected(job)} className="flex-1 rounded-xl border-2 border-border py-2 text-xs font-medium hover:bg-secondary">Details</button><button onClick={() => prepare(job)} className="flex-1 rounded-xl border-2 border-border bg-primary py-2 text-xs font-bold text-white shadow-sm">Review & apply</button></div>
      </article>)}
      {visible.length === 0 && !loading && <div className="col-span-full rounded-2xl border-2 border-dashed border-border py-20 text-center"><Briefcase className="mx-auto h-10 w-10 text-muted-foreground/40" /><h2 className="mt-4 font-semibold">No saved matches yet</h2><p className="mt-1 text-sm text-muted-foreground">Search HiringCafe above. Nori AI will rank and save the results for Dashboard and overnight monitoring.</p></div>}
    </section>

    <Dialog.Root open={Boolean(selected)} onOpenChange={open => !open && setSelected(null)}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[70] bg-black/60" /><Dialog.Content className="fixed inset-y-3 right-3 z-[75] w-[calc(100%-24px)] max-w-xl overflow-y-auto rounded-[24px] border-2 border-border bg-card p-6 shadow-xl">
      <div className="flex items-start justify-between"><CompanyLogo name={selected?.companyName} domain={selected?.companyDomain} logoUrl={selected?.logoUrl} className="h-11 w-11" /><Dialog.Close className="rounded-xl p-2 text-muted-foreground hover:bg-secondary"><X className="h-4 w-4" /></Dialog.Close></div>
      <Dialog.Title className="mt-6 text-2xl font-bold">{selected?.title || 'Job detail'}</Dialog.Title><Dialog.Description className="mt-2 text-sm text-muted-foreground">{selected ? companyLabel(selected) : ''}</Dialog.Description>
      <div className="mt-6 grid grid-cols-2 gap-3"><div className="rounded-2xl border-2 border-border bg-background p-4"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Nori match</p><p className="mt-2 text-2xl font-black">{selected?.matchScore ?? 0}%</p></div><div className="rounded-2xl border-2 border-border bg-background p-4"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Apply system</p><p className="mt-2 text-sm font-semibold">{selected?.atsType || 'Needs preflight'}</p></div></div>
      {selected?.matchReasons?.length ? <div className="mt-4 rounded-2xl border-2 border-border bg-background p-5"><h3 className="text-sm font-semibold">Why it matched</h3><ul className="mt-3 space-y-2 text-xs text-muted-foreground">{selected.matchReasons.map(reason => <li key={reason}>• {reason}</li>)}</ul></div> : null}
      {selected?.matchWarnings?.length ? <div className="mt-4 rounded-2xl border-2 border-amber-300 bg-amber-50 p-5 dark:border-amber-900 dark:bg-amber-950/30"><h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200">Requirements to verify</h3><ul className="mt-3 space-y-2 text-xs text-amber-800 dark:text-amber-300">{selected.matchWarnings.map(warning => <li key={warning}>• {warning}</li>)}</ul></div> : null}
      {selected?.description && <div className="mt-4 rounded-2xl border-2 border-border bg-background p-5"><h3 className="text-sm font-semibold">HiringCafe summary</h3><p className="mt-3 whitespace-pre-line text-xs leading-5 text-muted-foreground">{selected.description}</p></div>}
      <div className="mt-6 flex gap-2"><a href={selected?.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border-2 border-border px-4 py-2.5 text-sm"><ExternalLink className="h-4 w-4" />Open posting</a><button onClick={() => { if (selected) prepare(selected); setSelected(null) }} className="flex-1 rounded-xl border-2 border-border bg-primary px-4 py-2.5 text-sm font-bold text-white"><FileSearch className="mr-2 inline h-4 w-4" />Review & apply</button></div>
    </Dialog.Content></Dialog.Portal></Dialog.Root>
    <QuickApplyDialog open={quickOpen} onOpenChange={setQuickOpen} initialUrl={quickJob?.url || ''} identity={{ companyName: quickJob?.companyName, companyDomain: quickJob?.companyDomain, logoUrl: quickJob?.logoUrl, jobTitle: quickJob?.title }} />
  </div>
}
