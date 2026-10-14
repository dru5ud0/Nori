import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Bot, CalendarDays, CheckCircle2, Download, ExternalLink, FileUser, Goal,
  Inbox as InboxIcon, Loader2, MessageCircle, Microscope, Moon, RefreshCw,
  Save, Send, Settings as SettingsIcon, ShieldCheck, Sparkles,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api, type ApplySettings, type MonitorLane, type MonitorSettings } from '../api'
import { safeHostname } from '../lib/utils'

function Header({ title, subtitle, icon: Icon }: { title: string; subtitle: string; icon: typeof Bot }) {
  return <div className="flex items-start gap-4">
    <div className="grid h-11 w-11 place-items-center rounded-2xl border border-primary/20 bg-primary/10 text-primary"><Icon className="h-5 w-5" /></div>
    <div><h1 className="text-2xl font-bold tracking-tight">{title}</h1><p className="mt-1 text-sm text-muted-foreground">{subtitle}</p></div>
  </div>
}

export function AutoApply() {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ['monitor'], queryFn: api.getMonitor, refetchInterval: 5000 })
  const { data: preview } = useQuery({ queryKey: ['monitor-preview'], queryFn: () => api.monitorPreview(7), refetchInterval: 15000 })
  const { data: readiness } = useQuery({ queryKey: ['automation-readiness'], queryFn: api.automationReadiness, refetchInterval: 5000 })
  const [draft, setDraft] = useState<MonitorSettings | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [testing, setTesting] = useState(false)
  useEffect(() => { if (data && !dirty) setDraft({ ...data }) }, [data, dirty])
  const settings = draft || data
  const update = (key: keyof MonitorSettings, value: unknown) => { if (settings) { setDraft({ ...settings, [key]: value }); setDirty(true) } }
  const lanes: MonitorLane[] = settings?.lanes || []
  const updateLane = (index: number, key: keyof MonitorLane, value: unknown) => update('lanes', lanes.map((lane, laneIndex) => laneIndex === index ? { ...lane, [key]: value } : lane))
  const addLane = () => {
    if (lanes.length >= 5) return
    update('lanes', [...lanes, { id: `lane-${Date.now()}`, name: `Lane ${lanes.length + 1}`, enabled: true, query: '', location: '', remoteOnly: false, minScore: 25, minMatchQuality: 'stretch' }])
  }
  const removeLane = (index: number) => {
    if (lanes.length <= 1) return
    update('lanes', lanes.filter((_, laneIndex) => laneIndex !== index))
  }
  const save = async () => {
    if (!settings) return
    setSaving(true)
    try {
      const result = await api.updateMonitor(settings)
      setDraft({ ...result.settings })
      setDirty(false)
      queryClient.setQueryData(['monitor'], result.settings)
      await queryClient.invalidateQueries({ queryKey: ['automation-readiness'] })
      await queryClient.invalidateQueries({ queryKey: ['monitor-preview'] })
      toast.success(result.settings.enabled ? 'Overnight monitor enabled' : 'Monitor settings saved')
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not save monitor') }
    finally { setSaving(false) }
  }
  const runNow = async () => {
    setRunning(true)
    try {
      if (settings && dirty) {
        const saved = await api.updateMonitor(settings)
        queryClient.setQueryData(['monitor'], saved.settings)
      }
      const result = await api.runMonitor()
      setDraft(null)
      setDirty(false)
      await queryClient.invalidateQueries({ queryKey: ['monitor'] })
      await queryClient.invalidateQueries({ queryKey: ['feed', 'saved'] })
      await queryClient.invalidateQueries({ queryKey: ['feed', 'top'] })
      await queryClient.invalidateQueries({ queryKey: ['applications'] })
      await queryClient.invalidateQueries({ queryKey: ['automation-readiness'] })
      await queryClient.invalidateQueries({ queryKey: ['monitor-preview'] })
      toast.success(`${result.count} jobs checked · ${result.prepared} prepared · ${result.applied} applied · ${result.needsReview} need review`)
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Monitor run failed') }
    finally { setRunning(false) }
  }
  const testTelegram = async () => {
    if (!settings) return
    setTesting(true)
    try {
      if (settings.telegramBotToken) {
        const result = await api.updateMonitor(settings)
        setDraft({ ...result.settings })
        setDirty(false)
        queryClient.setQueryData(['monitor'], result.settings)
      }
      await api.testMonitor()
      toast.success('Telegram test sent')
    }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Telegram test failed') }
    finally { setTesting(false) }
  }
  if (!settings) return null
  const active = Boolean(settings.enabled)
  const preparationRequested = settings.applicationMode === 'prepare' || settings.applicationMode === 'apply'
  const preparationBlocked = preparationRequested && readiness?.readyToPrepare === false
  return <div className="max-w-5xl space-y-6">
    <Header title="Automation" subtitle="Let Nori AI watch HiringCafe overnight and alert you to strong matches." icon={Moon} />
    <div className="overflow-hidden rounded-2xl border-2 border-border bg-accent p-6 shadow-md">
      <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center">
        <div><span className="border-2 border-border bg-card px-2 py-1 text-[10px] font-semibold uppercase">Local + private</span><h2 className="mt-4 text-xl font-semibold">Your overnight job watch</h2><p className="mt-2 max-w-xl text-sm text-black/70">Nori searches HiringCafe, ranks matches, sends alerts, and can prepare supported ATS forms for your review while you are away.</p></div>
        <div className={`rounded-2xl border-2 border-border p-5 ${active ? 'bg-emerald-100' : 'bg-card'}`}><div className="flex items-center gap-2 text-sm font-bold"><span className={`h-2.5 w-2.5 rounded-full ${active ? 'bg-emerald-500' : 'bg-zinc-500'}`} />{active ? 'Monitor running' : 'Monitor off'}</div><p className="mt-2 text-xs text-black/60">Keep the Nori AI server window open. While enabled, Windows stays awake and the display may turn off.</p></div>
      </div>
    </div>
    {readiness && <section className={`rounded-2xl border-2 p-5 ${readiness.readyToPrepare ? 'border-emerald-500/30 bg-emerald-500/[.04]' : 'border-amber-500/30 bg-amber-500/[.05]'}`}>
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Automation preflight</p><h2 className="mt-2 font-semibold">{readiness.readyToPrepare ? 'Ready to prepare applications' : 'Finish setup before automated preparation'}</h2><p className="mt-1 text-xs text-muted-foreground">Monitoring can run independently. Preparation and submission require every safety check below.</p></div><span className={`rounded-full px-3 py-1 text-xs font-semibold ${readiness.readyToPrepare ? 'bg-emerald-500/10 text-emerald-600' : 'bg-amber-500/10 text-amber-600'}`}>{readiness.readyToPrepare ? 'Ready' : `${readiness.blockers.length} blocker${readiness.blockers.length === 1 ? '' : 's'}`}</span></div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{readiness.checks.map(check => <div key={check.id} className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs">{check.ok ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" /> : <AlertTriangle className={`h-4 w-4 shrink-0 ${check.required ? 'text-amber-500' : 'text-muted-foreground'}`} />}<span>{check.label}</span>{!check.required && <span className="ml-auto text-[9px] uppercase text-muted-foreground">Optional</span>}</div>)}</div>
      {readiness.warnings.length > 0 && <div className="mt-3 space-y-1 text-xs text-muted-foreground">{readiness.warnings.map(warning => <p key={warning}>{warning}</p>)}</div>}
    </section>}
    <section className="rounded-2xl border-2 border-border bg-card p-5 space-y-4">
      <h2 className="font-semibold">Search preferences and application behavior</h2>
      <label className="block text-sm">Saved HiringCafe search URL<input value={settings.savedSearchUrl || ''} onChange={event => update('savedSearchUrl', event.target.value)} placeholder="Paste the URL after setting your filters on HiringCafe" className="field mt-2 w-full text-sm" /></label>
      <p className="text-xs text-muted-foreground">Uses HiringCafe’s native experience, sponsorship, salary, clearance, and other filters. The role keywords below replace the saved search keywords. The salary check excludes known lower-paying roles; unlisted salaries remain eligible.</p>
      <div className="grid gap-4 md:grid-cols-2"><label className="text-sm">Exclude titles containing<input value={settings.excludedTitles || ''} onChange={event => update('excludedTitles', event.target.value)} placeholder="intern, director, sales" className="field mt-2 w-full text-sm" /></label><label className="text-sm">Minimum annual salary (USD)<input type="number" min={0} value={settings.minimumSalary || 0} onChange={event => update('minimumSalary', Number(event.target.value))} className="field mt-2 w-full text-sm" /></label></div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings.strictLocation)} onChange={event => update('strictLocation', event.target.checked)} />Only preferred city or remote roles</label>
      <div className="grid gap-4 md:grid-cols-4"><label className="text-sm">When a matching job is found<select value={settings.applicationMode || 'notify'} onChange={event => update('applicationMode', event.target.value)} className="field mt-2 w-full text-sm"><option value="notify">Notify only</option><option value="prepare">Prepare applications automatically</option><option value="apply">Request auto-submit on certified ATSes</option></select></label><label className="text-sm">Maximum applications per search cycle<input type="number" min={1} max={10} value={settings.maxApplicationsPerCycle || 3} onChange={event => update('maxApplicationsPerCycle', Number(event.target.value))} className="field mt-2 w-full text-sm" /></label><label className="text-sm">Shared daily application cap<input type="number" min={1} max={150} value={settings.dailyApplicationCap || 10} onChange={event => update('dailyApplicationCap', Number(event.target.value))} className="field mt-2 w-full text-sm" /></label><label className="text-sm">Minimum match quality<select value={settings.minMatchQuality || 'stretch'} onChange={event => update('minMatchQuality', event.target.value)} className="field mt-2 w-full text-sm"><option value="excellent">Excellent</option><option value="strong">Strong</option><option value="good">Good</option><option value="stretch">Stretch</option></select></label></div>
      <label className="block text-sm">Standing instructions (only explicit exclusions rule jobs out)<textarea value={settings.standingInstructions || ''} onChange={event => update('standingInstructions', event.target.value)} placeholder={'Example:\nAvoid: internships, director\nExclude: jobs outside the United States'} rows={3} className="field mt-2 w-full text-sm" /></label>
      <div className="rounded-xl border border-border bg-secondary/40 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-sm font-semibold">Automation lanes</h3><p className="mt-1 text-xs text-muted-foreground">Run up to five HiringCafe searches from one shared daily budget. A lane changes what gets considered, not how many applications Nori can prepare.</p></div><button onClick={addLane} disabled={lanes.length >= 5} className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold disabled:opacity-40">Add lane</button></div>
        <div className="mt-4 space-y-3">{lanes.map((lane, index) => <div key={lane.id} className="rounded-xl border border-border bg-card p-3"><div className="grid gap-3 md:grid-cols-[1fr_1.5fr_1fr_auto] md:items-end"><label className="text-xs font-semibold">Lane name<input value={lane.name} onChange={event => updateLane(index, 'name', event.target.value)} className="field mt-1 w-full text-sm font-normal" /></label><label className="text-xs font-semibold">Role or keywords<input value={lane.query} onChange={event => updateLane(index, 'query', event.target.value)} placeholder="Cloud security" className="field mt-1 w-full text-sm font-normal" /></label><label className="text-xs font-semibold">Location<input value={lane.location} onChange={event => updateLane(index, 'location', event.target.value)} placeholder="Chicago, IL" className="field mt-1 w-full text-sm font-normal" /></label><label className="flex items-center gap-2 pb-2 text-xs"><input type="checkbox" checked={lane.enabled} onChange={event => updateLane(index, 'enabled', event.target.checked)} />Enabled</label></div><div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end"><label className="text-xs font-semibold">Quality<select value={lane.minMatchQuality} onChange={event => updateLane(index, 'minMatchQuality', event.target.value)} className="field mt-1 w-full text-sm font-normal"><option value="excellent">Excellent</option><option value="strong">Strong</option><option value="good">Good</option><option value="stretch">Stretch</option></select></label><label className="text-xs font-semibold">Minimum score<input type="number" min={0} max={100} value={lane.minScore} onChange={event => updateLane(index, 'minScore', Number(event.target.value))} className="field mt-1 w-full text-sm font-normal" /></label><label className="flex items-center gap-2 pb-2 text-xs"><input type="checkbox" checked={lane.remoteOnly} onChange={event => updateLane(index, 'remoteOnly', event.target.checked)} />Remote only</label><button type="button" onClick={() => removeLane(index)} disabled={lanes.length <= 1} className="rounded-lg border border-border px-3 py-2 text-xs font-semibold text-muted-foreground disabled:opacity-40">Remove</button></div></div>)}</div>
      </div>
      {settings.applicationMode === 'apply' && <p className="rounded-xl bg-amber-500/10 p-3 text-sm">No ATS adapter is certified for unattended submission yet. Nori will prepare eligible drafts and stop for review; a Telegram Submit button is an explicit approval. Certification requires a verified live submission receipt, not just ATS detection.</p>}
      <p className="text-sm text-muted-foreground">Last cycle: {settings.lastPreparedCount || 0} prepared · {settings.lastAppliedCount || 0} applied · {settings.lastNeedsReviewCount || 0} need review · {settings.dailyApplicationsUsed || 0} / {settings.dailyApplicationCap || 10} daily budget used</p>
    </section>
    <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
      <div className="rounded-2xl border-2 border-border bg-card p-5 shadow-sm">
        <div className="flex items-start gap-3"><CalendarDays className="mt-0.5 h-5 w-5 text-primary" /><div><h2 className="font-semibold">Seven-day preview</h2><p className="mt-1 text-xs text-muted-foreground">A budget forecast based on saved matches and measured runs—not a promise of available jobs.</p></div></div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-secondary/50 p-3"><p className="font-mono text-[10px] uppercase text-muted-foreground">Ready now</p><p className="mt-2 text-2xl font-bold">{preview?.currentEligibleCandidates ?? 0}</p><p className="text-[11px] text-muted-foreground">untracked saved matches</p></div>
          <div className="rounded-xl bg-secondary/50 p-3"><p className="font-mono text-[10px] uppercase text-muted-foreground">7-day ceiling</p><p className="mt-2 text-2xl font-bold">{preview?.maximumPreparations ?? (settings.dailyApplicationCap || 10) * 7}</p><p className="text-[11px] text-muted-foreground">from your daily cap</p></div>
          <div className="rounded-xl bg-secondary/50 p-3"><p className="font-mono text-[10px] uppercase text-muted-foreground">Estimated new</p><p className="mt-2 text-2xl font-bold">{preview?.estimateAvailable ? preview.projectedNewJobs : '—'}</p><p className="text-[11px] text-muted-foreground">{preview?.estimateAvailable ? `${preview.recentRunsMeasured} measured runs` : 'run the monitor to measure'}</p></div>
          <div className="rounded-xl bg-secondary/50 p-3"><p className="font-mono text-[10px] uppercase text-muted-foreground">Search cadence</p><p className="mt-2 text-2xl font-bold">{preview?.cyclesPerDay ?? Math.max(1, Math.floor(1440 / settings.intervalMinutes))}</p><p className="text-[11px] text-muted-foreground">cycles per day</p></div>
        </div>
      </div>
      <div className="rounded-2xl border-2 border-border bg-card p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">Run history</h2><p className="mt-1 text-xs text-muted-foreground">The latest automation outcomes are kept locally.</p></div><span className="font-mono text-[10px] uppercase text-muted-foreground">Last 50</span></div>
        <div className="mt-4 space-y-2">
          {(settings.runHistory || []).slice(0, 8).map(run => <div key={run.runId} className="rounded-xl border border-border px-3 py-2.5"><div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${run.status === 'completed' ? 'bg-emerald-500' : run.status === 'partial' ? 'bg-amber-500' : 'bg-red-500'}`} /><span className="text-xs font-semibold capitalize">{run.status}</span><span className="text-[10px] uppercase text-muted-foreground">{run.mode}</span></div><time className="text-[10px] text-muted-foreground">{new Date(run.startedAt).toLocaleString()}</time></div><p className="mt-1 text-[11px] text-muted-foreground">{run.found} found · {run.new} new · {run.prepared} prepared · {run.applied} applied · {run.needsReview} review</p>{run.error && <p className="mt-1 truncate text-[11px] text-red-500" title={run.error}>{run.error}</p>}</div>)}
          {(!settings.runHistory || settings.runHistory.length === 0) && <div className="rounded-xl border border-dashed border-border py-10 text-center text-xs text-muted-foreground">No runs recorded yet. Use Run now or enable overnight monitoring.</div>}
        </div>
      </div>
    </section>
    <section className="rounded-2xl border-2 border-border bg-card p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold">Recent match alerts</h2><p className="mt-1 text-xs text-muted-foreground">New overnight matches stay here even when Telegram is not connected.</p></div><span className="font-mono text-[10px] uppercase text-muted-foreground">Last 50</span></div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {(settings.recentAlerts || []).slice(0, 8).map(alert => <a key={alert.id || alert.url} href={alert.url} target="_blank" rel="noreferrer" className="rounded-xl border border-border p-4 transition-colors hover:border-primary/40 hover:bg-secondary/40"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-semibold">{alert.title || safeHostname(alert.url)}</p><p className="mt-1 truncate text-xs text-muted-foreground">{alert.companyName || safeHostname(alert.url)}{alert.location ? ` · ${alert.location}` : ''}</p></div><ExternalLink className="h-4 w-4 shrink-0 text-muted-foreground" /></div><div className="mt-3 flex flex-wrap items-center gap-2 text-[10px]"><span className="rounded-full bg-primary/10 px-2 py-1 font-semibold text-primary">{alert.matchScore}% match</span><span className="text-muted-foreground">{alert.telegramNotified ? 'Sent to Telegram' : 'Saved locally'}</span>{alert.foundAt && <time className="ml-auto text-muted-foreground">{new Date(alert.foundAt).toLocaleString()}</time>}</div></a>)}
        {(!settings.recentAlerts || settings.recentAlerts.length === 0) && <div className="col-span-full rounded-xl border border-dashed border-border py-10 text-center text-xs text-muted-foreground">No new match alerts yet. Run the monitor or leave it enabled overnight.</div>}
      </div>
    </section>
    <section className="rounded-2xl border-2 border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><h2 className="font-semibold">HiringCafe watch</h2><p className="mt-1 text-xs text-muted-foreground">Search preferences also power Dashboard Top Matches.</p></div><label className="flex items-center gap-3 border-2 border-border bg-background px-3 py-2 text-sm font-semibold"><input type="checkbox" checked={active} onChange={event => update('enabled', event.target.checked)} />Run overnight</label></div>
      <div className="mt-5 grid gap-4 md:grid-cols-2"><label className="space-y-1 text-xs font-semibold">Role or keywords<input value={settings.query} onChange={event => update('query', event.target.value)} className="field mt-1 w-full text-sm font-normal outline-none" placeholder="Cybersecurity analyst" /></label><label className="space-y-1 text-xs font-semibold">Preferred location<input value={settings.location} onChange={event => update('location', event.target.value)} className="field mt-1 w-full text-sm font-normal outline-none" placeholder="Chicago, IL" /></label><label className="space-y-1 text-xs font-semibold">Check every<select value={settings.intervalMinutes} onChange={event => update('intervalMinutes', Number(event.target.value))} className="field mt-1 w-full text-sm font-normal outline-none"><option value={15}>15 minutes</option><option value={30}>30 minutes</option><option value={60}>1 hour</option><option value={180}>3 hours</option><option value={360}>6 hours</option></select></label><label className="space-y-1 text-xs font-semibold">Minimum match score<input type="number" min={0} max={100} value={settings.minScore} onChange={event => update('minScore', Number(event.target.value))} className="field mt-1 w-full text-sm font-normal outline-none" /></label></div>
      <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={settings.remoteOnly} onChange={event => update('remoteOnly', event.target.checked)} />Only notify me about remote roles</label>
      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4"><button onClick={save} disabled={saving || !settings.query.trim()} className="inline-flex items-center gap-2 rounded-xl border-2 border-border bg-primary px-4 py-2.5 text-sm font-bold text-white shadow-sm disabled:opacity-40">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}Save monitor</button><button onClick={runNow} disabled={running || preparationBlocked} title={preparationBlocked ? `Blocked: ${readiness?.blockers.join(', ')}` : ''} className="inline-flex items-center gap-2 rounded-xl border-2 border-border px-4 py-2.5 text-sm font-semibold disabled:opacity-40">{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}Run now</button>{settings.lastRunAt && <p className="ml-auto text-xs text-muted-foreground">Last check {new Date(settings.lastRunAt).toLocaleString()} · {settings.lastFoundCount} found · {settings.lastNewCount} new</p>}</div>
      {preparationBlocked && <p className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700">Automated preparation is blocked: {readiness?.blockers.join(', ')}. Monitoring still works in Notify only mode.</p>}
      {settings.lastError && <p className="mt-3 rounded-xl border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-600">{settings.lastError}</p>}
    </section>
    <section className="rounded-2xl border-2 border-border bg-card p-5 shadow-sm"><div className="flex items-start gap-3"><MessageCircle className="mt-0.5 h-5 w-5 text-primary" /><div><h2 className="font-semibold">Telegram alerts</h2><p className="mt-1 text-xs text-muted-foreground">Use a dedicated bot from BotFather, send it a private message, then paste its token and your private chat ID. Phone buttons prepare applications on this PC; ready drafts receive a separate Submit button. Keep Nori running. Groups are not permitted to control applications. The token stays in the local Nori state file and is never returned to the browser.</p></div></div><div className="mt-5 grid gap-4 md:grid-cols-2"><label className="space-y-1 text-xs font-semibold">Bot token<input type="password" value={settings.telegramBotToken} onChange={event => update('telegramBotToken', event.target.value)} className="field mt-1 w-full text-sm font-normal outline-none" placeholder={settings.telegramConfigured ? 'Configured — enter only to replace' : '123456:ABC…'} /></label><label className="space-y-1 text-xs font-semibold">Chat ID<input value={settings.telegramChatId} onChange={event => update('telegramChatId', event.target.value)} className="field mt-1 w-full text-sm font-normal outline-none" placeholder="123456789" /></label></div><div className="mt-5 flex flex-wrap gap-2"><button onClick={save} disabled={saving} className="inline-flex items-center gap-2 rounded-xl border-2 border-border bg-primary px-4 py-2.5 text-sm font-bold text-white"><Save className="h-4 w-4" />Save connection</button><button onClick={testTelegram} disabled={testing || (!settings.telegramConfigured && !settings.telegramBotToken)} className="inline-flex items-center gap-2 rounded-xl border-2 border-border px-4 py-2.5 text-sm font-semibold disabled:opacity-40">{testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}Send test</button>{settings.telegramConfigured && <span className="inline-flex items-center gap-1.5 px-2 text-xs font-semibold text-emerald-600"><CheckCircle2 className="h-4 w-4" />Connected locally</span>}</div></section>
    <AIProvider />
    <Settings compact />
  </div>
}

function AIProvider() {
  const client = useQueryClient()
  const {data} = useQuery({queryKey: ['ai-provider'], queryFn: api.aiProvider, refetchInterval: 5000})
  const [draft, setDraft] = useState<{baseUrl: string; model: string; apiKey: string; transport: string} | null>(null)
  const [busy, setBusy] = useState(false)
  const value = draft || {baseUrl: data?.baseUrl || '', model: data?.model || '', apiKey: '', transport: data?.transport || 'api'}
  const save = async () => {
    setBusy(true)
    try { await api.saveAIProvider(value); setDraft(null); await client.invalidateQueries({queryKey: ['ai-provider']}); toast.success('Provider saved. Test the connection next.') }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Could not save provider') }
    finally { setBusy(false) }
  }
  const test = async () => {
    setBusy(true)
    try { const result = await api.testAIProvider(); await client.invalidateQueries({queryKey: ['ai-provider']}); if (!result.ok) throw new Error(result.lastError || 'AI returned no answer'); toast.success('AI provider answered successfully') }
    catch (error) { toast.error(error instanceof Error ? error.message : 'AI test failed') }
    finally { setBusy(false) }
  }
  return <section className="rounded-2xl border-2 border-border bg-card p-5 space-y-4">
    <h2 className="font-semibold">AI provider connection</h2>
    <label className="block text-sm">Connection method<select value={value.transport} onChange={event => setDraft({...value, transport: event.target.value, model: '', apiKey: ''})} className="field mt-2 w-full"><option value="chatgpt">ChatGPT sign-in (local Codex)</option><option value="api">API key provider</option></select></label>
    {value.transport === 'chatgpt' && <div className="rounded-xl bg-primary/5 p-3 text-sm"><p>{data?.login?.signedIn ? 'Signed in with ChatGPT' : 'Sign in once with codex login in a terminal, then test the connection.'}</p><p className="mt-2 text-xs text-muted-foreground">Uses the installed Codex CLI and your ChatGPT/Codex allowance. Nori never copies OAuth tokens. Requests are isolated, text-only, and read-only. Leave Model ID blank to use Codex’s default.</p></div>}
    <p className="text-xs text-muted-foreground">A saved key is not proof the provider works. Test it here. Keys entered here are encrypted for your Windows account and never returned to the browser.</p>
    {data?.baseUrl.includes('yunwu.ai') && <p className="rounded-xl bg-amber-500/10 p-3 text-sm">Yunwu reports migrated accounts must use OpenLux. If your account migrated, enter https://api.openlux.ai/v1 and a new key created there. Nori will not forward your old key automatically.</p>}
    {data?.lastError && <p role="alert" className="rounded-xl bg-red-500/10 p-3 text-sm text-red-600">{data.lastError}</p>}
    <div className="grid gap-4 md:grid-cols-2">{value.transport !== 'chatgpt' && <label className="text-sm">API base URL<input value={value.baseUrl} onChange={event => setDraft({...value, baseUrl: event.target.value})} className="field mt-2 w-full" /></label>}<label className="text-sm">Model ID<input value={value.model} onChange={event => setDraft({...value, model: event.target.value})} className="field mt-2 w-full" /></label></div>
    {value.transport !== 'chatgpt' && <label className="block text-sm">API key<input type="password" autoComplete="off" value={value.apiKey} onChange={event => setDraft({...value, apiKey: event.target.value})} placeholder={data?.configured ? 'Configured — enter a new key to replace' : 'Provider API key'} className="field mt-2 w-full" /></label>}
    <div className="flex gap-3"><button onClick={save} disabled={busy || !draft} className="rounded-xl bg-primary px-4 py-2 text-sm text-white disabled:opacity-40">Save encrypted connection</button><button onClick={test} disabled={busy || Boolean(draft)} className="rounded-xl border border-border px-4 py-2 text-sm disabled:opacity-40">{busy ? 'Working…' : 'Test saved connection'}</button></div>
  </section>
}

export function Inbox() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['inbox'], queryFn: api.inbox, refetchInterval: 5000 })
  const [clientId, setClientId] = useState('')
  const [busy, setBusy] = useState('')
  const [category, setCategory] = useState('all')
  const connect = async () => {
    if (!clientId.trim()) return
    setBusy('connect')
    try {
      const redirect = `${window.location.origin}/api/inbox/gmail/callback`
      const result = await api.gmailConnect(clientId.trim(), redirect)
      window.open(result.authorizationUrl, '_blank', 'noopener,noreferrer')
      toast.info('Complete Google authorization, then return here and sync')
    } catch (err) { toast.error(err instanceof Error ? err.message : 'Could not start Gmail connection') }
    finally { setBusy('') }
  }
  const sync = async () => {
    setBusy('sync')
    try { const result = await api.gmailSync(50); await queryClient.invalidateQueries({ queryKey: ['inbox'] }); toast.success(`${result.count} job messages synced`) }
    catch (err) { toast.error(err instanceof Error ? err.message : 'Gmail sync failed') }
    finally { setBusy('') }
  }
  const disconnect = async () => {
    if (!window.confirm('Remove Nori’s locally encrypted Gmail credentials? This does not delete email.')) return
    setBusy('disconnect')
    try { await api.gmailDisconnect(); await queryClient.invalidateQueries({ queryKey: ['inbox'] }); toast.success('Gmail disconnected locally') }
    catch (err) { toast.error(err instanceof Error ? err.message : 'Could not disconnect Gmail') }
    finally { setBusy('') }
  }
  const categories = ['all', 'interview', 'offer', 'action_required', 'acknowledgment', 'rejection', 'verification', 'other']
  const messages = (data?.messages || []).filter(message => category === 'all' || message.category === category)
  return <div className="max-w-5xl space-y-6"><Header title="Inbox" subtitle="Read-only Gmail signals for applications, interviews, offers, and follow-ups." icon={InboxIcon} />
    {error && <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">{error.message}</div>}
    <section className="rounded-2xl border border-border bg-card p-5"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-start"><div><h2 className="font-semibold">Gmail read-only connection</h2><p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">Nori requests only Gmail read access, stores encrypted OAuth credentials for your Windows account, and saves at most 500 message headers and short snippets locally. It cannot send or delete mail.</p></div><span className={`rounded-full px-3 py-1 text-xs font-semibold ${data?.authorized ? 'bg-emerald-500/10 text-emerald-500' : 'bg-secondary text-muted-foreground'}`}>{data?.authorized ? 'Connected' : 'Not connected'}</span></div>
      {!data?.authorized ? <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]"><label className="text-xs font-semibold">Google OAuth desktop client ID<input value={clientId} onChange={event => setClientId(event.target.value)} placeholder="…apps.googleusercontent.com" className="field mt-1 w-full text-sm font-normal text-foreground outline-none" /></label><button onClick={connect} disabled={busy === 'connect' || !clientId.trim()} className="mt-auto inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-white disabled:opacity-40">{busy === 'connect' && <Loader2 className="h-4 w-4 animate-spin" />}Connect Gmail</button><p className="text-xs text-muted-foreground md:col-span-2">Create a Desktop OAuth client in Google Cloud, enable the Gmail API, and add this local callback if prompted: <code className="text-foreground">{window.location.origin}/api/inbox/gmail/callback</code></p></div> : <div className="mt-5 flex flex-wrap gap-2"><button onClick={sync} disabled={Boolean(busy)} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white">{busy === 'sync' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}Sync inbox</button><button onClick={disconnect} disabled={Boolean(busy)} className="rounded-xl border border-border px-4 py-2.5 text-sm">Disconnect locally</button></div>}
      {data?.connectionError && <p className="mt-3 text-xs text-red-500">{data.connectionError}</p>}
    </section>
    <section className="overflow-hidden rounded-2xl border border-border bg-card"><div className="flex flex-col gap-3 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold">Job messages</h2><p className="mt-1 text-xs text-muted-foreground">{data?.count || 0} cached locally</p></div><select value={category} onChange={event => setCategory(event.target.value)} className="h-9 rounded-xl border border-border bg-secondary px-3 text-xs">{categories.map(item => <option key={item} value={item}>{item.replace('_', ' ')}</option>)}</select></div>
      {isLoading ? <div className="grid h-48 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div> : messages.length ? <div className="divide-y divide-border">{messages.map(message => <article key={message.id} className="p-5"><div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="text-sm font-semibold">{message.subject || '(No subject)'}</h3><p className="mt-1 text-xs text-muted-foreground">{message.sender}</p></div><span className="rounded-full bg-primary/10 px-2.5 py-1 text-[10px] font-semibold uppercase text-primary">{message.category.replace('_', ' ')}</span></div>{message.snippet && <p className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">{message.snippet}</p>}<p className="mt-3 text-[10px] text-muted-foreground">{message.timestamp ? new Date(message.timestamp).toLocaleString() : message.date}</p></article>)}</div> : <div className="py-16 text-center"><InboxIcon className="mx-auto h-10 w-10 text-muted-foreground/30" /><h2 className="mt-4 font-semibold">No matching messages yet</h2><p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{data?.authorized ? 'Click Sync inbox to fetch recent job-related messages.' : 'Connect Gmail to classify recent job-related messages.'}</p></div>}
    </section>
  </div>
}

export function Tracker() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [moving, setMoving] = useState('')
  const [adding, setAdding] = useState(false)
  const [savingEntry, setSavingEntry] = useState(false)
  const [entry, setEntry] = useState({ companyName: '', jobTitle: '', url: '', stage: 'applied' })
  const { data } = useQuery({ queryKey: ['applications', 'all'], queryFn: () => api.listApplications('all'), refetchInterval: 3000 })
  const columns = ['applied', 'interviewing', 'offer', 'rejected']
  const move = async (id: string, stage: string) => {
    setMoving(id)
    try {
      await api.updateTrackerStage(id, stage)
      await queryClient.invalidateQueries({ queryKey: ['applications'] })
      toast.success(`Moved to ${stage}`)
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not move application') }
    finally { setMoving('') }
  }
  const addEntry = async () => {
    if (!entry.companyName.trim() && !entry.jobTitle.trim()) return
    setSavingEntry(true)
    try { await api.addTrackerEntry(entry); setEntry({ companyName: '', jobTitle: '', url: '', stage: 'applied' }); setAdding(false); await queryClient.invalidateQueries({ queryKey: ['applications'] }); toast.success('Application added to tracker') }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Could not add tracker entry') }
    finally { setSavingEntry(false) }
  }
  return <div className="space-y-6"><div className="flex flex-wrap items-start justify-between gap-3"><Header title="Tracker" subtitle="Track applications from submitted through offer." icon={Goal} /><div className="flex gap-2"><button onClick={() => setAdding(value => !value)} className="inline-flex items-center gap-2 rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white">{adding ? 'Close' : 'Add application'}</button><a href={api.trackerExportUrl} download="nori-tracker.csv" className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground"><Download className="h-3.5 w-3.5" />Export CSV</a></div></div>{adding && <section className="rounded-2xl border border-border bg-card p-4"><div className="grid gap-3 md:grid-cols-4"><input value={entry.companyName} onChange={event => setEntry({...entry, companyName: event.target.value})} placeholder="Company" className="field text-sm" /><input value={entry.jobTitle} onChange={event => setEntry({...entry, jobTitle: event.target.value})} placeholder="Role" className="field text-sm" /><input value={entry.url} onChange={event => setEntry({...entry, url: event.target.value})} placeholder="Posting URL (optional)" className="field text-sm" /><select value={entry.stage} onChange={event => setEntry({...entry, stage: event.target.value})} className="field text-sm"><option value="applied">Applied</option><option value="interviewing">Interviewing</option><option value="offer">Offer</option><option value="rejected">Rejected</option></select></div><div className="mt-3 flex justify-end"><button onClick={addEntry} disabled={savingEntry || (!entry.companyName.trim() && !entry.jobTitle.trim())} className="rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-white disabled:opacity-40">{savingEntry ? 'Adding…' : 'Add to tracker'}</button></div></section>}<div className="grid gap-3 lg:grid-cols-4">{columns.map(status => {
    const applications = data?.applications.filter(a => (a.trackerStage || (a.status === 'applied' ? 'applied' : '')) === status) || []
    return <section key={status} className="min-h-64 rounded-2xl border border-border bg-card/60 p-3"><div className="mb-3 flex items-center justify-between"><h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{status}</h2><span className="rounded-full bg-secondary px-2 py-0.5 text-xs">{applications.length}</span></div>{applications.map(a => <div key={a.id} className="mb-2 rounded-xl border border-border bg-background p-3 text-sm"><button onClick={() => navigate(`/applications/${a.id}`)} className="w-full text-left font-medium hover:text-primary">{a.company || safeHostname(a.url)}</button><p className="mt-1 truncate text-xs text-muted-foreground">{a.title || 'Application'}</p><select aria-label={`Move ${a.title || 'application'}`} value={status} disabled={moving === a.id} onChange={event => move(a.id, event.target.value)} className="mt-3 h-8 w-full rounded-lg border border-border bg-secondary px-2 text-xs">{columns.map(stage => <option value={stage} key={stage}>{stage}</option>)}</select></div>)}{applications.length === 0 && <p className="py-10 text-center text-xs text-muted-foreground/50">No roles</p>}</section>
  })}</div></div>
}

export function Resume() {
  const navigate = useNavigate()
  const { data } = useQuery({ queryKey: ['profile'], queryFn: api.getProfile })
  const ready = Boolean(data?.resumeFormat && data?.resumePath)
  return <div className="max-w-5xl space-y-6"><Header title="Resume" subtitle="Manage your source resume and per-application tailoring." icon={FileUser} /><div className="grid gap-5 md:grid-cols-[1fr_320px]"><div className="rounded-2xl border border-border bg-card p-6"><div className="flex items-center justify-between"><div><p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Source resume</p><h2 className="mt-2 text-xl font-semibold">{data?.personalInformation?.firstName || 'Candidate'} Resume</h2><p className="mt-1 text-sm text-muted-foreground">{ready ? 'PDF · Stored locally · Available for applications' : 'No usable PDF imported yet'}</p></div><span className={`rounded-full px-3 py-1 text-xs ${ready ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>{ready ? 'Ready' : 'Missing'}</span></div><div className="mt-8 flex gap-2">{ready && <a href={api.sourceResumeUrl} target="_blank" rel="noreferrer" className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white"><Download className="mr-2 inline h-4 w-4" />Open PDF</a>}<button onClick={() => navigate('/profile')} className="rounded-xl border border-border px-4 py-2 text-sm">Edit profile / import</button></div></div><div className="rounded-2xl border border-border bg-card p-5"><Sparkles className="h-5 w-5 text-primary" /><h3 className="mt-3 font-semibold">Per-job documents</h3><p className="mt-2 text-sm text-muted-foreground">Nori creates honest tailored versions during a dry run. Generated files appear on that application’s Documents tab.</p><div className="mt-4 space-y-2 text-xs text-muted-foreground"><p><CheckCircle2 className="mr-2 inline h-3.5 w-3.5 text-emerald-400" />No experience is fabricated</p><p><CheckCircle2 className="mr-2 inline h-3.5 w-3.5 text-emerald-400" />You review before submission</p></div></div></div></div>
}

export function Research() {
  const cards = [
    {title:'Interview playbooks', text:'Structured preparation by role and company.', details:['Build six short STAR stories from your real experience.','Map each story to a requirement in the posting.','Prepare two role questions and one business-impact question.']},
    {title:'ATS fundamentals', text:'What applicant tracking systems actually parse and rank.', details:['Use ordinary headings such as Experience, Education, and Skills.','Keep contact details as text, not images.','Mirror truthful role vocabulary; keyword stuffing is not useful.']},
    {title:'Application strategy', text:'Use trace evidence to improve answer and resume quality.', details:['Fix repeated fallback answers in your Profile.','Prioritize strong matches instead of raw application count.','Review every generated answer and document before submit.']},
  ]
  const [selected, setSelected] = useState(0)
  const guide = cards[selected]
  return <div className="max-w-5xl space-y-6"><Header title="Research" subtitle="Practical guides for applications, ATS systems, and interviews." icon={Microscope} /><div className="grid gap-4 md:grid-cols-3">{cards.map((card,i) => <article key={card.title} className={`group rounded-2xl border bg-card p-5 ${selected === i ? 'border-primary/60' : 'border-border'}`}><span className="text-xs font-semibold text-primary">0{i+1}</span><h2 className="mt-8 font-semibold">{card.title}</h2><p className="mt-2 text-sm text-muted-foreground">{card.text}</p><button onClick={() => setSelected(i)} className="mt-6 text-xs font-semibold text-primary">Read guide</button></article>)}</div><section className="rounded-2xl border border-border bg-card p-6"><p className="text-xs font-semibold uppercase tracking-wider text-primary">Selected guide</p><h2 className="mt-2 text-xl font-semibold">{guide.title}</h2><ul className="mt-4 space-y-3 text-sm text-muted-foreground">{guide.details.map(item => <li key={item} className="flex gap-3"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />{item}</li>)}</ul></section></div>
}

export function Settings({ compact = false }: { compact?: boolean }) {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const [draft, setDraft] = useState<ApplySettings | null>(null)
  const [saving, setSaving] = useState(false)
  const settings = draft || data
  if (!settings) return null
  const update = (key: string, value: unknown) => setDraft({...settings, [key]: value})
  const save = async () => { setSaving(true); try { const safe = {...settings, autoSubmitApplication: false, reviewBeforeSubmit: true}; const result = await api.updateSettings(safe); queryClient.setQueryData(['settings'], result.settings); setDraft(null); toast.success('Application settings saved') } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not save settings') } finally { setSaving(false) } }
  return <div className={compact ? '' : 'max-w-4xl space-y-6'}>{!compact && <Header title="Settings" subtitle="Document behavior and local safety controls." icon={SettingsIcon} />}<section className="rounded-2xl border border-border bg-card p-5"><div className="grid gap-5 md:grid-cols-2"><label className="space-y-2 text-sm"><span className="font-medium">Resume optimization</span><select value={settings.optimizationMode} onChange={e => update('optimizationMode', e.target.value)} className="w-full rounded-xl border border-border bg-secondary px-3 py-2.5"><option value="off">Off</option><option value="honest">Honest</option><option value="aggressive">Aggressive</option></select></label><label className="space-y-2 text-sm"><span className="font-medium">Cover letter</span><select value={settings.coverLetterMode} onChange={e => update('coverLetterMode', e.target.value)} className="w-full rounded-xl border border-border bg-secondary px-3 py-2.5"><option value="off">Off</option><option value="honest">Honest</option><option value="generated">Generated</option></select></label></div><div className="mt-5 divide-y divide-border">{[['autoApproveResume','Use the prepared resume in the review draft'],['autoApproveCoverLetter','Use the prepared cover letter in the review draft']].map(([key,label]) => <label key={key} className="flex items-center justify-between py-3 text-sm"><span>{label}</span><input type="checkbox" checked={Boolean(settings[key])} onChange={e => update(key, e.target.checked)} className="h-4 w-4 accent-violet-500" /></label>)}</div><div className="mt-5 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-muted-foreground"><p><ShieldCheck className="mr-2 inline h-4 w-4 text-emerald-400" />Manual preparation stops at review. Scheduled applications follow the separate automation mode saved above.</p><div className="mt-3 flex justify-end"><button onClick={save} disabled={saving} className="rounded-lg bg-primary px-3 py-2 font-medium text-white disabled:opacity-50">{saving ? <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 inline h-3.5 w-3.5" />}Save</button></div></div></section></div>
}
