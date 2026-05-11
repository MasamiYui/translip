import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { systemApi } from '../api/config'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { CacheSection } from '../components/settings/CacheSection'
import { formatBytes } from '../lib/utils'
import { CheckCircle, XCircle, Save, Lock } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import { worksApi } from '../api/works'

export function SettingsPage() {
  const { t } = useI18n()
  const { data: sysInfo, isLoading } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
  })

  const { data: tmdbConfig } = useQuery({
    queryKey: ['tmdb-config'],
    queryFn: worksApi.tmdbGetConfig,
  })

  const [apiKeyV3, setApiKeyV3] = useState('')
  const [apiKeyV4, setApiKeyV4] = useState('')
  const [defaultLanguage, setDefaultLanguage] = useState('zh-CN')

  const saveMutation = useMutation({
    mutationFn: () =>
      worksApi.tmdbSaveConfig({
        api_key_v3: apiKeyV3 || undefined,
        api_key_v4: apiKeyV4 || undefined,
        default_language: defaultLanguage || undefined,
      }),
    onSuccess: () => {
      // Refresh config
    },
  })

  const handleSave = () => {
    saveMutation.mutate()
  }

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
              <CacheSection cacheSize={formatBytes(sysInfo.cache_size_bytes)} />
            </div>
          ) : (
            <div className="border-l-2 border-rose-400 bg-rose-50 py-2 pl-3 text-sm text-rose-600">{t.settings.connectionError}</div>
          )}
        </div>

        {/* TMDb Configuration */}
        <div className="border-b border-slate-100 px-6 py-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">TMDb API</h2>
            {tmdbConfig?.ok && (tmdbConfig.api_key_v3_set || tmdbConfig.api_key_v4_set) ? (
              <div className="flex items-center gap-1.5 text-sm text-emerald-600">
                <CheckCircle size={14} />
                <span>已配置</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-sm text-amber-600">
                <XCircle size={14} />
                <span>未配置</span>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm">
              <Lock size={14} className="text-slate-400" />
              <span className="text-slate-500">API 密钥会保存在本地配置文件中，不会上传到服务器。</span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  API Key (v3)
                </label>
                <input
                  type="password"
                  value={apiKeyV3}
                  onChange={(e) => setApiKeyV3(e.target.value)}
                  placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
                {tmdbConfig?.api_key_v3_set && !apiKeyV3 && (
                  <p className="mt-1 text-xs text-slate-500">已保存（点击输入框可修改）</p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Bearer Token (v4)
                </label>
                <input
                  type="password"
                  value={apiKeyV4}
                  onChange={(e) => setApiKeyV4(e.target.value)}
                  placeholder="eyJhbGciOiJIUzI1NiJ9..."
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
                {tmdbConfig?.api_key_v4_set && !apiKeyV4 && (
                  <p className="mt-1 text-xs text-slate-500">已保存（点击输入框可修改）</p>
                )}
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                默认语言
              </label>
              <select
                value={defaultLanguage}
                onChange={(e) => setDefaultLanguage(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="zh-CN">中文 (简体)</option>
                <option value="zh-TW">中文 (繁體)</option>
                <option value="en-US">English</option>
                <option value="ja-JP">日本語</option>
                <option value="ko-KR">한국어</option>
              </select>
            </div>

            <button
              onClick={handleSave}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save size={16} />
              {saveMutation.isPending ? '保存中...' : '保存配置'}
            </button>
          </div>
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
