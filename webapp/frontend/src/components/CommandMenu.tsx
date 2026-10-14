import * as Dialog from '@radix-ui/react-dialog'
import { Command } from 'cmdk'
import { Bot, Briefcase, FileText, Goal, LayoutDashboard, Search, Settings, User, Zap } from 'lucide-react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const destinations = [
  ['Dashboard', '/', LayoutDashboard], ['Browse jobs', '/jobs', Briefcase],
  ['Applications', '/applications', FileText], ['Automation', '/auto-apply', Bot],
  ['Tracker', '/tracker', Goal], ['Profile', '/profile', User], ['Settings', '/settings', Settings],
] as const

export function CommandMenu({ open, onOpenChange, onQuickApply }: { open: boolean; onOpenChange: (open: boolean) => void; onQuickApply: () => void }) {
  const navigate = useNavigate()
  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); onOpenChange(!open) } }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onOpenChange])
  const select = (path: string) => { onOpenChange(false); navigate(path) }
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[70] bg-black/55 backdrop-blur-sm" /><Dialog.Content className="fixed left-1/2 top-[18%] z-[75] w-[calc(100%-24px)] max-w-xl -translate-x-1/2 overflow-hidden rounded-2xl border border-border bg-[#111116] shadow-2xl"><Dialog.Title className="sr-only">Command menu</Dialog.Title><Command label="Global commands" className="w-full"><div className="flex items-center gap-3 border-b border-border px-4"><Search className="h-4 w-4 text-muted-foreground" /><Command.Input autoFocus placeholder="Search pages and actions..." className="h-13 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" /><kbd className="rounded-md border border-border bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">ESC</kbd></div><Command.List className="max-h-96 overflow-y-auto p-2"><Command.Empty className="py-10 text-center text-sm text-muted-foreground">No command found.</Command.Empty><Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"><Command.Item onSelect={() => { onOpenChange(false); onQuickApply() }} className="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm data-[selected=true]:bg-primary/10 data-[selected=true]:text-primary"><Zap className="h-4 w-4" />Prepare a job application</Command.Item></Command.Group><Command.Group heading="Navigate" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground">{destinations.map(([label,path,Icon]) => <Command.Item key={path} onSelect={() => select(path)} className="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm data-[selected=true]:bg-secondary"><Icon className="h-4 w-4 text-muted-foreground" />{label}</Command.Item>)}</Command.Group></Command.List></Command></Dialog.Content></Dialog.Portal></Dialog.Root>
}
