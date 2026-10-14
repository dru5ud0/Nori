import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Building2, CheckCircle2, Clipboard, ExternalLink,
  FileSignature, Loader2, MapPin, MessageSquareText, Search, ShieldCheck,
  Trash2, Users, Plus,
} from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api, type NetworkingContact } from '../api'

const STATUSES = ['discovered', 'vetted', 'contacted', 'replied', 'rtr', 'submitted', 'interview', 'closed', 'archived']

const SIGNAL_LABELS: Record<string, string> = {
  chicagoRelevant: 'Chicago area',
  directClient: 'Direct client',
  w2: 'W2',
  c2c: 'C2C',
  rtr: 'RTR',
  optEad: 'OPT EAD',
  stemOpt: 'STEM OPT',
  eVerify: 'E-Verify',
  i983: 'I-983',
  h1b: 'H-1B',
  unitedAirlines: 'United / UAL',
}

function scoreStyle(score: number) {
  if (score >= 75) return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
  if (score >= 45) return 'border-amber-500/30 bg-amber-500/10 text-amber-300'
  return 'border-zinc-600 bg-zinc-800/70 text-zinc-300'
}

export function Networking() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [chicagoOnly, setChicagoOnly] = useState(true)
  const [busy, setBusy] = useState('')
  const [draft, setDraft] = useState<{ name: string; text: string } | null>(null)
  const [adding, setAdding] = useState(false)
  const [savingContact, setSavingContact] = useState(false)
  const [newContact, setNewContact] = useState({ name: '', company: '', location: '', linkedinUrl: '', email: '', notes: '' })

  const { data, isLoading } = useQuery({
    queryKey: ['networking', query, status, chicagoOnly],
    queryFn: () => api.networkingContacts(query, status, chicagoOnly),
  })
  const contacts = data?.contacts || []

  const update = async (contact: NetworkingContact, updates: Partial<NetworkingContact>) => {
    setBusy(contact.id)
    try {
      await api.networkingUpdate(contact.id, updates)
      await queryClient.invalidateQueries({ queryKey: ['networking'] })
      toast.success('Contact updated')
    } catch (error: any) {
      toast.error(error.message)
    } finally {
      setBusy('')
    }
  }

  const createDraft = async (contact: NetworkingContact) => {
    setBusy(contact.id)
    try {
      const result = await api.networkingDraft(contact.id)
      setDraft({ name: contact.name, text: result.draft })
      await queryClient.invalidateQueries({ queryKey: ['networking'] })
    } catch (error: any) {
      toast.error(error.message)
    } finally {
      setBusy('')
    }
  }

  const remove = async (contact: NetworkingContact) => {
    if (!window.confirm(`Delete ${contact.name || 'this contact'} from the local CRM?`)) return
    setBusy(contact.id)
    try {
      await api.networkingDelete(contact.id)
      await queryClient.invalidateQueries({ queryKey: ['networking'] })
      toast.success('Contact deleted')
    } catch (error: any) {
      toast.error(error.message)
    } finally {
      setBusy('')
    }
  }

  const addContact = async () => {
    if (!newContact.name.trim() && !newContact.linkedinUrl.trim() && !newContact.email.trim()) return
    setSavingContact(true)
    try {
      await api.networkingUpsert(newContact)
      setNewContact({ name: '', company: '', location: '', linkedinUrl: '', email: '', notes: '' })
      setAdding(false)
      await queryClient.invalidateQueries({ queryKey: ['networking'] })
      toast.success('Contact added locally')
    } catch (error: any) { toast.error(error.message) }
    finally { setSavingContact(false) }
  }

  const summary = data?.summary || {}
  const cards = [
    ['Visible', contacts.length, Users],
    ['Vetted', summary.vetted || 0, ShieldCheck],
    ['RTR / submitted', (summary.rtr || 0) + (summary.submitted || 0), FileSignature],
    ['Interviews', summary.interview || 0, CheckCircle2],
  ] as const

  return <div className="max-w-6xl space-y-6">
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex items-start gap-4">
        <div className="grid h-11 w-11 place-items-center rounded-2xl border border-primary/20 bg-primary/10 text-primary"><Users className="h-5 w-5" /></div>
        <div><h1 className="text-2xl font-bold tracking-tight">Chicago Recruiter & Vendor CRM</h1><p className="mt-1 max-w-2xl text-sm text-muted-foreground">Capture LinkedIn recruiter evidence, qualify STEM-OPT/W2 relationships, map RTR progress, and draft outreach. Nothing is sent automatically.</p></div>
      </div>
      <div className="flex flex-wrap gap-2"><button onClick={() => setAdding(true)} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white"><Plus className="h-4 w-4" />Add contact</button><div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs text-muted-foreground"><ShieldCheck className="mr-2 inline h-4 w-4 text-emerald-400" />Local-only · review before outreach</div></div>
    </div>

    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map(([label, value, Icon]) => <div key={label} className="rounded-2xl border border-border bg-card p-4"><div className="flex items-center justify-between text-xs uppercase tracking-wider text-muted-foreground"><span>{label}</span><Icon className="h-4 w-4" /></div><div className="mt-3 text-2xl font-bold">{value}</div></div>)}
    </div>

    <section className="rounded-2xl border border-border bg-card p-4">
      <div className="grid gap-3 md:grid-cols-[1fr_180px_auto]">
        <label className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search recruiter, company, client, skill, or evidence" className="h-9 w-full rounded-xl border border-border bg-secondary pl-9 pr-3 text-sm outline-none focus:ring-1 focus:ring-primary" /></label>
        <select value={status} onChange={event => setStatus(event.target.value)} className="h-9 rounded-xl border border-border bg-secondary px-3 text-sm"><option value="">All statuses</option>{STATUSES.map(item => <option key={item} value={item}>{item}</option>)}</select>
        <label className="flex h-9 items-center gap-2 rounded-xl border border-border bg-secondary px-3 text-sm"><input type="checkbox" checked={chicagoOnly} onChange={event => setChicagoOnly(event.target.checked)} className="accent-violet-500" />Chicago roles/end clients</label>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Recruiters may live elsewhere; the filter keeps contacts with Chicago, Illinois, nearby-suburb, United Airlines, or UAL evidence.</p>
    </section>

    {isLoading ? <div className="grid min-h-48 place-items-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div> : <div className="grid gap-4 lg:grid-cols-2">
      {contacts.map(contact => {
        const enabledSignals = Object.entries(contact.signals || {}).filter(([, enabled]) => enabled)
        return <article key={contact.id} className="rounded-2xl border border-border bg-card p-5">
          <div className="flex items-start gap-4">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-secondary"><Building2 className="h-5 w-5 text-primary" /></div>
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{contact.name || 'Unnamed contact'}</h2><p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{contact.headline || contact.company || 'Recruiter/vendor contact'}</p></div><span className={`rounded-full border px-2.5 py-1 text-xs font-bold ${scoreStyle(contact.score || 0)}`}>{contact.score || 0}/100</span></div>
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">{contact.company && <span><Building2 className="mr-1 inline h-3.5 w-3.5" />{contact.company}</span>}{contact.location && <span><MapPin className="mr-1 inline h-3.5 w-3.5" />{contact.location}</span>}{contact.connectionDegree && <span>{contact.connectionDegree} connection</span>}</div>
            </div>
          </div>

          <div className="mt-4 flex min-h-7 flex-wrap gap-1.5">{enabledSignals.map(([key]) => <span key={key} className="rounded-full bg-primary/10 px-2 py-1 text-[10px] font-semibold text-primary">{SIGNAL_LABELS[key] || key}</span>)}{enabledSignals.length === 0 && <span className="text-xs text-muted-foreground">No qualification evidence captured yet</span>}</div>
          {contact.riskFlags?.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{contact.riskFlags.map(flag => <span key={flag} className="rounded-full bg-red-500/10 px-2 py-1 text-[10px] font-semibold text-red-300"><AlertTriangle className="mr-1 inline h-3 w-3" />{flag}</span>)}</div>}
          {contact.notes && <p className="mt-3 rounded-xl bg-secondary/60 p-3 text-xs text-muted-foreground">{contact.notes}</p>}

          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4">
            <select value={contact.status || 'discovered'} onChange={event => update(contact, { status: event.target.value })} disabled={busy === contact.id} className="h-8 rounded-lg border border-border bg-secondary px-2 text-xs">{STATUSES.map(item => <option key={item} value={item}>{item}</option>)}</select>
            <button onClick={() => createDraft(contact)} disabled={busy === contact.id} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary/10 px-3 text-xs font-medium text-primary hover:bg-primary/20 disabled:opacity-50">{busy === contact.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MessageSquareText className="h-3.5 w-3.5" />}Draft outreach</button>
            <button onClick={() => remove(contact)} disabled={busy === contact.id} title="Delete local contact" className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2 text-xs text-muted-foreground hover:bg-red-500/10 hover:text-red-600 disabled:opacity-50"><Trash2 className="h-3.5 w-3.5" /></button>
            {contact.linkedinUrl && <a href={contact.linkedinUrl} target="_blank" rel="noreferrer" className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-xs hover:bg-secondary">LinkedIn <ExternalLink className="h-3.5 w-3.5" /></a>}
          </div>
        </article>
      })}
    </div>}

    {!isLoading && contacts.length === 0 && <div className="rounded-2xl border border-dashed border-border py-16 text-center"><Users className="mx-auto h-10 w-10 text-muted-foreground/30" /><h2 className="mt-4 font-semibold">No matching contacts yet</h2><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">Add a recruiter manually, or capture a LinkedIn recruiter profile with the browser companion. Contacts stay in this local workspace.</p><button onClick={() => setAdding(true)} className="mt-5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white">Add first contact</button></div>}

    {adding && <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onClick={() => setAdding(false)}><div className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl" onClick={event => event.stopPropagation()}><div><p className="text-xs font-semibold uppercase tracking-wider text-primary">Local CRM</p><h2 className="mt-1 text-lg font-semibold">Add recruiter or hiring contact</h2></div><div className="mt-5 grid gap-3 sm:grid-cols-2">{([['name','Name'],['company','Company'],['location','Location'],['email','Email'],['linkedinUrl','LinkedIn profile URL']] as const).map(([key,label]) => <label key={key} className={`text-xs text-muted-foreground ${key === 'linkedinUrl' ? 'sm:col-span-2' : ''}`}>{label}<input value={newContact[key]} onChange={event => setNewContact({...newContact, [key]:event.target.value})} className="field mt-1 w-full text-sm text-foreground outline-none" /></label>)}<label className="text-xs text-muted-foreground sm:col-span-2">Notes<textarea value={newContact.notes} onChange={event => setNewContact({...newContact, notes:event.target.value})} rows={4} className="mt-1 w-full rounded-xl border border-border bg-secondary p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" /></label></div><div className="mt-5 flex justify-end gap-2"><button onClick={() => setAdding(false)} className="rounded-lg border border-border px-4 py-2 text-sm">Cancel</button><button onClick={addContact} disabled={savingContact || (!newContact.name.trim() && !newContact.linkedinUrl.trim() && !newContact.email.trim())} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-40">{savingContact && <Loader2 className="h-4 w-4 animate-spin" />}Save contact</button></div></div></div>}

    {draft && <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onClick={() => setDraft(null)}><div className="w-full max-w-2xl rounded-2xl border border-border bg-card p-6 shadow-2xl" onClick={event => event.stopPropagation()}><div className="flex items-center justify-between"><div><p className="text-xs uppercase tracking-wider text-muted-foreground">Review-only outreach draft</p><h2 className="mt-1 text-lg font-semibold">{draft.name}</h2></div><MessageSquareText className="h-5 w-5 text-primary" /></div><textarea value={draft.text} onChange={event => setDraft({ ...draft, text: event.target.value })} rows={9} className="mt-5 w-full rounded-xl border border-border bg-secondary p-3 text-sm outline-none focus:ring-1 focus:ring-primary" /><div className="mt-4 flex justify-end gap-2"><button onClick={() => setDraft(null)} className="rounded-lg border border-border px-4 py-2 text-sm">Close</button><button onClick={async () => { await navigator.clipboard.writeText(draft.text); toast.success('Draft copied') }} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white"><Clipboard className="h-4 w-4" />Copy draft</button></div><p className="mt-3 text-xs text-muted-foreground">Copying does not send the message. Verify the role, end client, employer, rate, and vendor chain before signing an RTR.</p></div></div>}
  </div>
}
