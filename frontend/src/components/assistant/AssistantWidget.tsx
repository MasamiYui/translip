import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import {
  AlertCircle,
  Download,
  Loader2,
  Maximize2,
  Minimize2,
  Paperclip,
  Play,
  RotateCcw,
  Send,
  Square,
  Sparkles,
  X,
} from 'lucide-react'
import { assistantApi } from '../../api/assistant'
import { atomicToolsApi } from '../../api/atomic-tools'
import { useI18n } from '../../i18n/useI18n'
import { cn, formatBytes } from '../../lib/utils'
import { useAssistantStore, type ChatMessage } from '../../stores/assistantStore'
import type { AssistantPlan, RunState } from '../../types/assistant'
import { CallChainDiagram } from './CallChainDiagram'
import { RobotMascot, type MascotState } from './RobotMascot'

const EXPANDED_STORAGE_KEY = 'translip:assistant-expanded'

function readExpanded(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(EXPANDED_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof AxiosError) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (detail) return detail
    return error.message
  }
  if (error instanceof Error) return error.message
  return fallback
}

export function AssistantWidget() {
  const { t } = useI18n()
  const {
    isOpen,
    toggle,
    close,
    messages,
    attachments,
    addMessage,
    updateMessage,
    addAttachment,
    removeAttachment,
    clearAttachments,
    reset,
  } = useAssistantStore()

  const [input, setInput] = useState('')
  const [expanded, setExpanded] = useState<boolean>(readExpanded)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [activeMsgId, setActiveMsgId] = useState<string | null>(null)

  function toggleExpanded() {
    setExpanded(prev => {
      const next = !prev
      try {
        window.localStorage.setItem(EXPANDED_STORAGE_KEY, next ? '1' : '0')
      } catch {
        /* ignore */
      }
      return next
    })
  }
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  // --- planning ---
  const planMutation = useMutation({
    mutationFn: (vars: { message: string; fileIds: string[]; filenames: string[] }) =>
      assistantApi.plan(vars.message, vars.fileIds, vars.filenames),
  })

  // --- run polling ---
  const runQuery = useQuery({
    queryKey: ['assistant-run', activeRunId],
    queryFn: () => assistantApi.getRun(activeRunId as string),
    enabled: activeRunId != null,
    refetchInterval: query => {
      const status = (query.state.data as RunState | undefined)?.status
      return status === 'running' || status === 'pending' ? 1200 : false
    },
  })

  // Persist each poll into the owning message. Polling self-stops once the run
  // reaches a terminal status (see refetchInterval below), so there's no need to
  // clear the active run id from here.
  useEffect(() => {
    if (!runQuery.data || !activeMsgId) return
    updateMessage(activeMsgId, { run: runQuery.data })
  }, [runQuery.data, activeMsgId, updateMessage])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, isOpen])

  // --- actions ---
  async function handleSend(text: string) {
    const message = text.trim()
    if (!message || planMutation.isPending) return
    const snapshot = [...attachments]
    addMessage({
      role: 'user',
      kind: 'text',
      text: message,
      attachments: snapshot,
    })
    setInput('')
    clearAttachments()
    const fileIds = snapshot.map(f => f.file_id)
    const filenames = snapshot.map(f => f.filename)
    try {
      const plan = await planMutation.mutateAsync({ message, fileIds, filenames })
      addMessage({ role: 'assistant', kind: 'plan', plan, fileIds, text: plan.summary })
    } catch (error) {
      addMessage({
        role: 'assistant',
        kind: 'error',
        text: errorMessage(error, t.assistant.errorTitle),
      })
    }
  }

  async function handleUpload(files: FileList | null) {
    if (!files) return
    for (const file of Array.from(files)) {
      try {
        const res = await atomicToolsApi.upload(file)
        addAttachment({ file_id: res.file_id, filename: res.filename })
      } catch {
        // surfaced as a plan error later if needed; ignore individual upload failures
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const executeMutation = useMutation({
    mutationFn: (vars: { plan: AssistantPlan; fileIds: string[] }) =>
      assistantApi.execute(vars.plan, vars.fileIds),
  })

  async function handleRun(msg: ChatMessage) {
    if (!msg.plan) return
    try {
      const { run_id } = await executeMutation.mutateAsync({
        plan: msg.plan,
        fileIds: msg.fileIds ?? [],
      })
      updateMessage(msg.id, { runId: run_id })
      setActiveRunId(run_id)
      setActiveMsgId(msg.id)
    } catch (error) {
      addMessage({
        role: 'assistant',
        kind: 'error',
        text: errorMessage(error, t.assistant.errorTitle),
      })
    }
  }

  async function handleCancel() {
    if (!activeRunId) return
    try {
      await assistantApi.cancelRun(activeRunId)
    } catch {
      /* ignore */
    }
  }

  const mascotState: MascotState = planMutation.isPending
    ? 'thinking'
    : runQuery.data && runQuery.data.status === 'running'
      ? 'running'
      : 'idle'

  const exampleList = [
    t.assistant.examples.jaSubs,
    t.assistant.examples.extractVoice,
    t.assistant.examples.removeSubs,
    t.assistant.examples.dubEn,
  ]

  return (
    <>
      {/* Floating launcher */}
      {!isOpen && (
        <button
          type="button"
          onClick={toggle}
          aria-label={t.assistant.open}
          title={t.assistant.open}
          className="assistant-float fixed bottom-6 right-6 z-40 flex h-16 w-16 items-center justify-center rounded-full border border-[#dbe3ff] bg-gradient-to-br from-[#eef2ff] to-white shadow-[0_8px_28px_rgba(59,91,219,0.28)] transition-transform hover:scale-105 print:hidden"
        >
          <RobotMascot state={mascotState} size={44} />
        </button>
      )}

      {/* Chat panel — right-docked, full-height drawer */}
      {isOpen && (
        <div
          role="dialog"
          aria-label={t.assistant.title}
          className={cn(
            'assistant-slide-in fixed right-0 top-0 z-40 flex h-screen max-w-full flex-col overflow-hidden border-l border-[#e4e9f0] bg-white shadow-[-12px_0_40px_rgba(17,24,39,0.14)] transition-[width] duration-200 ease-out print:hidden',
            'w-full',
            expanded ? 'sm:w-[760px]' : 'sm:w-[480px]',
          )}
        >
          {/* Header */}
          <div className="flex items-center gap-3 border-b border-[#eef1f6] bg-gradient-to-r from-[#3b5bdb] to-[#5b8def] px-4 py-3 text-white">
            <RobotMascot state={mascotState} size={34} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{t.assistant.title}</div>
              <div className="truncate text-[11px] text-white/80">{t.assistant.subtitle}</div>
            </div>
            <button
              type="button"
              onClick={toggleExpanded}
              aria-label={expanded ? t.assistant.collapseWidth : t.assistant.expandWidth}
              title={expanded ? t.assistant.collapseWidth : t.assistant.expandWidth}
              className="hidden rounded-md p-1.5 text-white/85 transition-colors hover:bg-white/15 sm:inline-flex"
            >
              {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button
              type="button"
              onClick={reset}
              aria-label={t.assistant.reset}
              title={t.assistant.reset}
              className="rounded-md p-1.5 text-white/85 transition-colors hover:bg-white/15"
            >
              <RotateCcw size={16} />
            </button>
            <button
              type="button"
              onClick={close}
              aria-label={t.assistant.close}
              title={t.assistant.close}
              className="rounded-md p-1.5 text-white/85 transition-colors hover:bg-white/15"
            >
              <X size={16} />
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-[#f7f9fc] px-3 py-3">
            {messages.length === 0 && (
              <div className="space-y-3">
                <div className="flex gap-2">
                  <RobotMascot state="idle" size={28} className="mt-1 shrink-0" />
                  <div className="rounded-2xl rounded-tl-sm bg-white px-3 py-2 text-sm text-[#374151] shadow-sm">
                    {t.assistant.greeting}
                  </div>
                </div>
                <div>
                  <div className="mb-1.5 flex items-center gap-1 px-1 text-[11px] font-medium text-[#9ca3af]">
                    <Sparkles size={12} /> {t.assistant.examplesTitle}
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {exampleList.map(example => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => handleSend(example)}
                        className="rounded-xl border border-[#e4e9f0] bg-white px-3 py-2 text-left text-[13px] text-[#374151] transition-colors hover:border-[#3b5bdb]/50 hover:bg-[#f0f3ff]"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {messages.map(msg => (
              <MessageBubble
                key={msg.id}
                message={msg}
                runState={msg.id === activeMsgId ? runQuery.data ?? msg.run : msg.run}
                onRun={() => handleRun(msg)}
                onCancel={handleCancel}
                onEditPlan={plan => updateMessage(msg.id, { plan })}
                isExecuting={executeMutation.isPending}
              />
            ))}

            {planMutation.isPending && (
              <div className="flex items-center gap-2 px-1 text-[13px] text-[#6b7280]">
                <Loader2 size={14} className="animate-spin" /> {t.assistant.planning}
              </div>
            )}
          </div>

          {/* Attachments */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 border-t border-[#eef1f6] bg-white px-3 py-2">
              {attachments.map(file => (
                <span
                  key={file.file_id}
                  className="inline-flex max-w-[180px] items-center gap-1 rounded-full bg-[#f0f3ff] px-2 py-0.5 text-[11px] text-[#3b5bdb]"
                >
                  <span className="truncate" title={file.filename}>{file.filename}</span>
                  <button type="button" onClick={() => removeAttachment(file.file_id)} aria-label="remove">
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Composer */}
          <div className="border-t border-[#eef1f6] bg-white px-3 py-3">
            <div className="flex items-end gap-2 rounded-xl border border-[#e4e9f0] bg-white px-2 py-1.5 transition-colors focus-within:border-[#3b5bdb] focus-within:ring-2 focus-within:ring-[#3b5bdb]/10">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={e => handleUpload(e.target.files)}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                aria-label={t.assistant.attach}
                title={t.assistant.attach}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[#6b7280] transition-colors hover:bg-[#f3f4f6]"
              >
                <Paperclip size={18} />
              </button>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSend(input)
                  }
                }}
                rows={2}
                placeholder={t.assistant.inputPlaceholder}
                className="max-h-32 min-h-[52px] flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm leading-relaxed text-[#374151] focus:outline-none"
              />
              <button
                type="button"
                onClick={() => handleSend(input)}
                disabled={!input.trim() || planMutation.isPending}
                aria-label={t.assistant.send}
                title={t.assistant.send}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#3b5bdb] text-white transition-colors hover:bg-[#3451c7] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

interface MessageBubbleProps {
  message: ChatMessage
  runState?: RunState | null
  onRun: () => void
  onCancel: () => void
  onEditPlan: (plan: AssistantPlan) => void
  isExecuting: boolean
}

function MessageBubble({ message, runState, onRun, onCancel, onEditPlan, isExecuting }: MessageBubbleProps) {
  const { t } = useI18n()

  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-[#3b5bdb] px-3 py-2 text-sm text-white shadow-sm">
          <div className="whitespace-pre-wrap break-words">{message.text}</div>
          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {message.attachments.map(f => (
                <span key={f.file_id} className="rounded bg-white/20 px-1.5 py-0.5 text-[10px]">
                  {f.filename}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (message.kind === 'error') {
    return (
      <div className="flex gap-2">
        <RobotMascot state="idle" size={26} className="mt-1 shrink-0" />
        <div className="flex items-start gap-2 rounded-2xl rounded-tl-sm border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 shadow-sm">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          <span className="break-words">{message.text}</span>
        </div>
      </div>
    )
  }

  // plan message
  const status = runState?.status
  const started = message.runId != null
  const mascot: MascotState = status === 'completed' ? 'done' : status === 'running' ? 'running' : 'idle'
  const artifacts = runState?.steps.flatMap(s => s.artifacts) ?? []

  return (
    <div className="flex gap-2">
      <RobotMascot state={mascot} size={26} className="mt-1 shrink-0" />
      <div className="min-w-0 flex-1 space-y-2 rounded-2xl rounded-tl-sm bg-white px-3 py-2.5 shadow-sm">
        {message.text && <p className="text-sm text-[#374151]">{message.text}</p>}
        {!started && <p className="text-[12px] text-[#9ca3af]">{t.assistant.planIntro}</p>}

        {message.plan && (
          <div className="overflow-x-auto">
            <CallChainDiagram
              plan={message.plan}
              runState={runState}
              editable={!started}
              onChange={onEditPlan}
            />
          </div>
        )}

        {/* Action bar */}
        {!started && (
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={onRun}
              disabled={isExecuting}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#3b5bdb] px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-[#3451c7] disabled:opacity-50"
            >
              <Play size={14} /> {t.assistant.run}
            </button>
          </div>
        )}

        {status === 'running' && (
          <div className="flex items-center justify-between pt-1">
            <span className="inline-flex items-center gap-1.5 text-[12px] text-[#3b5bdb]">
              <Loader2 size={13} className="animate-spin" /> {t.assistant.running}
            </span>
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex items-center gap-1 rounded-lg border border-[#e4e9f0] px-2 py-1 text-[12px] text-[#6b7280] transition-colors hover:bg-[#f3f4f6]"
            >
              <Square size={12} /> {t.assistant.cancelRun}
            </button>
          </div>
        )}

        {status === 'failed' && runState?.error_message && (
          <p className="text-[12px] text-red-600">{runState.error_message}</p>
        )}

        {status === 'completed' && (
          <div className="space-y-1.5 border-t border-[#eef1f6] pt-2">
            <p className="text-[12px] font-medium text-emerald-700">{t.assistant.doneTitle}</p>
            {artifacts.length === 0 && (
              <p className="text-[12px] text-[#9ca3af]">{t.assistant.noArtifacts}</p>
            )}
            <div className="flex flex-col gap-1">
              {artifacts.map(a => (
                <a
                  key={a.download_url}
                  href={a.download_url}
                  download
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#e4e9f0] px-2.5 py-1.5 text-[12px] text-[#3b5bdb] transition-colors hover:bg-[#f0f3ff]"
                >
                  <Download size={13} />
                  <span className="truncate" title={a.filename}>{a.filename}</span>
                  <span className="ml-auto text-[10px] text-[#9ca3af]">{formatBytes(a.size_bytes)}</span>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
