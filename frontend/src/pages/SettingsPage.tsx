import { useQuery } from '@tanstack/react-query'
import { systemApi } from '../api/config'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { CacheSection } from '../components/settings/CacheSection'
import { formatBytes } from '../lib/utils'
import { CheckCircle, XCircle } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'

export function SettingsPage() {
  const { t } = useI18n()
  const { data: sysInfo, isLoading } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
  })

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">{t.settings.title}</h1>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        {/* System info */}
        <div className="border-b border-slate-100 px-6 py-5">
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">{t.settings.systemInfo}</h2>
          {isLoading ? (
            <div className="text-sm text-slate-400">{t.common.loading}</div>
          ) : sysInfo ? (
            <div className="divide-y divide-slate-100 text-sm">
              <InfoRow label={t.settings.fields.python} value={sysInfo.python_version} />
              <InfoRow label={t.settings.fields.platform} value={sysInfo.platform} />
              <InfoRow label={t.settings.fields.device} value={sysInfo.device} />
              <InfoRow label={t.settings.fields.cacheDir} value={sysInfo.cache_dir} mono />
              <InfoRow label={t.settings.fields.cacheSize} value={formatBytes(sysInfo.cache_size_bytes)} />
            </div>
          ) : (
            <div className="border-l-2 border-rose-400 bg-rose-50 py-2 pl-3 text-sm text-rose-600">{t.settings.connectionError}</div>
          )}
        </div>

        {/* Model status */}
        {sysInfo && (
          <div className="border-b border-slate-100 px-6 py-5">
            <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">{t.settings.modelStatus}</h2>
            <div className="divide-y divide-slate-100">
              {sysInfo.models.map(m => (
                <div key={m.name} className="flex items-center justify-between py-2.5">
                  <span className="text-sm text-slate-700">{m.name}</span>
                  <div className="flex items-center gap-1.5 text-sm">
                    {m.status === 'available' ? (
                      <>
                        <CheckCircle size={14} className="text-emerald-500" />
                        <span className="text-emerald-700">{t.settings.models.downloaded}</span>
                      </>
                    ) : (
                      <>
                        <XCircle size={14} className="text-slate-400" />
                        <span className="text-slate-400">{t.settings.models.missing}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Cache management */}
        <CacheSection />

        {/* About */}
        <div className="px-6 py-5">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-400">{t.settings.about}</h2>
          <div className="text-sm text-slate-600 space-y-1">
            <p>{t.settings.aboutTitle}</p>
            <p className="text-slate-400">{t.settings.aboutSubtitle}</p>
          </div>
        </div>
      </div>
    </PageContainer>
  )
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-4 py-2.5">
      <span className="w-24 shrink-0 text-slate-400">{label}</span>
      <span className={`text-slate-700 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}
