import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MainLayout } from './components/layout/MainLayout'
import { I18nProvider } from './i18n/I18nProvider'

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then(module => ({ default: module.DashboardPage })),
)
const TaskListPage = lazy(() =>
  import('./pages/TaskListPage').then(module => ({ default: module.TaskListPage })),
)
const NewTaskPage = lazy(() =>
  import('./pages/NewTaskPage').then(module => ({ default: module.NewTaskPage })),
)
const TaskDetailPage = lazy(() =>
  import('./pages/TaskDetailPage').then(module => ({ default: module.TaskDetailPage })),
)
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then(module => ({ default: module.SettingsPage })),
)
const DubbingEditorPage = lazy(() =>
  import('./pages/DubbingEditorPage').then(module => ({ default: module.DubbingEditorPage })),
)
const ToolListPage = lazy(() =>
  import('./pages/ToolListPage').then(module => ({ default: module.ToolListPage })),
)
const ToolPage = lazy(() =>
  import('./pages/ToolPage').then(module => ({ default: module.ToolPage })),
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10000,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter>
          <Suspense
            fallback={
              <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
                Loading…
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<MainLayout />}>
                <Route index element={<DashboardPage />} />
                <Route path="tasks" element={<TaskListPage />} />
                <Route path="tasks/new" element={<NewTaskPage />} />
                <Route path="tasks/:id" element={<TaskDetailPage />} />
                <Route path="tasks/:id/dubbing-editor" element={<DubbingEditorPage />} />
                <Route path="tools" element={<ToolListPage />} />
                <Route path="tools/:toolId" element={<ToolPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  )
}
