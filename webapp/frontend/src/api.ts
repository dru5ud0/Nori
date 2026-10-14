const BASE = '/api'

function errorText(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(errorText).filter(Boolean).join('; ')
  if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>
    const message = item.msg || item.message || item.detail || item.error
    const location = Array.isArray(item.loc) ? item.loc.join('.') : ''
    return message ? `${location ? location + ': ' : ''}${errorText(message)}` : JSON.stringify(item)
  }
  return String(value || 'Request failed')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const message = errorText(err.detail || err.error || `HTTP ${res.status}`)
    throw new Error(message.includes('body.source') ? 'An older Nori server is running. Restart Nori AI to load the HiringCafe search upgrade.' : message)
  }
  return res.json()
}

export interface BootstrapData {
  profile: { firstName: string; lastName: string; email: string; hasResume: boolean; ready: boolean; testProfile: boolean; missingFields: {field: string; label: string; section: string}[] }
  counts: { total: number; queued: number; review: number; running: number; applied: number; failed: number; paused: number }
  recent: Application[]
}

export interface Application {
  id: string
  url: string
  title: string
  company: string
  companyDomain?: string
  logoUrl?: string
  status: string
  ats: string
  submitted: boolean
  archived?: boolean
  archivedAt?: number | null
  manualSubmissionConfirmed?: boolean
  submissionEvidence?: {
    kind: 'ats-confirmed' | 'user-confirmed' | 'legacy-unverified' | 'not-submitted'
    confirmed: boolean
    automated: boolean
    label: string
    detail: string
  }
  createdAt: string
  updatedAt: string
  error?: string
  trace?: TraceData
  submissionReceipt?: {
    confirmed: boolean
    ats: string
    capturedAt: number
    url: string
    signals: { kind: string; value: string }[]
    confirmationText?: string
    confirmationId?: string
  }
  answerOverrides?: Record<string, AnswerValue>
  trackerStage?: 'applied' | 'interviewing' | 'offer' | 'rejected'
  manualTrackerEntry?: boolean
  documents?: {
    resume?: { pdfGenerated?: boolean; fileName?: string }
    coverLetter?: { pdfGenerated?: boolean; fileName?: string; enabled?: boolean }
  }
  answersSummary?: { uploaded_documents?: { kind?: string; fileName?: string }[] }
}

export type AnswerValue = string | boolean | number | string[] | null

export interface TraceData {
  meta: { ats: string; outcome: string; startedAt: number; durationMs: number }
  answers: Answer[]
  timeline: TimelineEntry[]
  derivedMissingFields: string[]
}

export interface Answer {
  fieldId: string
  label: string
  kind: string
  source: string
  value: AnswerValue
  required: boolean
  display?: string
  reason?: string
  options?: { label: string; value: string }[]
}

export interface TimelineEntry {
  phase: string
  at: number
}

export interface JobFeed {
  ok: boolean
  count: number
  jobs: JobFeedItem[]
}

export interface CompanyIdentity {
  companyName?: string
  companyDomain?: string
  logoUrl?: string
  jobTitle?: string
}

export interface JobFeedItem extends CompanyIdentity {
  id: string
  title: string
  url: string
  location?: string
  updated_at?: string
  atsType?: string
  source?: string
  remote?: boolean
  salaryMin?: number
  salaryMax?: number
  currency?: string
  experienceLevel?: string
  skills?: string[]
  description?: string
  matchScore?: number
  matchReasons?: string[]
  matchWarnings?: string[]
  matchQuality?: 'excellent' | 'strong' | 'good' | 'stretch'
}

export interface ApplySettings {
  optimizationMode: 'off' | 'honest' | 'aggressive'
  coverLetterMode: 'off' | 'honest' | 'generated'
  autoApproveResume: boolean
  autoApproveCoverLetter: boolean
  autoSubmitApplication: boolean
  reviewBeforeSubmit: boolean
  [key: string]: unknown
}

