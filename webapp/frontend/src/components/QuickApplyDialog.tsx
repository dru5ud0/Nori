import * as Dialog from '@radix-ui/react-dialog'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, CheckCircle2, ExternalLink, FileSearch, Loader2, ShieldCheck, UserRoundCheck, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api, type CompanyIdentity, type PreflightResult } from '../api'

const blockerCopy: Record<string, string> = {
  'invalid-url': 'Enter a complete http or https job URL.',
  'linkedin-apply-url-unresolved': 'LinkedIn guest links hide the external apply URL. Open the job with the browser companion first.',
  'unsupported-ats': 'Nori recognizes this destination but does not yet have a safe form walker for it.',
  'duplicate-application': 'This job is already tracked in Mission Control.',
  'profile-incomplete': 'Complete the required profile fields before preparing an application.',
  'test-profile-active': 'The demo Jane Doe profile is still active. Import and review your real resume first.',
}

export function QuickApplyDialog({ open, onOpenChange, initialUrl = '', identity = {} }: { open: boolean; onOpenChange: (open: boolean) => void; initialUrl?: string; identity?: CompanyIdentity }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [url, setUrl] = useState(initialUrl)
  const [checking, setChecking] = useState(false)
  const [queueing, setQueueing] = useState(false)
  const [result, setResult] = useState<PreflightResult | null>(null)

  useEffect(() => { if (open) { setUrl(initialUrl); setResult(null) } }, [open, initialUrl])

  const check = async () => {
    if (!url.trim()) return
    setChecking(true)
    try { setResult(await api.preflight(url.trim())) }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Preflight failed') }
    finally { setChecking(false) }
  }

  const queue = async () => {
    if (!result?.canQueue) return
    setQueueing(true)
    try {
      const sameJob = result.url.replace(/\/$/, '') === initialUrl.trim().replace(/\/$/, '')
      const created = await api.createApplication(result.url, sameJob ? identity : {})
      toast.success('Nori AI is preparing a review draft')
      queryClient.invalidateQueries({ queryKey: ['applications'] })
      queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
      onOpenChange(false)
      navigate(`/applications/${created.applicationId}`)
      void api.runApplication(created.applicationId).then(() => {
        queryClient.invalidateQueries({ queryKey: ['application', created.applicationId] })
        queryClient.invalidateQueries({ queryKey: ['trace', created.applicationId] })
        queryClient.invalidateQueries({ queryKey: ['applications'] })
        queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
        toast.success('Review draft is ready')
      }).catch(error => toast.error(error instanceof Error ? error.message : 'Preparation failed'))
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not queue application') }
    finally { setQueueing(false) }
  }

  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[80] bg-black/65 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out" />
      <Dialog.Content className="fixed left-1/2 top-1/2 z-[90] max-h-[90vh] w-[calc(100%-24px)] max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[24px] border border-border bg-[#101015] p-1 shadow-2xl">
        <div className="border-b border-border/70 p-5 md:p-6"><div className="flex items-start justify-between gap-4"><div><Dialog.Title className="text-xl font-bold">Prepare with Nori AI</Dialog.Title><Dialog.Description className="mt-1 text-sm text-muted-foreground">Check the destination, profile, and safety mode before Nori creates a review draft.</Dialog.Description></div><Dialog.Close className="rounded-xl p-2 text-muted-foreground hover:bg-secondary hover:text-foreground" aria-label="Close"><X className="h-4 w-4" /></Dialog.Close></div><div className="mt-5 flex gap-2"><input autoFocus value={url} onChange={e => { setUrl(e.target.value); setResult(null) }} onKeyDown={e => e.key === 'Enter' && check()} placeholder="https://company.com/jobs/..." className="field min-w-0 flex-1 text-sm outline-none focus:border-primary/60" /><button onClick={check} disabled={checking || !url.trim()} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-white disabled:opacity-40">{checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}Check job</button></div></div>

        {!result && <div className="grid gap-3 p-5 md:grid-cols-3 md:p-6">{[['1','Resolve','Follow redirects and identify the actual ATS.'],['2','Validate','Check duplicates and required profile fields.'],['3','Review','Prepare answers without submitting anything.']].map(([n,title,text]) => <div key={n} className="rounded-2xl border border-border bg-card/60 p-4"><span className="font-mono text-[10px] text-primary">0{n}</span><h3 className="mt-5 text-sm font-semibold">{title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p></div>)}</div>}

        {result && <div className="space-y-4 p-5 md:p-6">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-border bg-card p-4"><p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Destination</p><p className="mt-3 text-sm font-semibold">{result.atsName || 'Unknown'}</p><p className="mt-1 text-xs text-muted-foreground">{Math.round(result.confidence * 100)}% detected · {result.capabilityLevel.replaceAll('-', ' ')}</p></div>
            <div className="rounded-2xl border border-border bg-card p-4"><p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Profile</p><p className={`mt-3 text-sm font-semibold ${result.profileReady ? 'text-emerald-400' : 'text-amber-400'}`}>{result.profileReady ? 'Application ready' : `${result.missingFields.length} fields missing`}</p><p className="mt-1 text-xs text-muted-foreground">Required application defaults</p></div>
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[.05] p-4"><p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400">Safety mode</p><p className="mt-3 text-sm font-semibold">Prepare + review</p><p className="mt-1 text-xs text-muted-foreground">No automatic submission</p></div>
          </div>

          {result.blockers.length > 0 && <div className="rounded-2xl border border-amber-500/25 bg-amber-500/[.06] p-4"><div className="flex items-center gap-2 text-sm font-semibold text-amber-400"><AlertTriangle className="h-4 w-4" />Action needed</div><ul className="mt-3 space-y-2">{result.blockers.map(blocker => <li key={blocker} className="text-sm text-muted-foreground">{blockerCopy[blocker] || blocker}</li>)}</ul>{(result.blockers.includes('profile-incomplete') || result.blockers.includes('test-profile-active')) && <button onClick={() => { onOpenChange(false); navigate('/profile') }} className="mt-4 rounded-xl border border-amber-500/30 px-3 py-2 text-xs font-semibold text-amber-400">Open profile setup <ArrowRight className="ml-1 inline h-3 w-3" /></button>}{result.linkedinOnly && <button onClick={() => { onOpenChange(false); navigate('/linkedin') }} className="mt-4 rounded-xl border border-amber-500/30 px-3 py-2 text-xs font-semibold text-amber-400">Open LinkedIn harvest <ExternalLink className="ml-1 inline h-3 w-3" /></button>}</div>}

          {result.warnings.length > 0 && <div className="rounded-2xl border border-sky-500/20 bg-sky-500/[.05] p-4"><p className="text-sm font-semibold text-sky-300">Adapter capability</p><ul className="mt-2 space-y-1">{result.warnings.map(warning => <li key={warning} className="text-xs leading-5 text-muted-foreground">{warning}</li>)}</ul></div>}

          {result.canQueue && <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[.05] p-4"><div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-400" /><div><p className="text-sm font-semibold">Ready to prepare</p><p className="mt-1 text-xs leading-5 text-muted-foreground">Nori will immediately walk and fill a dry-run draft, then stop in Needs you. You can change any collected answer before authorizing a real submission.</p></div></div></div>}

          <div className="flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck className="h-4 w-4 text-emerald-400" />Explicit approval remains required.</p><div className="flex gap-2"><Dialog.Close className="rounded-xl border border-border px-4 py-2.5 text-sm font-medium">Cancel</Dialog.Close><button onClick={queue} disabled={!result.canQueue || queueing} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-35">{queueing ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserRoundCheck className="h-4 w-4" />}Prepare application</button></div></div>
        </div>}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
