import { motion } from 'framer-motion'
import {
  Bot, Briefcase, ChevronRight, Command, FileText, FileUser, Globe,
  Goal, Inbox, LayoutDashboard, Menu, Microscope, Plus, Settings, User, Users,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { Drawer } from 'vaul'
import { CommandMenu } from './CommandMenu'
import { QuickApplyDialog } from './QuickApplyDialog'
import { Button } from './ui/button'

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/jobs', icon: Briefcase, label: 'Browse jobs' },
  { to: '/auto-apply', icon: Bot, label: 'Automation', badge: 'Live' },
  { to: '/applications', icon: FileText, label: 'Applications' },
  { to: '/inbox', icon: Inbox, label: 'Inbox' },
  { to: '/tracker', icon: Goal, label: 'Tracker' },
  { to: '/networking', icon: Users, label: 'Networking', badge: 'Beta' },
  { to: '/resume', icon: FileUser, label: 'Resume' },
  { to: '/profile', icon: User, label: 'Profile' },
  { to: '/research', icon: Microscope, label: 'Research', badge: 'New' },
]

export function Layout() {
  const loc = useLocation()
  const [commandsOpen, setCommandsOpen] = useState(false)
  const [quickApplyOpen, setQuickApplyOpen] = useState(false)
  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden h-screen w-60 shrink-0 flex-col border-r border-border/70 bg-card md:sticky md:top-0 md:flex">
        <div className="flex h-[60px] items-center gap-2.5 border-b border-border/70 px-5">
          <span className="grid h-8 w-8 place-items-center border-2 border-foreground bg-primary text-white shadow-sm"><span className="text-sm font-black">N</span></span>
          <span className="text-base font-black tracking-[-.04em]">Nori AI</span>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {nav.map(({ to, icon: Icon, label, badge }) => {
            const active = to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(to)
            return <NavLink key={to} to={to} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${active ? 'bg-primary/10 font-medium text-primary' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'}`}>
              <Icon className="h-4 w-4" /><span>{label}</span>
              {badge && !active && <span className="ml-auto rounded-full border border-primary/25 bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-primary">{badge}</span>}
              {active && <motion.div layoutId="nav-indicator" className="ml-auto"><ChevronRight className="h-4 w-4" /></motion.div>}
            </NavLink>
          })}
        </nav>
        <div className="space-y-1 border-t border-border/70 p-3">
          <NavLink to="/linkedin" className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"><Globe className="h-4 w-4" />LinkedIn harvest</NavLink>
          <NavLink to="/settings" className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"><Settings className="h-4 w-4" />Settings</NavLink>
          <div className="flex items-center justify-between px-3 pt-2 text-[10px] text-muted-foreground"><span>Nori local engine</span><span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,.7)]" /></div>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex h-[60px] items-center justify-between border-b border-border/70 bg-background/85 px-4 backdrop-blur-xl md:px-7">
          <button onClick={() => setCommandsOpen(true)} className="flex min-w-0 items-center gap-2 rounded-xl border border-transparent px-2 py-1.5 text-xs text-muted-foreground hover:border-border hover:bg-card hover:text-foreground"><Command className="h-4 w-4" /><span className="hidden sm:inline">Search or jump to…</span><kbd className="hidden rounded-md border border-border bg-secondary px-1.5 py-0.5 font-mono text-[9px] lg:inline">Ctrl K</kbd></button>
          <div className="flex items-center gap-2"><Button size="sm" onClick={() => setQuickApplyOpen(true)} className="hidden uppercase sm:inline-flex"><Plus className="h-3.5 w-3.5" />Prepare job</Button><span className="border-2 border-border bg-card px-3 py-1.5 font-mono text-[10px] uppercase shadow-sm"><b className="text-foreground">Local</b> / review</span><div className="grid h-8 w-8 place-items-center border-2 border-foreground bg-accent text-xs font-black text-black shadow-sm">DS</div></div>
        </header>
        <motion.div key={loc.pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }} className="p-4 pb-24 md:p-7"><Outlet /></motion.div>
      </main>
      <nav className="fixed inset-x-3 bottom-3 z-50 flex items-center justify-around rounded-2xl border border-border bg-card/95 p-2 shadow-2xl backdrop-blur-xl md:hidden">
        {nav.slice(0, 4).map(({ to, icon: Icon, label }) => <NavLink key={to} to={to} className={({isActive}) => `flex min-w-14 flex-col items-center gap-1 rounded-xl px-2 py-1.5 text-[10px] ${isActive ? 'bg-primary/15 text-primary' : 'text-muted-foreground'}`}><Icon className="h-4 w-4" /><span>{label.split(' ')[0]}</span></NavLink>)}
        <Drawer.Root>
          <Drawer.Trigger onClick={event => event.currentTarget.blur()} className="flex min-w-14 flex-col items-center gap-1 rounded-xl px-2 py-1.5 text-[10px] text-muted-foreground"><Menu className="h-4 w-4" />More</Drawer.Trigger>
          <Drawer.Portal>
            <Drawer.Overlay className="fixed inset-0 z-[60] bg-black/55" />
            <Drawer.Content className="fixed inset-x-0 bottom-0 z-[65] rounded-t-[28px] border-2 border-border bg-card p-4 pb-8">
              <div className="mx-auto mb-5 h-1.5 w-12 rounded-full bg-zinc-700" />
              <Drawer.Title className="mb-3 px-2 text-sm font-semibold">All tools</Drawer.Title>
              <div className="grid grid-cols-3 gap-2">{nav.slice(4).map(({to,icon:Icon,label}) => <Drawer.Close asChild key={to}><NavLink to={to} className="flex flex-col items-center gap-2 rounded-2xl border border-border bg-card p-4 text-center text-xs text-muted-foreground"><Icon className="h-5 w-5 text-primary" />{label}</NavLink></Drawer.Close>)}</div>
              <div className="mt-2 grid grid-cols-2 gap-2"><Drawer.Close asChild><NavLink to="/linkedin" className="rounded-xl border border-border p-3 text-center text-xs">LinkedIn harvest</NavLink></Drawer.Close><Drawer.Close asChild><NavLink to="/settings" className="rounded-xl border border-border p-3 text-center text-xs">Settings</NavLink></Drawer.Close></div>
            </Drawer.Content>
          </Drawer.Portal>
        </Drawer.Root>
      </nav>
      <CommandMenu open={commandsOpen} onOpenChange={setCommandsOpen} onQuickApply={() => setQuickApplyOpen(true)} />
      <QuickApplyDialog open={quickApplyOpen} onOpenChange={setQuickApplyOpen} />
    </div>
  )
}