export interface MonitorSettings {
  savedSearchUrl: string
  excludedTitles: string
  minimumSalary: number
  strictLocation: boolean
  applicationMode: 'notify' | 'prepare' | 'apply'
  maxApplicationsPerCycle: number
  dailyApplicationCap: number
  dailyApplicationsUsed: number
  dailyApplicationsRemaining: number
  dailyUsageDate: string
  minMatchQuality: 'excellent' | 'strong' | 'good' | 'stretch'
  standingInstructions: string
  lanes: MonitorLane[]
  lastPreparedCount: number
  lastAppliedCount: number
  lastNeedsReviewCount: number
  enabled: boolean
  query: string
  location: string
  remoteOnly: boolean
  intervalMinutes: number
  limit: number
  minScore: number
  telegramBotToken: string
  telegramChatId: string
  telegramConfigured: boolean
  lastRunAt: string
  nextRunAt: string
  lastError: string
  lastFoundCount: number
  lastNewCount: number
  notificationsSent: number
  runHistory: MonitorRun[]
  recentAlerts: MonitorAlert[]
}

export interface MonitorAlert {
  id: string
  url: string
  title: string
  companyName: string
  location: string
  matchScore: number
  matchQuality: string
  foundAt: string
  telegramNotified: boolean
}

export interface MonitorRun {
  runId: string
  startedAt: string
  finishedAt: string
  durationMs: number
  status: 'completed' | 'partial' | 'blocked' | 'failed'
  mode: 'notify' | 'prepare' | 'apply'
  laneCount: number
  found: number
  new: number
  notified: number
  prepared: number
  applied: number
  needsReview: number
  error: string
}

export interface AutomationPreview {
  ok: boolean
  days: number
  activeLanes: number
  minimumScore: number
  currentEligibleCandidates: number
  dailyApplicationCap: number
  maximumPreparations: number
  cyclesPerDay: number
  recentRunsMeasured: number
  averageNewPerRun: number
  projectedNewJobs: number
  projectedPreparations: number
  estimateAvailable: boolean
}

export interface MonitorLane {
  id: string
  name: string
  enabled: boolean
  query: string
  location: string
  remoteOnly: boolean
  minScore: number
  minMatchQuality: 'excellent' | 'strong' | 'good' | 'stretch'
}

export interface AutomationReadiness {
  ok: boolean
  readyToPrepare: boolean
  readyToMonitor: boolean
  readyToSubmitUnattended: boolean
  checks: { id: string; label: string; ok: boolean; required: boolean }[]
  blockers: string[]
  warnings: string[]
  workAuthorization: { isAuthorizedToWork: boolean | null; needsSponsorship: boolean | null; reviewedAt: string }
  certifiedUnattendedAts: string[]
}

export interface PreflightResult {
  ok: boolean
  url: string
  validUrl: boolean
  ats: string
  atsName: string
  confidence: number
  rule: string
  supported: boolean
  capabilityLevel: 'dry-run-verified' | 'experimental' | 'detect-only'
  capabilities: {
    ats: string
    name: string
    level: string
    detect: boolean
    prepare: boolean
    fill: boolean
    reviewMode: 'replay' | 'none'
    manualSubmit: boolean
    unattendedSubmit: boolean
    confirmation: string
    warnings: string[]
  }
  warnings: string[]
  duplicate: boolean
  linkedinOnly: boolean
  profileReady: boolean
  testProfile: boolean
  missingFields: { field: string; label: string; section: string }[]
  settings: ApplySettings
  mode: 'prepare-and-review'
  canQueue: boolean
  blockers: string[]
}

export interface NetworkingEvidence {
  sourceUrl: string
  text: string
  capturedAt: number
  kind: string
}

export interface NetworkingContact {
  id: string
  name: string
  linkedinUrl: string
  headline?: string
  location?: string
  company?: string
  connectionDegree?: string
  email?: string
  about?: string
  notes?: string
  status: string
  score: number
  signals: Record<string, boolean>
  scoreReasons: { signal: string; points: number }[]
  riskFlags: string[]
  tags?: string[]
  evidence?: NetworkingEvidence[]
  outreachDraft?: string
  createdAt: number
  updatedAt: number
}

export interface NetworkingList {
  ok: boolean
  count: number
  contacts: NetworkingContact[]
  summary: Record<string, number>
  relationships: any[]
}

export interface InboxMessage {
  id: string
  threadId: string
  timestamp: number
  subject: string
  sender: string
  date: string
  snippet: string
  category: string
  confidence: string
}

export interface InboxData {
  ok: boolean
  authorized: boolean
  count: number
  messages: InboxMessage[]
  scope?: string
  connectionError?: string
}

