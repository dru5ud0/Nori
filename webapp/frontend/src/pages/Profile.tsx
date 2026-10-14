import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Save, Upload, Plus, Trash2, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

export function Profile() {
  const { data: profile, isLoading } = useQuery({ queryKey: ['profile'], queryFn: api.getProfile })
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [draft, setDraft] = useState<any>(null)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (profile && !dirty) setDraft(JSON.parse(JSON.stringify(profile)))
  }, [profile, dirty])

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const handleSave = async () => {
    if (!draft) return
    setSaving(true)
    try {
      await api.updateProfile(draft)
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
      queryClient.invalidateQueries({ queryKey: ['automation-readiness'] })
      setDirty(false)
      toast.success('Profile saved')
    } catch (e: any) {
      toast.error(e.message)
    }
    setSaving(false)
  }

  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await api.importResume(file)
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['bootstrap'] })
      queryClient.invalidateQueries({ queryKey: ['automation-readiness'] })
      setDirty(false)
      toast.success('Resume imported. Review the extracted fields before saving.')
    } catch (err: any) {
      toast.error(err.message)
    }
    setUploading(false)
  }

  const updateField = (section: string, field: string, value: any) => {
    setDraft((current: any) => ({
      ...current,
      [section]: { ...(current?.[section] || {}), [field]: value },
    }))
    setDirty(true)
  }
  const updateAuthorization = (field: string, value: boolean) => {
    setDraft((current: any) => ({
      ...current,
      workAuthorization: {
        ...(current?.workAuthorization || {}),
        [field]: value,
        reviewedAt: '',
      },
    }))
    setDirty(true)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-6 h-6 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!draft) return null
  const pi = draft.personalInformation ?? {}
  const wa = draft.workAuthorization ?? {}
  const we = draft.workExperience ?? []
  const edu = draft.education ?? []
  const skills = draft.skillCategories ?? []
  const certifications = draft.certifications ?? []
  const testProfile = String(pi.email || '').endsWith('@example.com') || (pi.firstName === 'Jane' && pi.lastName === 'Doe')
  const required = ['firstName','lastName','email','phone','address','city','state','zipCode','country']
  const contactReady = required.every(key => Boolean(pi[key]))
  const authorizationAnswered = typeof wa.isAuthorizedToWork === 'boolean' && typeof wa.needsSponsorship === 'boolean'
  const authorizationReady = authorizationAnswered && Boolean(wa.reviewedAt)
  const resumeReady = Boolean(draft.resumeFormat && draft.resumePath)
  const completed = required.filter(key => Boolean(pi[key])).length + (typeof wa.isAuthorizedToWork === 'boolean' ? 1 : 0) + (typeof wa.needsSponsorship === 'boolean' ? 1 : 0) + (authorizationReady ? 1 : 0) + (resumeReady ? 1 : 0)
  const readiness = Math.round((completed / 13) * 100)
  const setList = (key: string, value: any[]) => { setDraft((current: any) => ({...current, [key]: value})); setDirty(true) }
  const updateListItem = (key: string, index: number, updates: Record<string, unknown>) => {
    const rows = [...(draft[key] || [])]
    rows[index] = { ...rows[index], ...updates }
    setList(key, rows)
  }
  const splitComma = (value: string) => value.split(',').map(item => item.trim()).filter(Boolean)
  const splitLines = (value: string) => value.split('\n').map(item => item.trim()).filter(Boolean)

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Profile</h1>
          <p className="text-sm text-muted-foreground mt-1">Candidate profile used for form filling</p>
        </div>
        <div className="flex items-center gap-2">
          <label className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm font-medium hover:bg-secondary cursor-pointer transition-colors ${uploading ? 'opacity-50' : ''}`}>
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            Import Resume
            <input type="file" accept=".pdf" onChange={handleResumeUpload} className="hidden" />
          </label>
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save
          </button>
        </div>
      </div>

      {testProfile && <section className="flex flex-col justify-between gap-4 rounded-2xl border border-amber-500/25 bg-amber-500/[.06] p-5 sm:flex-row sm:items-center"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 text-amber-400" /><div><h2 className="text-sm font-semibold text-amber-400">Demo profile active</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">Import your real PDF resume. New applications are blocked until the demo identity is replaced and reviewed.</p></div></div><label className="cursor-pointer rounded-xl bg-amber-400 px-4 py-2.5 text-center text-xs font-bold text-black">Choose my resume<input type="file" accept=".pdf" onChange={handleResumeUpload} className="hidden" /></label></section>}

      <section className="rounded-2xl border-2 border-border bg-card p-5 shadow-md">
        <div className="flex items-center justify-between"><div><p className="font-mono text-xs font-semibold uppercase tracking-wider text-muted-foreground">Application readiness</p><p className="mt-2 text-sm font-medium">{readiness === 100 && !testProfile ? 'Ready to prepare applications' : 'Review required before applying'}</p></div><span className={`text-2xl font-black ${readiness === 100 && !testProfile ? 'text-emerald-700' : 'text-primary'}`}>{readiness}%</span></div>
        <div className="mt-4 h-3 overflow-hidden border-2 border-black bg-secondary"><div className="h-full bg-primary transition-all" style={{width:`${readiness}%`}} /></div>
        <div className="mt-4 flex flex-wrap gap-2 font-mono text-[10px] uppercase text-muted-foreground">
          <span className="border-2 border-border bg-card px-2 py-1">{contactReady ? <CheckCircle2 className="mr-1 inline h-3 w-3 text-emerald-700" /> : <AlertTriangle className="mr-1 inline h-3 w-3 text-amber-600" />}Contact details</span>
          <span className="border-2 border-border bg-card px-2 py-1">{authorizationReady ? <CheckCircle2 className="mr-1 inline h-3 w-3 text-emerald-700" /> : <AlertTriangle className="mr-1 inline h-3 w-3 text-amber-600" />}Work eligibility</span>
          <span className="border-2 border-border bg-card px-2 py-1">{resumeReady ? <CheckCircle2 className="mr-1 inline h-3 w-3 text-emerald-700" /> : <AlertTriangle className="mr-1 inline h-3 w-3 text-amber-600" />}Resume PDF</span>
        </div>
      </section>

      {/* Personal Info */}
      <section className="rounded-xl border border-border bg-card p-5">
        <h2 className="text-sm font-semibold mb-4">Personal Information</h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            ['firstName', 'First Name'],
            ['lastName', 'Last Name'],
            ['title', 'Professional Title'],
            ['email', 'Email'],
            ['phone', 'Phone'],
            ['address', 'Address'],
            ['city', 'City'],
            ['state', 'State'],
            ['zipCode', 'Zip Code'],
            ['country', 'Country'],
            ['linkedinUrl', 'LinkedIn URL'],
            ['githubUrl', 'GitHub URL'],
          ].map(([key, label]) => (
            <div key={key}>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">{label}</label>
              <input
                type="text"
                value={pi[key] || ''}
                onChange={e => updateField('personalInformation', key, e.target.value)}
                className="w-full h-9 px-3 rounded-lg bg-secondary border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          ))}
        </div>
        <label className="mt-3 block text-xs font-medium text-muted-foreground">Professional Summary<textarea value={pi.summary || ''} onChange={e => updateField('personalInformation', 'summary', e.target.value)} rows={5} className="mt-1 w-full rounded-lg border border-border bg-secondary p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" /></label>
      </section>

      <section className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div><h2 className="text-sm font-semibold">Reusable cover-letter template</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">Optional text used for honest cover letters. Use <code className="text-foreground">{'{{company}}'}</code> and <code className="text-foreground">{'{{role}}'}</code> for job-specific placeholders. Nori preserves your wording and never adds invented facts.</p></div>
          <span className="rounded-full bg-primary/10 px-2 py-1 text-[10px] font-semibold uppercase text-primary">Profile asset</span>
        </div>
        <textarea value={draft.coverLetterText || ''} onChange={e => { setDraft((current: any) => ({...current, coverLetterText: e.target.value})); setDirty(true) }} rows={9} placeholder="Dear Hiring Team,\n\nI am excited to apply for {{role}} at {{company}}..." className="mt-4 w-full rounded-xl border border-border bg-secondary p-3 text-sm leading-6 text-foreground outline-none focus:ring-1 focus:ring-primary" />
      </section>

      {/* Work Authorization */}
      <section className="rounded-xl border border-border bg-card p-5">
        <h2 className="text-sm font-semibold mb-4">Work Authorization</h2>
        <div className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground">Are you currently authorized to work in the US?<select value={typeof wa.isAuthorizedToWork === 'boolean' ? String(wa.isAuthorizedToWork) : ''} onChange={e => updateAuthorization('isAuthorizedToWork', e.target.value === 'true')} className="field mt-1 w-full text-sm text-foreground"><option value="" disabled>Choose an answer</option><option value="true">Yes</option><option value="false">No</option></select></label>
          <label className="block text-xs font-medium text-muted-foreground">Will you now or in the future require visa sponsorship?<select value={typeof wa.needsSponsorship === 'boolean' ? String(wa.needsSponsorship) : ''} onChange={e => updateAuthorization('needsSponsorship', e.target.value === 'true')} className="field mt-1 w-full text-sm text-foreground"><option value="" disabled>Choose an answer</option><option value="true">Yes</option><option value="false">No</option></select></label>
          <label className="flex items-start gap-3 rounded-lg border border-border bg-secondary/40 p-3">
            <input
              type="checkbox"
              checked={Boolean(wa.reviewedAt)}
              disabled={!authorizationAnswered}
              onChange={e => updateField('workAuthorization', 'reviewedAt', e.target.checked ? new Date().toISOString() : '')}
              className="mt-0.5 h-4 w-4 rounded accent-primary"
            />
            <span className="text-sm"><span className="font-medium">I reviewed both answers and they are currently accurate.</span><span className="mt-1 block text-xs text-muted-foreground">Changing either answer clears this confirmation. Required before Nori prepares scheduled applications.</span></span>
          </label>
        </div>
      </section>

      {/* Work Experience */}
      <section className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold">Work Experience</h2>
          <button onClick={() => setList('workExperience', [...we, {role:'', company:'', location:'', startDate:'', endDate:'', isCurrentRole:false, responsibilities:[], technologies:[]}])} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
        {we.length === 0 ? (
          <p className="text-sm text-muted-foreground">No work experience added</p>
        ) : (
          <div className="space-y-4">
            {we.map((exp: any, i: number) => (
              <div key={exp.id || i} className="rounded-xl border border-border bg-secondary p-4">
                <div className="mb-3 flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Experience {i + 1}</p><button onClick={() => setList('workExperience', we.filter((_: any, index: number) => index !== i))} className="p-1 text-muted-foreground hover:text-failed" aria-label={`Remove ${exp.role || exp.title || 'experience'}`}><Trash2 className="w-4 h-4" /></button></div>
                <div className="grid gap-3 sm:grid-cols-2">{[['role','Role'],['company','Company'],['location','Location'],['startDate','Start date'],['endDate','End date']].map(([key,label]) => <label key={key} className="text-xs text-muted-foreground">{label}<input value={exp[key] || (key === 'role' ? exp.title : '') || ''} disabled={key === 'endDate' && Boolean(exp.isCurrentRole || exp.current)} onChange={e => updateListItem('workExperience', i, {[key]: e.target.value})} className="field mt-1 w-full text-sm text-foreground outline-none disabled:opacity-40" /></label>)}</div>
                <label className="mt-3 flex items-center gap-2 text-xs"><input type="checkbox" checked={Boolean(exp.isCurrentRole || exp.current)} onChange={e => updateListItem('workExperience', i, {isCurrentRole:e.target.checked, endDate:e.target.checked ? '' : exp.endDate})} />Current role</label>
                <label className="mt-3 block text-xs text-muted-foreground">Technologies (comma separated)<input value={(exp.technologies || []).join(', ')} onChange={e => updateListItem('workExperience', i, {technologies:splitComma(e.target.value)})} className="field mt-1 w-full text-sm text-foreground outline-none" /></label>
                <label className="mt-3 block text-xs text-muted-foreground">Responsibilities (one per line)<textarea value={(exp.responsibilities || []).join('\n')} onChange={e => updateListItem('workExperience', i, {responsibilities:splitLines(e.target.value)})} rows={6} className="mt-1 w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" /></label>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Education */}
      <section className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold">Education</h2>
          <button onClick={() => setList('education', [...edu, {university:'', degree:'', major:'', minor:'', startDate:'', endDate:''}])} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
        {edu.length === 0 ? (
          <p className="text-sm text-muted-foreground">No education added</p>
        ) : (
          <div className="space-y-4">
            {edu.map((entry: any, i: number) => (
              <div key={entry.id || i} className="rounded-xl border border-border bg-secondary p-4"><div className="mb-3 flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Education {i + 1}</p><button onClick={() => setList('education', edu.filter((_: any, index: number) => index !== i))} aria-label="Remove education" className="p-1 text-muted-foreground hover:text-failed"><Trash2 className="h-4 w-4" /></button></div><div className="grid gap-3 sm:grid-cols-2">{[['university','School'],['degree','Degree'],['major','Major'],['minor','Minor'],['location','Location'],['startDate','Start date'],['endDate','End date'],['gpa','GPA']].map(([key,label]) => <label key={key} className="text-xs text-muted-foreground">{label}<input value={entry[key] || (key === 'university' ? entry.school || entry.institution : key === 'major' ? entry.field : '') || ''} onChange={e => updateListItem('education', i, {[key]:e.target.value})} className="field mt-1 w-full text-sm text-foreground outline-none" /></label>)}</div></div>
            ))}
          </div>
        )}
      </section>

      {/* Skills */}
      <section className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold">Skills</h2>
          <button onClick={() => setList('skillCategories', [...skills, {name:'New category', skills:[]}])} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
        {skills.length === 0 ? (
          <p className="text-sm text-muted-foreground">No skills added</p>
        ) : (
          <div className="space-y-3">
            {skills.map((cat: any, i: number) => (
              <div key={cat.id || i} className="rounded-xl border border-border bg-secondary p-3"><div className="flex gap-2"><label className="flex-1 text-xs text-muted-foreground">Category<input value={cat.name || ''} onChange={e => updateListItem('skillCategories', i, {name:e.target.value})} className="field mt-1 w-full text-sm text-foreground outline-none" /></label><button onClick={() => setList('skillCategories', skills.filter((_: any, index: number) => index !== i))} aria-label={`Remove ${cat.name || 'skill category'}`} className="mt-5 p-2 text-muted-foreground hover:text-failed"><Trash2 className="h-4 w-4" /></button></div><label className="mt-3 block text-xs text-muted-foreground">Skills (comma separated)<textarea value={(cat.skills || []).join(', ')} onChange={e => updateListItem('skillCategories', i, {skills:splitComma(e.target.value)})} rows={2} className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" /></label></div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl border-2 border-border bg-card p-5 shadow-md">
        <div className="mb-4 flex items-center justify-between"><h2 className="text-sm font-semibold">Certifications</h2><button onClick={() => setList('certifications', [...certifications, {name:'', issuingOrganization:'', credentialId:'', credentialUrl:''}])} className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><Plus className="h-3 w-3" />Add</button></div>
        <div className="space-y-3">{certifications.map((cert: any, index: number) => <div key={cert.id || index} className="rounded-xl border border-border bg-secondary p-3"><div className="mb-2 flex justify-end"><button onClick={() => setList('certifications', certifications.filter((_: any, i: number) => i !== index))} aria-label={`Remove ${cert.name || 'certification'}`} className="p-1 text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button></div><div className="grid gap-3 sm:grid-cols-2">{[['name','Certification'],['issuingOrganization','Issuer'],['credentialId','Credential ID'],['credentialUrl','Credential URL']].map(([key,label]) => <label key={key} className="text-xs text-muted-foreground">{label}<input value={cert[key] || ''} onChange={e => updateListItem('certifications', index, {[key]:e.target.value})} className="field mt-1 w-full text-sm text-foreground outline-none" /></label>)}</div></div>)}</div>
      </section>
    </div>
  )
}
