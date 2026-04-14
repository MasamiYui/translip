import { useQuery } from '@tanstack/react-query'
import { systemApi } from '../api/config'
import { formatBytes } from '../lib/utils'
import { CheckCircle, XCircle } from 'lucide-react'

export function SettingsPage() {
  const { data: sysInfo, isLoading } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">全局设置</h1>

      {/* System info */}
      <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">系统信息</h2>
        {isLoading ? (
          <div className="text-sm text-slate-400">加载中...</div>
        ) : sysInfo ? (
          <div className="space-y-3 text-sm">
            <InfoRow label="Python" value={sysInfo.python_version} />
            <InfoRow label="平台" value={sysInfo.platform} />
            <InfoRow label="计算设备" value={sysInfo.device} />
            <InfoRow label="缓存目录" value={sysInfo.cache_dir} mono />
            <InfoRow label="缓存大小" value={formatBytes(sysInfo.cache_size_bytes)} />
          </div>
        ) : (
          <div className="text-sm text-red-500">无法连接到后端服务</div>
        )}
      </section>

      {/* Model status */}
      {sysInfo && (
        <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">模型状态</h2>
          <div className="space-y-2">
            {sysInfo.models.map(m => (
              <div key={m.name} className="flex items-center justify-between py-2.5 border-b border-slate-50 last:border-0">
                <span className="text-sm text-slate-700">{m.name}</span>
                <div className="flex items-center gap-1.5 text-sm">
                  {m.status === 'available' ? (
                    <>
                      <CheckCircle size={14} className="text-emerald-500" />
                      <span className="text-emerald-700">已下载</span>
                    </>
                  ) : (
                    <>
                      <XCircle size={14} className="text-slate-400" />
                      <span className="text-slate-400">未下载</span>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* About */}
      <section className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">关于</h2>
        <div className="text-sm text-slate-600 space-y-1">
          <p>Video Voice Separate — Pipeline Management System</p>
          <p className="text-slate-400">v0.1.0 · Speaker-aware multilingual dubbing pipeline</p>
        </div>
      </section>
    </div>
  )
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-4">
      <span className="text-slate-500 w-24 shrink-0">{label}</span>
      <span className={`text-slate-900 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}
