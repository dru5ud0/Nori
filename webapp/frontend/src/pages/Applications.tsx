import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api, type Application } from '../api'
import { Clock, AlertCircle, Play, CheckCircle2, XCircle, Pause, ExternalLink, RotateCw, Search, Download, Archive } from 'lucide-react'
import { CompanyLogo } from '../components/CompanyLogo'
import { toast } from 'sonner'
import { useState } from 'react'
import { safeHostname } from '../lib/utils'

const STATUS_ICONS: Record<string, React.FC<{ className?: string }>> = {
  queued: Clock,
  review: AlertCircle,
  running: Play,
  applied: CheckCircle2,
  failed: XCircle,
  paused: Pause,
}

const STATUS_COLORS: Record<string, string> = {
  queued: 'text-queued',
  review: 'text-review',
  running: 'text-running',
  applied: 'text-applied',
  failed: 'text-failed',
  paused: 'text-paused',
}

export function Applications() {
  const [params] = useSearchParams()
  const filter = params.get('filter') || 'all'
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['applications', filter, query],
    queryFn: () => api.listApplications(filter, 1, 100, query),
    refetchInterval: 3000,
  })

  const runMutation = useMutation({
    mutationFn: (id: string) => api.runApplication(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['applications'] }); toast.success('Application prepared for review') },
    onError: (error: Error) => toast.error(error.message),
  })

  const archiveMutation = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) => api.setApplicationArchived(id, archived),
    onSuccess: async result => {
      await queryClient.invalidateQueries({ queryKey: ['applications'] })
      await queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
      toast.success(result.archived ? 'Application archived' : 'Application restored')
    },
    onError: (error: Error) => toast.error(error.message),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  const apps = data?.applications ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Applications</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data?.total ?? 0} total · {data?.filtered ?? 0} shown
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1 rounded-lg bg-secondary p-0.5">
          {['all', 'queued', 'review', 'running', 'applied', 'failed', 'paused', 'archived'].map(f => (
            <button
              key={f}
              onClick={() => navigate(`/applications?filter=${f}`)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                filter === f ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <label className="relative block max-w-xl flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search company, role, ATS, URL, or tracker stage"
            aria-label="Search applications"
            className="h-10 w-full rounded-xl border border-border bg-card pl-9 pr-3 text-sm outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30"
          />
        </label>
        <a
          href={api.trackerExportUrl}
          download="nori-tracker.csv"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 text-xs font-semibold text-muted-foreground hover:text-foreground"
        >
          <Download className="h-3.5 w-3.5" /> Export CSV
        </a>
      </div>

      <div className="space-y-2">
        {apps.map((app: Application) => {
          const Icon = STATUS_ICONS[app.status] || Clock
          return (
            <motion.div
              key={app.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => navigate(`/applications/${app.id}`)}
              className="flex items-center gap-4 rounded-xl border border-border bg-card p-4 cursor-pointer hover:border-primary/30 transition-colors group"
            >
              <CompanyLogo name={app.company} domain={app.companyDomain} logoUrl={app.logoUrl} className="h-10 w-10" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">
                    {app.company || safeHostname(app.url)}
                  </span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-primary/10 text-primary border border-primary/20">
                    {app.ats || 'unknown'}
                  </span>
                  <span className={`inline-flex items-center gap-1 text-[10px] font-medium uppercase ${STATUS_COLORS[app.status]}`}><Icon className="h-3 w-3" />{app.status}</span>
                  {app.submissionEvidence?.kind === 'legacy-unverified' && <span className="inline-flex items-center rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-500">receipt unverified</span>}
                </div>
                <div className="text-xs text-muted-foreground truncate mt-0.5">
                  {app.title || app.url}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {!app.archived && !app.manualTrackerEntry && (app.status === 'queued' || app.status === 'paused') && (
                  <button
                    onClick={e => { e.stopPropagation(); runMutation.mutate(app.id) }}
                    disabled={runMutation.isPending}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                  >
                    <RotateCw className="w-3 h-3" />
                    {app.status === 'paused' ? 'Run again' : 'Run'}
                  </button>
                )}
                <button
                  onClick={e => { e.stopPropagation(); archiveMutation.mutate({ id: app.id, archived: !app.archived }) }}
                  disabled={archiveMutation.isPending}
                  aria-label={app.archived ? `Restore ${app.title || 'application'}` : `Archive ${app.title || 'application'}`}
                  title={app.archived ? 'Restore application' : 'Archive application'}
                  className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-40"
                >
                  {app.archived ? <RotateCw className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}
                  {app.archived ? 'Restore' : 'Archive'}
                </button>
                <ExternalLink className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
              </div>
            </motion.div>
          )
        })}
        {apps.length === 0 && (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-lg">No applications found</p>
            <p className="text-sm mt-1">Add a job URL from the Dashboard to get started</p>
          </div>
        )}
      </div>
    </div>
  )
}
