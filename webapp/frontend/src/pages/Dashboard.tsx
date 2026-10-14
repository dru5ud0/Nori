import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowRight, Check, FileSearch, FileText, Loader2, Search, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api, type Application, type JobFeedItem } from '../api'
import { CompanyLogo } from '../components/CompanyLogo'
import { QuickApplyDialog } from '../components/QuickApplyDialog'
import { safeHostname } from '../lib/utils'

const tabs = [
  { key: 'all', label: 'All' },
  { key: 'in_flight', label: 'In flight' },
  { key: 'needs', label: 'Needs you' },
  { key: 'failed', label: 'Failed' },
  { key: 'paused', label: 'Skipped' },
]

const statusCopy: Record<string, { label: string; className: string }> = {
  queued: { label: 'Queued', className: 'bg-blue-100 text-blue-800' },
  review: { label: 'Needs you', className: 'bg-amber-500/10 text-amber-400' },
  running: { label: 'Submitting', className: 'bg-blue-500/10 text-blue-400' },
  applied: { label: 'Submitted', className: 'bg-emerald-500/10 text-emerald-400' },
  failed: { label: 'Failed', className: 'bg-red-500/10 text-red-400' },
  paused: { label: 'Skipped', className: 'bg-zinc-500/10 text-zinc-400' },
}

function matchesTab(app: Application, tab: string) {
  if (tab === 'all') return true
  if (tab === 'in_flight') return app.status === 'queued' || app.status === 'running'
  if (tab === 'needs') return app.status === 'review'
  return app.status === tab
}