export const api = {
  bootstrap: () => request<BootstrapData>('/dashboard/bootstrap'),

  preflight: (url: string) => request<PreflightResult>(`/preflight?url=${encodeURIComponent(url)}`),

  listApplications: (filter = 'all', page = 1, limit = 100, q = '') =>
    request<{ total: number; filtered: number; applications: Application[] }>(
      `/applications?filter=${filter}&page=${page}&limit=${limit}&q=${encodeURIComponent(q)}`
    ),

  trackerExportUrl: `${BASE}/tracker/export`,

  getApplication: (id: string) => request<Application>(`/applications/${id}`),

  getTrace: (id: string) => request<TraceData>(`/applications/${id}/trace`),

  saveAnswers: (id: string, answers: Record<string, AnswerValue>) =>
    request<{ ok: boolean; saved: number }>(`/applications/${id}/answers`, {
      method: 'PUT',
      body: JSON.stringify({ answers }),
    }),

  createApplication: (url: string, identity: CompanyIdentity = {}) =>
    request<{ ok: boolean; applicationId: string; status: string; ats: string }>(
      '/applications',
      {
        method: 'POST',
        body: JSON.stringify({
          url,
          company_name: identity.companyName || '',
          company_domain: identity.companyDomain || '',
          logo_url: identity.logoUrl || '',
          job_title: identity.jobTitle || '',
        }),
      }
    ),

  runApplication: async (id: string, confirmed = false) => {
    const result = await request<{ ok: boolean; status: string; error?: string }>(`/applications/${id}/run`, {
      method: 'POST',
      body: JSON.stringify({ confirmed }),
    })
    if (!result.ok) throw new Error(result.error || 'Application run failed')
    return result
  },

  approveApplication: async (id: string) => {
    const result = await request<{ ok: boolean; submitted: boolean; status: string; error?: string }>(`/applications/${id}/approve`, { method: 'POST' })
    if (!result.ok || !result.submitted) throw new Error(result.error || 'Submission was not confirmed by the ATS')
    return result
  },

  rejectApplication: async (id: string) => {
    const result = await request<{ ok: boolean; error?: string }>(`/applications/${id}/reject`, { method: 'POST' })
    if (!result.ok) throw new Error(result.error || 'Could not pause application')
    return result
  },

  resolveApplication: async (id: string, resolution: 'applied' | 'skipped') => {
    const result = await request<{ ok: boolean; status: string; submitted: boolean; resolution: string; error?: string }>(`/applications/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ resolution }),
    })
    if (!result.ok) throw new Error(result.error || 'Could not update application')
    return result
  },

  setApplicationArchived: async (id: string, archived: boolean) => {
    const result = await request<{ ok: boolean; applicationId: string; archived: boolean; archivedAt?: number | null; error?: string }>(`/applications/${id}/archive`, {
      method: 'PATCH',
      body: JSON.stringify({ archived }),
    })
    if (!result.ok) throw new Error(result.error || 'Could not update application archive')
    return result
  },

  updateTrackerStage: (id: string, stage: string) =>
    request<{ ok: boolean; trackerStage: string }>(`/applications/${id}/tracker`, {
      method: 'PATCH',
      body: JSON.stringify({ stage }),
    }),

  addTrackerEntry: (entry: { companyName?: string; jobTitle?: string; url?: string; stage: string }) =>
    request<{ ok: boolean; applicationId: string; trackerStage: string }>('/tracker', {
      method: 'POST',
      body: JSON.stringify({
        company_name: entry.companyName || '',
        job_title: entry.jobTitle || '',
        url: entry.url || '',
        stage: entry.stage,
      }),
    }),

  getProfile: () => request<any>('/profile'),

  updateProfile: (profile: any) =>
    request<{ ok: boolean }>('/profile', {
      method: 'PUT',
      body: JSON.stringify({ profile }),
    }),

  getSettings: () => request<ApplySettings>('/settings'),
  aiProvider: () => request<{baseUrl: string; model: string; transport: string; configured: boolean; lastError: string; login?: {signedIn: boolean; error: string}}>('/ai/provider'),
  saveAIProvider: (settings: {baseUrl: string; model: string; apiKey: string; transport: string}) => request('/ai/provider', {method: 'PUT', body: JSON.stringify(settings)}),
  testAIProvider: () => request<{ok: boolean; lastError: string}>('/ai/test', {method: 'POST'}),

  updateSettings: (settings: ApplySettings) =>
    request<{ ok: boolean; settings: ApplySettings }>('/settings', {
      method: 'PUT',
      body: JSON.stringify({ settings }),
    }),

  importResume: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/resume/import`, { method: 'POST', body: form })
    if (!res.ok) throw new Error('Import failed')
    return res.json()
  },

  fetchFeed: (source: string, limit = 100) =>
    request<JobFeed>('/feed', {
      method: 'POST',
      body: JSON.stringify({ source, limit }),
    }),

  saveFeed: (source: string, limit = 100) =>
    request<{ ok: boolean }>('/feed/save', {
      method: 'POST',
      body: JSON.stringify({ source, limit }),
    }),

  searchJobs: (query: string, location = '', remoteOnly = false, limit = 50) =>
    request<JobFeed>('/feed/save', {
      method: 'POST',
      body: JSON.stringify({ query, location, remote_only: remoteOnly, limit }),
    }),

  loadFeed: () => request<{ ok: boolean; count: number; jobs: any[] }>('/feed/load'),

  topMatches: (limit = 6) => request<{ ok: boolean; count: number; jobs: JobFeedItem[]; minimumScore: number }>(`/feed/top?limit=${limit}`),

  sourceResumeUrl: `${BASE}/resume`,

  getMonitor: () => request<MonitorSettings>('/monitor'),

  monitorPreview: (days = 7) => request<AutomationPreview>(`/monitor/preview?days=${days}`),

  automationReadiness: () => request<AutomationReadiness>('/automation/readiness'),

  updateMonitor: (settings: Partial<MonitorSettings>) =>
    request<{ ok: boolean; settings: MonitorSettings }>('/monitor', {
      method: 'PUT',
      body: JSON.stringify({ settings }),
    }),

  runMonitor: () => request<{ ok: boolean; count: number; newCount: number; notified: number; prepared: number; applied: number; needsReview: number }>('/monitor/run', { method: 'POST' }),

  testMonitor: () => request<{ ok: boolean; sent: number }>('/monitor/test', { method: 'POST' }),

  inbox: () => request<InboxData>('/inbox'),

  gmailConnect: (clientId: string, redirectUri: string) =>
    request<{ ok: boolean; authorizationUrl: string }>('/inbox/gmail/connect', {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId, redirect_uri: redirectUri }),
    }),

  gmailSync: (maxMessages = 50) =>
    request<{ ok: boolean; count: number; messages: InboxMessage[] }>('/inbox/gmail/sync', {
      method: 'POST',
      body: JSON.stringify({ max_messages: maxMessages }),
    }),

  gmailDisconnect: () => request<{ ok: boolean; authorized: boolean }>('/inbox/gmail', { method: 'DELETE' }),

  atses: () => request<{ id: string; name: string }[]>('/atses'),

  linkedinSearch: (keywords: string, location = '', pages = 1, detail = 0) => {
    const form = new FormData()
    form.append('keywords', keywords)
    form.append('location', location)
    form.append('pages', String(pages))
    form.append('detail', String(detail))
    return fetch(`${BASE}/linkedin/search`, { method: 'POST', body: form }).then(r => r.json())
  },

  linkedinHarvest: (entries: { jobId: string; title: string; url: string }[]) =>
    request<{ ok: boolean; created: number; skipped: number }>('/linkedin/harvest', {
      method: 'POST',
      body: JSON.stringify({ entries }),
    }),

  networkingContacts: (query = '', status = '', chicagoOnly = true) =>
    request<NetworkingList>(`/networking/contacts?query=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}&chicago_only=${chicagoOnly}`),

  networkingUpsert: (contact: Partial<NetworkingContact> & { name?: string; linkedinUrl?: string }) =>
    request<{ ok: boolean; created: boolean; contact: NetworkingContact }>('/networking/contacts', {
      method: 'POST',
      body: JSON.stringify({ contact }),
    }),

  networkingUpdate: (id: string, updates: Partial<NetworkingContact>) =>
    request<{ ok: boolean; contact: NetworkingContact }>(`/networking/contacts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ updates }),
    }),

  networkingDelete: (id: string) =>
    request<{ ok: boolean; deleted: string }>(`/networking/contacts/${id}`, {
      method: 'DELETE',
    }),

  networkingDraft: (id: string) =>
    request<{ ok: boolean; draft: string; contact: NetworkingContact }>(`/networking/contacts/${id}/draft`, {
      method: 'POST',
    }),
}
