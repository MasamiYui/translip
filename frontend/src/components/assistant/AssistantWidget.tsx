import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import {
  AlertCircle,
  ChevronDown,
  Download,
  Loader2,
  Maximize2,
  Minimize2,
  Paperclip,
  Play,
  RotateCcw,
  Send,
  Settings,
  Sparkles,
  Square,
  Upload,
  X,
} from 'lucide-react'
import { assistantApi } from '../../api/assistant'
import { atomicToolsApi } from '../../api/atomic-tools'
import { systemApi } from '../../api/config'
import { useI18n } from '../../i18n/useI18n'
import { cn, formatBytes } from '../../lib/utils'
import { useAssistantStore, type AvailableFile, type ChatMessage } from '../../stores/assistantStore'
import type { AssistantPlan, ConversationTurn, RunState } from '../../types/assistant'
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

function formatTime(ms: number): string {
  try {
    return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

/** Highest upload_index a plan references, or -1 if it needs no uploaded file. */
function maxUploadIndex(plan: AssistantPlan): number {
  let max = -1
  for (const step of plan.steps) {
    for (const binding of Object.values(step.inputs)) {
      if (binding.source === 'upload') {
        max = Math.max(max, binding.upload_index ?? 0)
      }
    }
  }
  return max
}

/** Build the planner's conversation history from prior turns (current turn excluded). */
function buildHistory(messages: ChatMessage[], limit = 10): ConversationTurn[] {
  const turns: ConversationTurn[] = []
  for (const m of messages) {
    if (m.role === 'user') {
      if (m.text) turns.push({ role: 'user', content: m.text })
      continue
    }
    if (m.kind === 'plan') {
      const names = m.run?.steps.flatMap(s => s.artifacts).map(a => a.filename) ?? []
      let content = m.text || '已规划调用链路'
      if (m.run?.status === 'completed') {
        content += names.length ? `（已执行，产物：${names.join('、')}）` : '（已执行）'
      } else if (m.runId) {
        content += '（执行中）'
      } else {
        content += '（已规划未执行）'
      }
      turns.push({ role: 'assistant', content })
    } else if (m.kind === 'clarification') {
      turns.push({ role: 'assistant', content: m.clarification?.question ?? m.text ?? '' })
    } else if (m.kind === 'text' && m.text) {
      turns.push({ role: 'assistant', content: m.text })
    }
  }
  return turns.slice(-limit)
}

function findActiveRunMessage(messages: ChatMessage[]): ChatMessage | undefined {
  return [...messages]
    .reverse()
    .find(m => m.runId != null && (m.run?.status === 'running' || m.run?.status === 'pending'))
}

interface UploadingFile {
  key: string
  filename: string
  progress: number
}

export function AssistantWidget() {
  const { t } = useI18n()
  const {
    isOpen,
    conversationId,
    toggle,
    close,
    messages,
    attachments,
    availableFiles,
    addMessage,
    updateMessage,
    addAttachment,
    removeAttachment,
    clearAttachments,
    addAvailableFiles,
    reset,
  } = useAssistantStore()

  const [input, setInput] = useState('')
  const [expanded, setExpanded] = useState<boolean>(readExpanded)
  // Resume polling for a run that was still in flight when the page was reloaded.
  const [activeRunId, setActiveRunId] = useState<string | null>(
    () => findActiveRunMessage(useAssistantStore.getState().messages)?.runId ?? null,
  )
  const [activeMsgId, setActiveMsgId] = useState<string | null>(
    () => findActiveRunMessage(useAssistantStore.getState().messages)?.id ?? null,
  )
  const [uploading, setUploading] = useState<UploadingFile[]>([])
  const [showScrollButton, setShowScrollButton] = useState(false)

  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const nearBottomRef = useRef(true)

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

  // --- DeepSeek key availability (fail-open) ---
  const keyQuery = useQuery({
    queryKey: ['assistant-llm-keys'],
    queryFn: () => systemApi.getLlmKeys(),
    enabled: isOpen,
    staleTime: 30_000,
  })
  const keyMissing = keyQuery.data ? keyQuery.data.providers?.deepseek === false : false

  // --- planning ---
  const planMutation = useMutation({
    mutationFn: (vars: {
      message: string
      fileIds: string[]
      filenames: string[]
      history: ConversationTurn[]
      availableRefs: { label: string; filename: string }[]
    }) =>
      assistantApi.plan(vars.message, vars.fileIds, vars.filenames, vars.history, vars.availableRefs),
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

  useEffect(() => {
    if (!runQuery.data || !activeMsgId) return
    updateMessage(activeMsgId, { run: runQuery.data })
    // When a run completes, its artifacts become reusable inputs for later turns.
    if (runQuery.data.status === 'completed') {
      const outputs: AvailableFile[] = runQuery.data.steps
        .flatMap(s => s.artifacts)
        .filter(a => a.file_id)
        .map(a => ({ file_id: a.file_id as string, filename: a.filename, origin: 'output' }))
      if (outputs.length) addAvailableFiles(outputs)
    }
  }, [runQuery.data, activeMsgId, updateMessage, addAvailableFiles])

  // Autoscroll only when the user is already near the bottom (don't yank them up).
  useEffect(() => {
    if (scrollRef.current && nearBottomRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, isOpen])

  // ESC closes the drawer.
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, close])

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    nearBottomRef.current = distance < 60
    setShowScrollButton(distance > 120)
  }

  function scrollToBottom() {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  // --- actions ---
  async function handleSend(rawText: string) {
    const text = rawText.trim()
    if (!text || planMutation.isPending || keyMissing) return

    // If the latest assistant message is an unanswered clarification, merge the
    // original request with this answer so the planner has full context — without
    // any server-side conversation memory.
    const pending = [...messages]
      .reverse()
      .find(m => m.role === 'assistant' && m.kind === 'clarification' && !m.answered)

    const snapshot = [...attachments]
    // Conversation file pool = prior pool (uploads + run outputs) + this turn's new attachments.
    const pool: AvailableFile[] = []
    const seen = new Set<string>()
    for (const f of [
      ...availableFiles,
      ...snapshot.map(a => ({ file_id: a.file_id, filename: a.filename, origin: 'upload' as const })),
    ]) {
      if (!seen.has(f.file_id)) {
        seen.add(f.file_id)
        pool.push(f)
      }
    }
    const fileIds = pool.map(f => f.file_id)
    const availableRefs = pool.map(f => ({
      label: f.origin === 'output' ? `上一步产物：${f.filename}` : `上传文件：${f.filename}`,
      filename: f.filename,
    }))
    const history = buildHistory(messages)
    let effectiveMessage = text

    if (pending) {
      effectiveMessage = `${pending.sourceText ?? ''}\n（补充说明：${text}）`.trim()
      updateMessage(pending.id, { answered: true })
    }

    addMessage({ role: 'user', kind: 'text', text, attachments: snapshot })
    setInput('')
    // Persist this turn's uploads into the conversation pool, then clear staging.
    if (snapshot.length > 0) {
      addAvailableFiles(
        snapshot.map(a => ({ file_id: a.file_id, filename: a.filename, origin: 'upload' as const })),
      )
    }
    clearAttachments()

    try {
      const result = await planMutation.mutateAsync({
        message: effectiveMessage,
        fileIds,
        filenames: pool.map(f => f.filename),
        history,
        availableRefs,
      })
      if (result.type === 'clarification' && result.clarification) {
        addMessage({
          role: 'assistant',
          kind: 'clarification',
          clarification: result.clarification,
          text: result.clarification.question,
          sourceText: effectiveMessage,
          sourceFileIds: fileIds,
        })
      } else if (result.plan) {
        addMessage({
          role: 'assistant',
          kind: 'plan',
          plan: result.plan,
          fileIds,
          text: result.plan.summary,
        })
      } else {
        addMessage({ role: 'assistant', kind: 'error', text: t.assistant.errorTitle })
      }
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
      const key = `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 7)}`
      setUploading(prev => [...prev, { key, filename: file.name, progress: 0 }])
      try {
        const res = await atomicToolsApi.upload(file, percent =>
          setUploading(prev => prev.map(u => (u.key === key ? { ...u, progress: percent } : u))),
        )
        addAttachment({ file_id: res.file_id, filename: res.filename })
      } catch {
        // individual upload failures are surfaced when the plan can't find the file
      } finally {
        setUploading(prev => prev.filter(u => u.key !== key))
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const executeMutation = useMutation({
    mutationFn: (vars: { plan: AssistantPlan; fileIds: string[] }) =>
      assistantApi.execute(vars.plan, vars.fileIds, conversationId),
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

  const liveStatus = runQuery.data?.status
  const liveMessage =
    liveStatus === 'running'
      ? t.assistant.running
      : liveStatus === 'completed'
        ? t.assistant.doneTitle
        : liveStatus === 'failed'
          ? t.assistant.errorTitle
          : ''

  const mascotState: MascotState = planMutation.isPending
    ? 'thinking'
    : liveStatus === 'running'
      ? 'running'
      : liveStatus === 'completed'
        ? 'done'
        : 'idle'

  const categories = [
    { key: 'subtitle' as const, label: t.assistant.categories.subtitle, items: t.assistant.examplesByCategory.subtitle },
    { key: 'dubbing' as const, label: t.assistant.categories.dubbing, items: t.assistant.examplesByCategory.dubbing },
    { key: 'audio' as const, label: t.assistant.categories.audio, items: t.assistant.examplesByCategory.audio },
    { key: 'video' as const, label: t.assistant.categories.video, items: t.assistant.examplesByCategory.video },
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

          <div className="sr-only" role="status" aria-live="polite">
            {liveMessage}
          </div>

          {/* Messages */}
          <div className="relative flex-1 overflow-hidden">
            <div
              ref={scrollRef}
              onScroll={handleScroll}
              className="h-full space-y-3 overflow-y-auto bg-[#f7f9fc] px-3 py-3"
            >
              {keyMissing && (
                <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-amber-800">
                  <AlertCircle size={16} className="mt-0.5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-semibold">{t.assistant.needKeyTitle}</div>
                    <div className="mt-0.5 text-[12px] text-amber-700">{t.assistant.needKeyDesc}</div>
                    <Link
                      to="/settings"
                      onClick={close}
                      className="mt-1.5 inline-flex items-center gap-1 rounded-lg bg-amber-500 px-2.5 py-1 text-[12px] font-medium text-white transition-colors hover:bg-amber-600"
                    >
                      <Settings size={12} /> {t.assistant.goSettings}
                    </Link>
                  </div>
                </div>
              )}

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
                    <div className="space-y-2.5">
                      {categories.map(category => (
                        <div key={category.key}>
                          <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wide text-[#b0b7c3]">
                            {category.label}
                          </div>
                          <div className="flex flex-col gap-1.5">
                            {category.items.map(example => (
                              <button
                                key={example}
                                type="button"
                                disabled={keyMissing}
                                onClick={() => handleSend(example)}
                                className="rounded-xl border border-[#e4e9f0] bg-white px-3 py-2 text-left text-[13px] text-[#374151] transition-colors hover:border-[#3b5bdb]/50 hover:bg-[#f0f3ff] disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {example}
                              </button>
                            ))}
                          </div>
                        </div>
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
                  orientation={expanded ? 'horizontal' : 'vertical'}
                  onRun={() => handleRun(msg)}
                  onCancel={handleCancel}
                  onEditPlan={plan => updateMessage(msg.id, { plan })}
                  onAnswer={answer => handleSend(answer)}
                  onAttach={() => fileInputRef.current?.click()}
                  isExecuting={executeMutation.isPending}
                />
              ))}

              {planMutation.isPending && (
                <div className="flex items-center gap-2 px-1 text-[13px] text-[#6b7280]">
                  <Loader2 size={14} className="animate-spin" /> {t.assistant.planning}
                </div>
              )}
            </div>

            {showScrollButton && (
              <button
                type="button"
                onClick={scrollToBottom}
                aria-label={t.assistant.scrollToBottom}
                title={t.assistant.scrollToBottom}
                className="absolute bottom-3 right-3 flex h-8 w-8 items-center justify-center rounded-full border border-[#e4e9f0] bg-white text-[#6b7280] shadow-md transition-colors hover:bg-[#f3f4f6]"
              >
                <ChevronDown size={16} />
              </button>
            )}
          </div>

          {/* Attachments */}
          {(attachments.length > 0 || uploading.length > 0) && (
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
              {uploading.map(item => (
                <span
                  key={item.key}
                  className="inline-flex max-w-[180px] items-center gap-1 rounded-full bg-[#f3f4f6] px-2 py-0.5 text-[11px] text-[#6b7280]"
                >
                  <Loader2 size={11} className="animate-spin" />
                  <span className="truncate" title={item.filename}>{item.filename}</span>
                  <span className="tabular-nums">{Math.round(item.progress)}%</span>
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
                disabled={keyMissing}
                placeholder={keyMissing ? t.assistant.needKeyDesc : t.assistant.inputPlaceholder}
                className="max-h-32 min-h-[52px] flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm leading-relaxed text-[#374151] focus:outline-none disabled:cursor-not-allowed"
              />
              <button
                type="button"
                onClick={() => handleSend(input)}
                disabled={!input.trim() || planMutation.isPending || keyMissing}
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
  orientation: 'horizontal' | 'vertical'
  onRun: () => void
  onCancel: () => void
  onEditPlan: (plan: AssistantPlan) => void
  onAnswer: (answer: string) => void
  onAttach: () => void
  isExecuting: boolean
}

function MessageBubble({
  message,
  runState,
  orientation,
  onRun,
  onCancel,
  onEditPlan,
  onAnswer,
  onAttach,
  isExecuting,
}: MessageBubbleProps) {
  const { t } = useI18n()
  const time = formatTime(message.createdAt)

  if (message.role === 'user') {
    return (
      <div className="flex flex-col items-end">
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
        <span className="mt-0.5 pr-1 text-[10px] text-[#b0b7c3]">{time}</span>
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

  if (message.kind === 'clarification') {
    return (
      <div className="flex gap-2">
        <RobotMascot state="thinking" size={26} className="mt-1 shrink-0" />
        <div className="min-w-0 flex-1 space-y-2 rounded-2xl rounded-tl-sm bg-white px-3 py-2.5 shadow-sm">
          <div className="flex items-center gap-1 text-[11px] font-medium text-[#9ca3af]">
            <Sparkles size={12} /> {t.assistant.clarifyHint}
          </div>
          <p className="text-sm text-[#374151]">{message.clarification?.question ?? message.text}</p>
          {message.clarification?.options && message.clarification.options.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {message.clarification.options.map(option => (
                <button
                  key={option}
                  type="button"
                  disabled={message.answered}
                  onClick={() => onAnswer(option)}
                  className="rounded-full border border-[#3b5bdb]/40 bg-[#f0f3ff] px-3 py-1 text-[12px] font-medium text-[#3b5bdb] transition-colors hover:bg-[#e3e9ff] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {option}
                </button>
              ))}
            </div>
          )}
          <span className="block text-[10px] text-[#b0b7c3]">{time}</span>
        </div>
      </div>
    )
  }

  // plan message
  const status = runState?.status
  const started = message.runId != null
  const mascot: MascotState = status === 'completed' ? 'done' : status === 'running' ? 'running' : 'idle'
  const artifacts = runState?.steps.flatMap(s => s.artifacts) ?? []
  // Needs an upload only when the plan references a file beyond the available pool
  // (a follow-up that binds to a prior run's output is already satisfied).
  const needsUpload =
    !started && message.plan != null && maxUploadIndex(message.plan) >= (message.fileIds?.length ?? 0)

  return (
    <div className="flex gap-2">
      <RobotMascot state={mascot} size={26} className="mt-1 shrink-0" />
      <div className="min-w-0 flex-1 space-y-2 rounded-2xl rounded-tl-sm bg-white px-3 py-2.5 shadow-sm">
        {message.text && <p className="text-sm text-[#374151]">{message.text}</p>}
        {!started && <p className="text-[12px] text-[#9ca3af]">{t.assistant.planIntro}</p>}

        {message.plan && (
          <div className={orientation === 'horizontal' ? 'overflow-x-auto' : ''}>
            <CallChainDiagram
              plan={message.plan}
              runState={runState}
              orientation={orientation}
              editable={!started}
              onChange={onEditPlan}
            />
          </div>
        )}

        {/* Action bar */}
        {!started && !needsUpload && (
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

        {needsUpload && (
          <button
            type="button"
            onClick={onAttach}
            className="flex w-full items-center gap-2 rounded-lg border border-dashed border-[#f0b429]/60 bg-[#fffbeb] px-3 py-2 text-left text-[12px] text-[#92400e] transition-colors hover:bg-[#fff7d6]"
          >
            <Upload size={14} className="shrink-0" />
            {t.assistant.needUpload}
          </button>
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
            <p className="text-[12px] font-medium text-emerald-700">
              <span className="assistant-celebrate">🎉</span> {t.assistant.doneTitle}
            </p>
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

        <span className="block text-[10px] text-[#b0b7c3]">{time}</span>
      </div>
    </div>
  )
}