export function Dashboard() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState('all')
  const [quickApplyOpen, setQuickApplyOpen] = useState(false)
  const [quickJob, setQuickJob] = useState<JobFeedItem | null>(null)
  const { data: bootstrap, isLoading } = useQuery({ queryKey: ['bootstrap'], queryFn: api.bootstrap, refetchInterval: 2500 })
  const { data: applications } = useQuery({ queryKey: ['applications', 'all'], queryFn: () => api.listApplications('all'), refetchInterval: 2500 })
  const { data: feed } = useQuery({ queryKey: ['feed', 'top'], queryFn: () => api.topMatches(3) })
  const { data: monitor } = useQuery({ queryKey: ['monitor'], queryFn: api.getMonitor, refetchInterval: 5000 })

  const visible = useMemo(() => (applications?.applications || []).filter(app => {
    const needle = search.toLowerCase()
    return matchesTab(app, tab) && (!needle || `${app.company} ${app.title} ${app.url}`.toLowerCase().includes(needle))
  }), [applications, search, tab])

  const add = () => {
    if (!url.trim()) return
    setQuickJob(null)
    setQuickApplyOpen(true)
  }

  if (isLoading) return <div className="grid h-64 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
  const counts = bootstrap?.counts

  return <div className="space-y-7">
    {bootstrap?.profile.testProfile && <section className="flex flex-col justify-between gap-4 rounded-2xl border border-amber-500/25 bg-amber-500/[.06] p-5 sm:flex-row sm:items-center"><div><p className="text-sm font-semibold text-amber-400">Demo profile is active</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Import your real resume and review personal information before preparing new applications. Existing demo dry-runs remain safe.</p></div><button onClick={() => navigate('/profile')} className="shrink-0 rounded-xl bg-amber-400 px-4 py-2.5 text-xs font-bold text-black">Set up my profile</button></section>}
    <section className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
      <div><p className="text-xs font-semibold uppercase tracking-[.18em] text-primary">Mission Control</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Dashboard</h1><p className="mt-2 text-sm text-muted-foreground">{counts?.total || 0} applications · {counts?.applied || 0} submitted · {counts?.review || 0} need you</p></div>
      <div className="flex w-full max-w-2xl gap-2 rounded-2xl border border-border bg-card p-2 shadow-xl shadow-black/10"><input value={url} onChange={e => { setUrl(e.target.value); setQuickJob(null) }} onKeyDown={e => e.key === 'Enter' && add()} placeholder="Paste any job URL to check..." className="min-w-0 flex-1 bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground/60" /><button onClick={add} disabled={!url.trim()} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"><FileSearch className="h-4 w-4" />Check job</button></div>
    </section>

    <section className="grid gap-3 md:grid-cols-3">
      <div className="rounded-2xl border border-border bg-card p-5"><div className="flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">In flight</span><Loader2 className={`h-4 w-4 text-blue-400 ${counts?.running ? 'animate-spin' : ''}`} /></div><p className="mt-4 text-3xl font-bold">{(counts?.queued || 0) + (counts?.running || 0)}</p><p className="mt-1 text-xs text-muted-foreground">Queued or currently submitting</p></div>
      <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[.04] p-5"><div className="flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-wider text-amber-400">Needs you</span><AlertCircle className="h-4 w-4 text-amber-400" /></div><p className="mt-4 text-3xl font-bold">{counts?.review || 0}</p><p className="mt-1 text-xs text-muted-foreground">Resume, answer, or submit review</p></div>
      <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[.04] p-5"><div className="flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Submitted</span><Check className="h-4 w-4 text-emerald-400" /></div><p className="mt-4 text-3xl font-bold">{counts?.applied || 0}</p><p className="mt-1 text-xs text-muted-foreground">Completed applications</p></div>
    </section>

    <section className="space-y-3">
      <div className="flex items-center justify-between"><div><div className="flex items-center gap-2"><h2 className="text-lg font-semibold">Top job matches</h2>{monitor?.enabled && <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-600">Monitoring live</span>}</div><p className="text-xs text-muted-foreground">Profile-ranked HiringCafe results, highest score first</p></div><button onClick={() => navigate('/jobs')} className="text-xs font-medium text-primary">Browse Jobs <ArrowRight className="ml-1 inline h-3.5 w-3.5" /></button></div>
      <div className="grid gap-3 md:grid-cols-3">{(feed?.jobs || []).map((job: JobFeedItem) => <article key={job.id || job.url} className="rounded-2xl border-2 border-border bg-card p-4 shadow-sm"><div className="flex items-start justify-between"><CompanyLogo name={job.companyName} domain={job.companyDomain} logoUrl={job.logoUrl} className="h-9 w-9" /><span className="border-2 border-border bg-accent px-2 py-1 font-mono text-[10px] font-bold text-black">{job.matchScore ?? 0}% MATCH</span></div><h3 className="mt-4 truncate text-sm font-semibold">{job.title || 'Open role'}</h3><p className="mt-1 truncate text-xs text-muted-foreground">{job.companyName || safeHostname(job.url)}</p>{job.matchReasons?.[0] && <p className="mt-2 line-clamp-1 text-[11px] text-muted-foreground">{job.matchReasons[0]}</p>}<button onClick={() => { setUrl(job.url); setQuickJob(job); setQuickApplyOpen(true); toast.info('Job loaded for review') }} className="mt-4 w-full rounded-xl border-2 border-border bg-primary py-2 text-xs font-bold text-white shadow-sm">Review & apply</button></article>)}{(!feed?.jobs || feed.jobs.length === 0) && <div className="col-span-full rounded-2xl border-2 border-dashed border-border py-9 text-center text-sm text-muted-foreground">No saved jobs meet your monitor score yet. Search HiringCafe or lower the minimum score under Automation.</div>}</div>
    </section>

    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex flex-col gap-4 border-b border-border p-5 lg:flex-row lg:items-center lg:justify-between"><div><h2 className="text-lg font-semibold">All applications</h2><p className="text-xs text-muted-foreground">Live status from your local execution engine</p></div><div className="relative w-full lg:w-72"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by title, company..." className="w-full rounded-xl border border-border bg-secondary py-2 pl-9 pr-3 text-sm outline-none focus:border-primary/50" /></div></div>
      <div className="flex gap-1 overflow-x-auto border-b border-border px-4 pt-3">{tabs.map(item => <button key={item.key} onClick={() => setTab(item.key)} className={`whitespace-nowrap border-b-2 px-3 py-2 text-xs font-medium ${tab === item.key ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground'}`}>{item.label}</button>)}</div>
      <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left"><thead><tr className="border-b border-border text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"><th className="px-5 py-3">Position</th><th className="px-4 py-3">Resume</th><th className="px-4 py-3">Cover Letter</th><th className="px-4 py-3">Status</th><th className="px-5 py-3 text-right">Updated</th></tr></thead><tbody>{visible.map(app => { const status = statusCopy[app.status] || statusCopy.queued; const uploads = app.answersSummary?.uploaded_documents || []; const resumeReady = Boolean(app.documents?.resume?.pdfGenerated || uploads.some(item => item.kind === 'resume')); const coverReady = Boolean(app.documents?.coverLetter?.pdfGenerated || uploads.some(item => item.kind === 'cover_letter')); return <tr key={app.id} onClick={() => navigate(`/applications/${app.id}`)} className="cursor-pointer border-b border-border/70 last:border-0 hover:bg-secondary/40"><td className="px-5 py-4"><div className="flex items-center gap-3"><CompanyLogo name={app.company} domain={app.companyDomain} logoUrl={app.logoUrl} className="h-9 w-9" /><div><p className="max-w-xs truncate text-sm font-medium">{app.title || safeHostname(app.url)}</p><p className="mt-0.5 max-w-xs truncate text-xs text-muted-foreground">{app.company || app.ats || 'Application'}</p></div></div></td><td className="px-4 py-4"><span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><FileText className="h-3.5 w-3.5" />{resumeReady ? 'Ready' : 'Not prepared'}</span></td><td className="px-4 py-4"><span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Sparkles className="h-3.5 w-3.5" />{coverReady ? 'Ready' : 'Not prepared'}</span></td><td className="px-4 py-4"><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${status.className}`}>{status.label}</span></td><td className="px-5 py-4 text-right text-xs text-muted-foreground">{app.updatedAt ? new Date(app.updatedAt).toLocaleDateString() : '—'}</td></tr>})}</tbody></table>{visible.length === 0 && <div className="py-14 text-center text-sm text-muted-foreground">No applications in this view.</div>}</div>
    </section>
    <QuickApplyDialog open={quickApplyOpen} onOpenChange={setQuickApplyOpen} initialUrl={url} identity={{ companyName: quickJob?.companyName, companyDomain: quickJob?.companyDomain, logoUrl: quickJob?.logoUrl, jobTitle: quickJob?.title }} />
  </div>
}
