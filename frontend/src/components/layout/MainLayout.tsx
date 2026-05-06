import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

export function MainLayout() {
  const { pathname } = useLocation()
  const isWorkbench = /\/tasks\/[^/]+\/dubbing-editor\/?$/.test(pathname)

  return (
    <div className="min-h-screen bg-white">
      <Sidebar />
      <Header workbench={isWorkbench} />
      <main
        className={
          isWorkbench
            ? 'ml-[220px] pt-12 h-screen overflow-hidden bg-[#F5F7FB]'
            : 'ml-[220px] pt-16 min-h-screen'
        }
      >
        {isWorkbench ? (
          <div className="h-[calc(100vh-48px)] animate-[fadeIn_150ms_ease-out]">
            <Outlet />
          </div>
        ) : (
          <div className="p-6">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
