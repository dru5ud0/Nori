import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import { api, type Answer } from '../api'
import {
  ArrowLeft, CheckCircle2, XCircle, ExternalLink,
  Clock, AlertCircle, Play, Bot, User, FileText, EyeOff, ChevronDown, ShieldAlert, X,
  Download, Paperclip, Pencil, Save, Archive, RotateCw
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { CompanyLogo } from '../components/CompanyLogo'

const SOURCE_ICONS: Record<string, React.FC<{ className?: string }>> = {
  'profile-direct': User,
  'llm': Bot,
  'skip': EyeOff,
  'fallback': FileText,
  'user-override': Pencil,
}

const SOURCE_COLORS: Record<string, string> = {
  'profile-direct': 'text-blue-400',
  'llm': 'text-blue-700',
  'skip': 'text-muted-foreground',
  'fallback': 'text-amber-400',
  'user-override': 'text-emerald-600',
}

const STATUS_BADGE: Record<string, string> = {
  queued: 'bg-queued/10 text-queued border-queued/30',
  review: 'bg-review/10 text-review border-review/30',
  running: 'bg-running/10 text-running border-running/30',
  applied: 'bg-applied/10 text-applied border-applied/30',
  failed: 'bg-failed/10 text-failed border-failed/30',
  paused: 'bg-paused/10 text-paused border-paused/30',
}

const APPLICATION_ERROR_GUIDANCE: Record<string, { title: string; detail: string }> = {
  'jobvite-data-consent-required': {
    title: 'Consent needed on Jobvite',
    detail: 'Open the original posting, choose your residence/language, and review Jobvite’s privacy terms yourself. After you accept or decline, return to Nori and regenerate the draft.',
  },
  'smartrecruiters-human-challenge-required': {
    title: 'Human verification needed',
    detail: 'Open the original posting and complete the employer’s verification yourself. Nori does not solve or bypass CAPTCHAs. Return here and regenerate afterward.',
  },
  'bot-challenge-detected': {
    title: 'Job site verification needed',
    detail: 'This employer blocked the automated browser. Open the original posting in your browser, complete any human verification or sign-in, then return to Nori and regenerate the draft. Nori does not bypass security challenges.',
  },
  'polymer-browser-verification-required': {
    title: 'Polymer browser verification needed',
    detail: 'Polymer showed its Cloudflare verification page to Nori’s application browser. Open the original posting in your browser and complete the verification yourself, then regenerate the draft. Nori does not solve or bypass that security check.',
  },
  'indeed-account-required': {
    title: 'Indeed sign-in needed',
    detail: 'Indeed requires an account before it exposes this hosted application or company-site handoff. Open the original posting, sign in yourself, then regenerate the draft so Nori can reuse the saved session.',
  },
  'indeed-phone-verification-required': {
    title: 'Indeed phone verification needed',
    detail: 'Indeed is waiting for a phone or one-time-code check. Complete that verification yourself in the original posting, then regenerate the draft. Nori never requests or enters verification codes.',
  },
  'indeed-human-verification-required': {
    title: 'Indeed human verification needed',
    detail: 'Indeed displayed a human-verification checkpoint. Complete it yourself in the original posting, then regenerate the draft. Nori does not solve or bypass CAPTCHAs.',
  },
  'indeed-browser-verification-required': {
    title: 'Indeed blocked the application browser',
    detail: 'Indeed blocked Nori’s isolated browser before the apply flow loaded. Open the original posting in your normal browser, complete any verification or sign-in yourself, then regenerate the draft. Nori does not bypass Indeed’s protections.',
  },
  'indeed-external-ats-not-supported': {
    title: 'Employer site needs manual review',
    detail: 'Indeed handed this job to an employer site that Nori could not identify safely. Open the original posting and complete this application manually; Nori will not guess at an unknown form.',
  },
  'naukri-account-required': {
    title: 'Naukri account needed',
    detail: 'This posting requires a Naukri candidate profile before its application action becomes available. Sign in or register on the original posting yourself; Nori will not start Google sign-in or create an account.',
  },
  'naukri-one-click-review-required': {
    title: 'Review this Naukri application manually',
    detail: 'Naukri exposes an Apply action that may immediately send your stored candidate profile. Nori did not click it during draft preparation. Review your Naukri profile and trigger this application manually.',
  },
  'naukri-browser-verification-required': {
    title: 'Naukri browser verification needed',
    detail: 'Naukri blocked or challenged Nori’s isolated browser. Open the original posting in your normal browser and complete the checkpoint yourself; Nori does not bypass site protections.',
  },
  'bullhorn-job-closed': {
    title: 'This Bullhorn posting is closed',
    detail: 'Bullhorn’s published-job API reports that this exact job is no longer open. Nori did not send any candidate data.',
  },
  'bullhorn-job-not-public': {
    title: 'This Bullhorn posting is no longer public',
    detail: 'Bullhorn no longer exposes this job for public applications. Nori did not send any candidate data.',
  },
  'bullhorn-job-fetch': {
    title: 'Bullhorn job verification failed',
    detail: 'Nori could not verify the exact published job through Bullhorn’s read-only API. Regenerate later or open the original posting; no candidate data was sent.',
  },
  'bullhorn-resume-invalid': {
    title: 'Bullhorn needs a valid résumé file',
    detail: 'Choose a non-empty PDF, DOC, DOCX, RTF, or TXT résumé no larger than 5 MB, regenerate the draft, and review it before authorizing submission.',
  },
  'bullhorn-submission-not-confirmed': {
    title: 'Bullhorn did not return a complete receipt',
    detail: 'Do not retry until you check the employer portal or your email. Nori only marks a Bullhorn application applied when the API returns matching job, candidate, submission, status, and résumé-parse evidence.',
  },
  'captcha-required': {
    title: 'Human verification needed before submission',
    detail: 'Nori prepared the application but found an employer CAPTCHA. Review the saved answers, open the original posting, and complete the verification yourself. Nori does not solve or bypass CAPTCHAs.',
  },
  'workday-account-required': {
    title: 'Workday sign-in needed',
    detail: 'Open the original posting and sign in or create the employer-specific Workday account, then return to Nori and regenerate the draft.',
  },
  'adp-account-required': {
    title: 'ADP sign-in needed',
    detail: 'Open the original posting and sign in or create the employer-specific ADP candidate profile. Nori preserves the browser session and can regenerate the draft after the identity checkpoint is complete.',
  },
  'successfactors-account-required': {
    title: 'SuccessFactors account needed',
    detail: 'This employer requires its own SAP SuccessFactors candidate account before the application form. Open the posting, sign in or create that account, then regenerate the draft in Nori.',
  },
  'ultipro-account-required': {
    title: 'UKG candidate sign-in needed',
    detail: 'This employer routes applications through a UKG Pro candidate account. Open the original posting and sign in or create the employer-specific account, then regenerate the draft in Nori.',
  },
  'avature-account-required': {
    title: 'Employer candidate account needed',
    detail: 'This Avature employer requires a candidate account before the remaining application steps. Open the original posting, complete sign-in or registration, then regenerate the draft in Nori.',
  },
  'join-email-verification-required': {
    title: 'JOIN email verification needed',
    detail: 'Nori filled the local email field but did not press Continue because JOIN can send a magic link and start an authenticated application. Open the original posting, complete that checkpoint yourself, then regenerate the draft so Nori can reuse the saved session.',
  },
  'job-no-longer-open': {
    title: 'This posting is closed',
    detail: 'The employer is no longer accepting applications for this posting. Skip it to remove it from your review queue.',
  },
}

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [tab, setTab] = useState<'overview' | 'answers' | 'documents' | 'receipt'>('overview')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [answerDraft, setAnswerDraft] = useState<Record<string, any>>({})
  const [answersDirty, setAnswersDirty] = useState(false)

  const { data: app, isLoading } = useQuery({
    queryKey: ['application', id],
    queryFn: () => api.getApplication(id!),
    enabled: !!id,
    refetchInterval: query => query.state.data?.status === 'running' ? 2000 : false,
  })

  const { data: trace } = useQuery({
    queryKey: ['trace', id],
    queryFn: () => api.getTrace(id!),
    enabled: !!id,
  })

  useEffect(() => {
    if (trace?.answers && !answersDirty) {
      setAnswerDraft(Object.fromEntries(trace.answers.map(answer => [answer.fieldId, answer.value])))
    }
  }, [trace, answersDirty])

  const changedAnswers = () => Object.fromEntries(Object.entries(answerDraft).filter(([key, value]) =>
    JSON.stringify(value) !== JSON.stringify(trace?.answers.find(answer => answer.fieldId === key)?.value)))

  const saveAnswersMutation = useMutation({
    mutationFn: () => api.saveAnswers(id!, changedAnswers()),
    onSuccess: async result => {
      setAnswersDirty(false)
      await queryClient.invalidateQueries({ queryKey: ['trace', id] })
      await queryClient.invalidateQueries({ queryKey: ['application', id] })
      toast.success(`${result.saved} reviewed answers saved`)
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const approveMutation = useMutation({
    mutationFn: async () => {
      if (answersDirty) await api.saveAnswers(id!, changedAnswers())
      return api.approveApplication(id!)
    },
    onSuccess: async () => { setConfirmOpen(false); setConfirmed(false); setAnswersDirty(false); toast.success('Submission run completed'); await queryClient.invalidateQueries({ queryKey: ['application', id] }); await queryClient.invalidateQueries({ queryKey: ['trace', id] }); await queryClient.invalidateQueries({ queryKey: ['applications'] }); await queryClient.invalidateQueries({ queryKey: ['bootstrap'] }) },
    onError: (error: Error) => toast.error(error.message),
    onSettled: async () => { await queryClient.invalidateQueries({ queryKey: ['application', id] }); await queryClient.invalidateQueries({ queryKey: ['trace', id] }); await queryClient.invalidateQueries({ queryKey: ['applications'] }); await queryClient.invalidateQueries({ queryKey: ['bootstrap'] }) },
  })

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      if (answersDirty) await api.saveAnswers(id!, changedAnswers())
      await api.rejectApplication(id!)
      return api.runApplication(id!)
    },
    onSuccess: () => { setAnswersDirty(false); toast.success('Draft regenerated from your current profile') },
    onError: (error: Error) => toast.error(error.message),
    onSettled: async () => {
      await queryClient.invalidateQueries({queryKey: ['application', id]})
      await queryClient.invalidateQueries({queryKey: ['trace', id]})
      await queryClient.invalidateQueries({queryKey: ['applications']})
    },
  })

  const rejectMutation = useMutation({
    mutationFn: () => api.rejectApplication(id!),
    onSuccess: async () => { toast.success('Application skipped'); await queryClient.invalidateQueries({ queryKey: ['application', id] }); await queryClient.invalidateQueries({ queryKey: ['applications'] }); await queryClient.invalidateQueries({ queryKey: ['bootstrap'] }) },
    onError: (error: Error) => toast.error(error.message),
  })

  const manualResolutionMutation = useMutation({
    mutationFn: (resolution: 'applied' | 'skipped') => api.resolveApplication(id!, resolution),
    onSuccess: async result => {
      toast.success(result.resolution === 'applied' ? 'Marked as manually applied' : 'Application skipped')
      await queryClient.invalidateQueries({ queryKey: ['application', id] })
      await queryClient.invalidateQueries({ queryKey: ['applications'] })
      await queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
    },
    onError: (error: Error) => toast.error(error.message),
  })

  const runMutation = useMutation({
    mutationFn: () => api.runApplication(id!),
    onSuccess: async () => { toast.success('Review draft is ready'); await queryClient.invalidateQueries({ queryKey: ['application', id] }); await queryClient.invalidateQueries({ queryKey: ['trace', id] }); await queryClient.invalidateQueries({ queryKey: ['applications'] }); await queryClient.invalidateQueries({ queryKey: ['bootstrap'] }) },
    onError: (error: Error) => toast.error(error.message),
  })

  const archiveMutation = useMutation({
    mutationFn: () => api.setApplicationArchived(id!, !app?.archived),
    onSuccess: async result => {
      await queryClient.invalidateQueries({ queryKey: ['application', id] })
      await queryClient.invalidateQueries({ queryKey: ['applications'] })
      await queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
      toast.success(result.archived ? 'Application archived' : 'Application restored')
      if (result.archived) navigate('/applications')
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

  if (!app) {
    return <div className="text-muted-foreground">Application not found</div>
  }

  // Conditional fields are intentionally preserved in the backend trace for
  // replay/debugging, but they are not visible questions for the candidate.
  // Hiding them here also prevents vendor-generated UUIDs (common in Ashby)
  // from looking like empty questions in the review UI.
  const answers = (trace?.answers ?? []).filter(answer => !(
    answer.source === 'skip' && String(answer.reason || '').startsWith('conditional-hidden:')
  ))
  const application = app as any
  const resume = application.documents?.resume || {}
  const coverLetter = application.documents?.coverLetter || {}
  const uploadedDocuments = application.answersSummary?.uploaded_documents || []
  const preparedDocuments = application.answersSummary?.prepared_documents || []
  const resumeUpload = uploadedDocuments.find((item: any) => item.kind === 'resume')
  const resumePrepared = preparedDocuments.find((item: any) => item.kind === 'resume')
  const coverUpload = uploadedDocuments.find((item: any) => item.kind === 'cover_letter')
  const reviewIssues: string[] = [
    ...(application.answersSummary?.field_failures || []).map((failure: any) => `${failure.fieldId}: ${failure.error}`),
    ...(resume.qualityIssues || []).map((issue: string) => `Resume: ${issue}`),
    ...(coverLetter.qualityIssues || []).map((issue: string) => `Cover letter: ${issue}`),
  ]
  const errorGuidance = Object.entries(APPLICATION_ERROR_GUIDANCE)
    .find(([errorCode]) => (app.error || '').includes(errorCode))?.[1]
  const needsJobSite = app.status === 'failed' || /(captcha|bot-challenge|consent|required|no-application-fields|submit)/i.test(app.error || '')
  const sources = answers.reduce((acc, a) => {
    acc[a.source] = (acc[a.source] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate(-1)}
          className="p-2 rounded-lg hover:bg-secondary transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <CompanyLogo name={app.company} domain={app.companyDomain} logoUrl={app.logoUrl} className="h-12 w-12" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold">{app.company || 'Unknown Company'}</h1>
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border ${STATUS_BADGE[app.status]}`}>
              {app.status}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-primary/10 text-primary border border-primary/20">
              {app.ats || 'unknown'}
            </span>
          </div>
          <a href={app.url} target="_blank" rel="noopener noreferrer" className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 mt-1">
            {app.url} <ExternalLink className="w-3 h-3" />
          </a>
        </div>
        <div className="flex items-center gap-2">
          {!app.archived && !application.manualTrackerEntry && (app.status === 'queued' || app.status === 'paused' || app.status === 'failed') && (
            <button
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
            >
              <Play className="w-4 h-4" /> {app.status === 'failed' ? 'Retry & regenerate' : app.status === 'paused' ? 'Regenerate & run' : 'Run'}
            </button>
          )}
          {!app.archived && app.status === 'review' && (
            <>
              <button onClick={() => regenerateMutation.mutate()} disabled={regenerateMutation.isPending || approveMutation.isPending} className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-40">{regenerateMutation.isPending ? 'Regenerating…' : 'Regenerate draft'}</button>
              <button
                onClick={() => setConfirmOpen(true)}
                disabled={approveMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-applied text-white text-sm font-medium hover:bg-applied/90"
              >
                <CheckCircle2 className="w-4 h-4" /> Review & submit
              </button>
              <button
                onClick={() => rejectMutation.mutate()}
                disabled={rejectMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-failed text-white text-sm font-medium hover:bg-failed/90"
              >
                <XCircle className="w-4 h-4" /> Skip
              </button>
            </>
          )}
          {!app.archived && !application.manualTrackerEntry && ['review', 'failed', 'paused'].includes(app.status) && (
            <button
              onClick={() => {
                if (window.confirm('Confirm only if you completed this application on the employer’s job site. Nori will record it as manually applied, not as an automated submission.')) manualResolutionMutation.mutate('applied')
              }}
              disabled={manualResolutionMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-40"
            >
              <CheckCircle2 className="h-4 w-4" /> I applied manually
            </button>
          )}
          {!app.archived && app.status === 'failed' && (
            <button
              onClick={() => manualResolutionMutation.mutate('skipped')}
              disabled={manualResolutionMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-40"
            >
              <XCircle className="h-4 w-4" /> Skip
            </button>
          )}
          <button
            onClick={() => archiveMutation.mutate()}
            disabled={archiveMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium disabled:opacity-40"
          >
            {app.archived ? <RotateCw className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
            {app.archived ? 'Restore' : 'Archive'}
          </button>
        </div>
      </div>

      <div className="flex gap-1 overflow-x-auto rounded-xl border border-border bg-card p-1">{[
        ['overview','Overview'],['answers',`Form answers (${answers.length})`],['documents','Documents'],['receipt','Execution receipt'],
      ].map(([key,label]) => <button key={key} onClick={() => setTab(key as typeof tab)} className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-medium ${tab === key ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{label}</button>)}</div>

      {reviewIssues.length > 0 && <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm"><p className="font-semibold">Needs attention before automatic submission</p><ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">{reviewIssues.map((issue, index) => <li key={index}>{issue}</li>)}</ul></div>}
      {tab === 'overview' && application.answersSummary?.transport === 'bullhorn-public-rest' && (
        <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-4 text-sm">
          <p className="font-semibold text-blue-500">Bullhorn API review draft</p>
          <p className="mt-1 text-xs text-muted-foreground">Nori verified the exact published job through Bullhorn’s read-only API. The résumé and answers are prepared locally; nothing is sent to Bullhorn until you review every answer and explicitly authorize one submission.</p>
        </div>
      )}
      {tab === 'overview' && app.error && (
        <div className="rounded-xl border border-failed/30 bg-failed/5 p-4">
          <div className="flex items-center gap-2 text-failed text-sm font-medium">
            <AlertCircle className="w-4 h-4" /> {errorGuidance?.title || (needsJobSite ? 'Needs you on the job site' : 'Needs attention')}
          </div>
          <p className="text-sm text-muted-foreground mt-1">{app.error}</p>
          {errorGuidance ? <p className="mt-2 text-xs text-muted-foreground">{errorGuidance.detail}</p> : needsJobSite && <p className="mt-2 text-xs text-muted-foreground">Open the original posting above to finish or verify the application. Do not start a duplicate until you know whether the employer received it, then use “I applied manually” or “Skip.”</p>}
        </div>
      )}

      {/* Answer sources summary */}
      {tab === 'overview' && answers.length > 0 && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {['profile-direct', 'llm', 'user-override', 'skip', 'fallback'].map(src => {
            const Icon = SOURCE_ICONS[src] || FileText
            return (
              <div key={src} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center gap-2">
                  <Icon className={`w-4 h-4 ${SOURCE_COLORS[src]}`} />
                  <span className="text-xs text-muted-foreground uppercase">{src}</span>
                </div>
                <div className="text-2xl font-bold mt-1">{sources[src] || 0}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* Answers */}
      {tab === 'answers' && answers.length > 0 && (
        <div>
          <div className="mb-3 flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="text-lg font-semibold">Form answers</h2><p className="mt-1 text-xs text-muted-foreground">Change anything Nori collected. Saved values take priority when you approve the final run.</p></div>{app.status === 'review' && <button onClick={() => saveAnswersMutation.mutate()} disabled={!answersDirty || saveAnswersMutation.isPending} className="inline-flex items-center justify-center gap-2 rounded-xl border-2 border-border bg-primary px-4 py-2 text-xs font-bold text-white shadow-sm disabled:opacity-35"><Save className="h-3.5 w-3.5" />{saveAnswersMutation.isPending ? 'Saving…' : 'Save answer changes'}</button>}</div>
          <div className="space-y-2">
            {answers.map((answer: Answer, i: number) => {
              const Icon = SOURCE_ICONS[answer.source] || FileText
              const isOpen = expanded[answer.fieldId] ?? false
              return (
                <div
                  key={answer.fieldId || i}
                  className="rounded-xl border border-border bg-card overflow-hidden"
                >
                  <button
                    onClick={() => setExpanded(p => ({ ...p, [answer.fieldId]: !isOpen }))}
                    className="w-full flex items-center gap-3 p-4 text-left hover:bg-secondary/50 transition-colors"
                  >
                    <Icon className={`w-4 h-4 shrink-0 ${SOURCE_COLORS[answer.source] || 'text-muted-foreground'}`} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">
                        {answer.label || answer.fieldId || `Field ${i + 1}`}
                      </div>
                      <div className="text-xs text-muted-foreground truncate mt-0.5">
                        {answer.value === '' || answer.value == null ? '(empty)' : String(answer.value)}
                      </div>
                    </div>
                    <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-4 space-y-2 text-xs text-muted-foreground border-t border-border pt-3">
                      <div className="flex gap-4">
                        <span>Kind: <span className="text-foreground">{answer.kind}</span></span>
                        <span>Source: <span className="text-foreground">{answer.source}</span></span>
                        <span>Required: <span className="text-foreground">{answer.required ? 'Yes' : 'No'}</span></span>
                      </div>
                      {app.status === 'review' && <div className="rounded-xl border-2 border-border bg-background p-3"><label className="block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Reviewed value</label>{answer.options && answer.options.length > 0 ? <select value={String(answerDraft[answer.fieldId] ?? '')} onChange={event => { setAnswerDraft(current => ({ ...current, [answer.fieldId]: event.target.value })); setAnswersDirty(true) }} className="field mt-2 w-full text-sm text-foreground outline-none"><option value="">Choose an answer</option>{answer.options.map((option, optionIndex) => <option key={optionIndex} value={String(option.value)}>{option.label}</option>)}</select> : answer.kind === 'checkbox' ? <select value={String(Boolean(answerDraft[answer.fieldId]))} onChange={event => { setAnswerDraft(current => ({ ...current, [answer.fieldId]: event.target.value === 'true' })); setAnswersDirty(true) }} className="field mt-2 w-full text-sm text-foreground outline-none"><option value="true">Yes</option><option value="false">No</option></select> : answer.kind === 'textarea' ? <textarea value={String(answerDraft[answer.fieldId] ?? '')} onChange={event => { setAnswerDraft(current => ({ ...current, [answer.fieldId]: event.target.value })); setAnswersDirty(true) }} rows={5} className="field mt-2 w-full py-2 text-sm text-foreground outline-none" /> : <input value={String(answerDraft[answer.fieldId] ?? '')} onChange={event => { setAnswerDraft(current => ({ ...current, [answer.fieldId]: event.target.value })); setAnswersDirty(true) }} className="field mt-2 w-full text-sm text-foreground outline-none" />}</div>}
                      {answer.options && answer.options.length > 0 && (
                        <div>
                          <span className="block mb-1">Options:</span>
                          <div className="flex flex-wrap gap-1">
                            {answer.options.map((o, j) => (
                              <span key={j} className="px-2 py-0.5 rounded bg-secondary text-foreground">
                                {o.label}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {answer.display && (
                        <div>
                          <span className="block mb-1">Display:</span>
                          <span className="text-foreground">{answer.display}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {tab === 'answers' && answers.length === 0 && <div className="rounded-2xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">No form answers have been collected yet.</div>}

      {tab === 'documents' && (
        <div className="grid gap-4 md:grid-cols-2">
          <section className="rounded-2xl border border-border bg-card p-5">
            <FileText className="h-5 w-5 text-primary" />
            <h2 className="mt-4 font-semibold">Tailored resume</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {resume.pdfGenerated ? 'Application-specific PDF generated' : resume.useOptimizedResume ? 'PDF generation failed' : 'Original resume configured'}
            </p>
            <div className="mt-4 space-y-2 rounded-xl bg-secondary p-3 text-xs text-muted-foreground">
              <p><CheckCircle2 className={`mr-2 inline h-3.5 w-3.5 ${resume.pdfGenerated ? 'text-emerald-500' : 'text-amber-500'}`} />PDF artifact: {resume.pdfGenerated ? `${resume.fileName} · ${Math.ceil((resume.byteSize || 0) / 1024)} KB` : 'not generated'}</p>
              <p><Paperclip className={`mr-2 inline h-3.5 w-3.5 ${resumeUpload?.verified || resumePrepared?.verified ? 'text-emerald-500' : 'text-amber-500'}`} />Dry-run attachment: {resumeUpload?.verified ? `verified in ${resumeUpload.fieldId}` : resumePrepared?.verified ? `${resumePrepared.fileName} prepared locally for the Bullhorn API` : 'not verified'}</p>
              <p>Optimization: {resume.useOptimizedResume ? `${resume.optimizationMode || 'honest'} tailoring` : 'original document'}</p>
              {resume.resumeMetadata?.matchPercentage != null && <p>Keyword match: {resume.resumeMetadata.matchPercentage}%</p>}
              {resume.artifactError && <p className="text-failed">{resume.artifactError}</p>}
            </div>
            {resume.pdfGenerated && <a href={`/api/applications/${id}/documents/resume`} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white"><Download className="h-3.5 w-3.5" />Download tailored PDF</a>}
            <div className="mt-4 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl border border-border p-3 text-[10px] leading-4 text-muted-foreground">{resume.resumeText || 'No generated resume preview available.'}</div>
          </section>

          <section className="rounded-2xl border border-border bg-card p-5">
            <Bot className="h-5 w-5 text-primary" />
            <h2 className="mt-4 font-semibold">Cover letter</h2>
            <p className="mt-2 text-sm text-muted-foreground">{coverLetter.pdfGenerated ? 'Application-specific PDF generated' : coverLetter.useCoverLetter ? 'PDF generation failed' : 'No cover letter configured'}</p>
            <div className="mt-4 space-y-2 rounded-xl bg-secondary p-3 text-xs text-muted-foreground">
              <p><CheckCircle2 className={`mr-2 inline h-3.5 w-3.5 ${coverLetter.pdfGenerated ? 'text-emerald-500' : 'text-amber-500'}`} />PDF artifact: {coverLetter.pdfGenerated ? `${coverLetter.fileName} · ${Math.ceil((coverLetter.byteSize || 0) / 1024)} KB` : 'not generated'}</p>
              <p><Paperclip className={`mr-2 inline h-3.5 w-3.5 ${coverUpload?.verified ? 'text-emerald-500' : 'text-muted-foreground'}`} />Dry-run attachment: {coverUpload?.verified ? `verified in ${coverUpload.fieldId}` : 'not attached'}</p>
            </div>
            {coverLetter.pdfGenerated && <a href={`/api/applications/${id}/documents/cover-letter`} target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-semibold"><Download className="h-3.5 w-3.5" />Download cover-letter PDF</a>}
            <div className="mt-4 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-secondary p-3 text-xs leading-5 text-muted-foreground">{coverLetter.coverLetterText || 'No cover letter preview available.'}</div>
          </section>
        </div>
      )}

      {/* Timeline */}
      {tab === 'receipt' && app.submissionEvidence && (
        <section className={`mb-4 rounded-2xl border p-5 ${app.submissionEvidence.kind === 'ats-confirmed' ? 'border-emerald-500/30 bg-emerald-500/5' : app.submissionEvidence.kind === 'legacy-unverified' ? 'border-amber-500/30 bg-amber-500/5' : 'border-border bg-card'}`}>
          <div className="flex items-start gap-3">{app.submissionEvidence.confirmed ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-500" /> : <AlertCircle className="mt-0.5 h-5 w-5 text-amber-500" />}<div><h2 className="font-semibold">{app.submissionEvidence.label}</h2><p className="mt-1 text-sm text-muted-foreground">{app.submissionEvidence.detail}</p><p className="mt-2 text-xs text-muted-foreground">{app.submissionReceipt?.ats || app.ats || 'unknown ATS'} · {app.submissionReceipt?.capturedAt ? new Date(app.submissionReceipt.capturedAt).toLocaleString() : 'No ATS receipt capture time'}</p></div></div>
          {app.submissionReceipt?.confirmationId && <p className="mt-4 font-mono text-xs">Confirmation ID: {app.submissionReceipt.confirmationId}</p>}
          {app.submissionReceipt?.confirmationText && <p className="mt-3 rounded-xl bg-background/70 p-3 text-sm text-muted-foreground">{app.submissionReceipt.confirmationText}</p>}
          <div className="mt-3 space-y-1">{(app.submissionReceipt?.signals || []).map((signal, index) => <p key={index} className="font-mono text-[11px] text-muted-foreground">{signal.kind}: {signal.value}</p>)}</div>
        </section>
      )}
      {tab === 'receipt' && trace?.timeline && trace.timeline.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-3">Timeline</h2>
          <div className="rounded-xl border border-border bg-card">
            <div className="divide-y divide-border">
              {trace.timeline.map((t, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-sm font-mono">{t.phase}</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {new Date(t.at).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {tab === 'receipt' && (!trace?.timeline || trace.timeline.length === 0) && <div className="rounded-2xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">Execution has not started.</div>}

      <Dialog.Root open={confirmOpen} onOpenChange={open => { setConfirmOpen(open); if (!open) setConfirmed(false) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[80] bg-black/65 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-1/2 z-[90] w-[calc(100%-24px)] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-[24px] border border-red-500/20 bg-[#111116] p-6 shadow-2xl"><div className="flex items-start justify-between"><div className="grid h-11 w-11 place-items-center rounded-2xl bg-red-500/10 text-red-400"><ShieldAlert className="h-5 w-5" /></div><Dialog.Close className="rounded-xl p-2 text-muted-foreground hover:bg-secondary"><X className="h-4 w-4" /></Dialog.Close></div><Dialog.Title className="mt-5 text-xl font-bold">Submit this real application?</Dialog.Title><Dialog.Description className="mt-2 text-sm leading-6 text-muted-foreground">{application.answersSummary?.transport === 'bullhorn-public-rest' ? 'This leaves dry-run mode and sends the reviewed identity fields plus résumé once through Bullhorn’s official public application API.' : 'This leaves dry-run mode, reopens the employer form, fills it with the reviewed profile, answer changes, and documents, then clicks the final submit control.'}</Dialog.Description><div className="mt-5 rounded-2xl border border-red-500/20 bg-red-500/[.05] p-4 text-sm"><p className="font-semibold">Before continuing</p><ul className="mt-2 space-y-1.5 text-xs text-muted-foreground"><li>• Verify every answer under Form answers.</li><li>• Unsaved answer changes will be saved before this run.</li><li>• CAPTCHA or account prompts may still require intervention.</li></ul></div><label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-border p-3 text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-red-500" /><span>I reviewed this application and explicitly authorize one real submission attempt.</span></label><div className="mt-5 flex justify-end gap-2"><Dialog.Close className="rounded-xl border border-border px-4 py-2.5 text-sm">Keep reviewing</Dialog.Close><button onClick={() => approveMutation.mutate()} disabled={!confirmed || approveMutation.isPending} className="rounded-xl bg-red-500 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-35">{approveMutation.isPending ? 'Submitting…' : 'Authorize submission'}</button></div></Dialog.Content></Dialog.Portal></Dialog.Root>
    </div>
  )
}
