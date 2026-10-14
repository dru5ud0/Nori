import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { Layout } from './components/Layout'

const Dashboard = lazy(() => import('./pages/Dashboard').then(module => ({ default: module.Dashboard })))
const Applications = lazy(() => import('./pages/Applications').then(module => ({ default: module.Applications })))
const ApplicationDetail = lazy(() => import('./pages/ApplicationDetail').then(module => ({ default: module.ApplicationDetail })))
const Jobs = lazy(() => import('./pages/Jobs').then(module => ({ default: module.Jobs })))
const LinkedIn = lazy(() => import('./pages/LinkedIn').then(module => ({ default: module.LinkedIn })))
const Profile = lazy(() => import('./pages/Profile').then(module => ({ default: module.Profile })))
const AutoApply = lazy(() => import('./pages/ProductPages').then(module => ({ default: module.AutoApply })))
const Inbox = lazy(() => import('./pages/ProductPages').then(module => ({ default: module.Inbox })))
const Tracker = lazy(() => import('./pages/ProductPages').then(module => ({ default: module.Tracker })))
const Networking = lazy(() => import('./pages/Networking').then(module => ({ default: module.Networking })))
const Resume = lazy(() => import('./pages/ProductPages').then(module => ({ default: module.Resume })))
const Research = lazy(() => import('./pages/ProductPages').then(module => ({ default: module.Research })))
const Settings = lazy(() => import('./pages/ProductPages').then(module => ({ default: module.Settings })))

function PageLoader() {
  return <div className="space-y-4" aria-label="Loading page"><div className="h-9 w-56 animate-pulse rounded-xl bg-secondary" /><div className="h-24 animate-pulse rounded-2xl border border-border bg-card" /><div className="h-64 animate-pulse rounded-2xl border border-border bg-card" /></div>
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15_000 } },
})

export default function App() {
  return <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="jobs" element={<Jobs />} />
            <Route path="auto-apply" element={<AutoApply />} />
            <Route path="applications" element={<Applications />} />
            <Route path="applications/:id" element={<ApplicationDetail />} />
            <Route path="inbox" element={<Inbox />} />
            <Route path="tracker" element={<Tracker />} />
            <Route path="networking" element={<Networking />} />
            <Route path="resume" element={<Resume />} />
            <Route path="profile" element={<Profile />} />
            <Route path="research" element={<Research />} />
            <Route path="linkedin" element={<LinkedIn />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </Suspense>
      <Toaster theme="dark" richColors position="bottom-right" />
    </BrowserRouter>
  </QueryClientProvider>
}
