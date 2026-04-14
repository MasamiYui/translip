import { useQuery } from '@tanstack/react-query'
import { Monitor, CheckCircle, AlertCircle } from 'lucide-react'
import { systemApi } from '../../api/config'

export function Header() {
  const { data: sysInfo } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
    staleTime: 30000,
    retry: 1,
  })

  return (
    <header className="fixed top-0 right-0 left-[220px] h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 z-30">
      <div />
      <div className="flex items-center gap-4">
        {sysInfo && (
          <>
            <div className="flex items-center gap-1.5 text-sm text-slate-600">
              <Monitor size={14} className="text-slate-400" />
              <span>{sysInfo.device}</span>
            </div>
            <div className="flex items-center gap-1.5 text-sm">
              <CheckCircle size={14} className="text-emerald-500" />
              <span className="text-slate-600">Ready</span>
            </div>
          </>
        )}
        {!sysInfo && (
          <div className="flex items-center gap-1.5 text-sm text-slate-400">
            <AlertCircle size={14} />
            <span>连接中...</span>
          </div>
        )}
      </div>
    </header>
  )
}
