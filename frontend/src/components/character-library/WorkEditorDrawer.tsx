import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import { worksApi, type CreateWorkPayload } from '../../api/works'
import type { Work, WorkType } from '../../types'

export interface WorkEditorDrawerProps {
  open: boolean
  work: Work | null
  onClose: () => void
  onSaved: (work: Work, isCreate: boolean) => void
  onError?: (message: string) => void
  onTypeAdded?: (key: string) => void
}

interface WorkFormState {
  title: string
  type: string
  year: string
  aliases: string
  cover_emoji: string
  color: string
  note: string
  tags: string
}

const EMPTY_FORM: WorkFormState = {
  title: '',
  type: 'tv',
  year: '',
  aliases: '',
  cover_emoji: '',
  color: '',
  note: '',
  tags: '',
}

function toFormState(work: Work): WorkFormState {
  return {
    title: work.title ?? '',
    type: work.type ?? 'tv',
    year: work.year != null ? String(work.year) : '',
    aliases: (work.aliases ?? []).join(', '),
    cover_emoji: work.cover_emoji ?? '',
    color: work.color ?? '',
    note: work.note ?? '',
    tags: (work.tags ?? []).join(', '),
  }
}

function splitCsv(value: string): string[] {
  return value
    .split(/[,，]/)
    .map(s => s.trim())
    .filter(Boolean)
}

function toPayload(form: WorkFormState): CreateWorkPayload {
  const payload: CreateWorkPayload = {
    title: form.title.trim(),
    type: form.type.trim() || 'tv',
  }
  const year = form.year.trim()
  if (year) {
    const n = Number.parseInt(year, 10)
    if (Number.isFinite(n)) payload.year = n
  }
  const aliases = splitCsv(form.aliases)
  if (aliases.length) payload.aliases = aliases
  if (form.cover_emoji.trim()) payload.cover_emoji = form.cover_emoji.trim()
  if (form.color.trim()) payload.color = form.color.trim()
  if (form.note.trim()) payload.note = form.note.trim()
  const tags = splitCsv(form.tags)
  if (tags.length) payload.tags = tags
  return payload
}

const ADD_CUSTOM_SENTINEL = '__add_custom__'

export function WorkEditorDrawer({
  open,
  work,
  onClose,
  onSaved,
  onError,
  onTypeAdded,
}: WorkEditorDrawerProps) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<WorkFormState>(EMPTY_FORM)
  const [customOpen, setCustomOpen] = useState(false)
  const [customKey, setCustomKey] = useState('')
  const [customLabelZh, setCustomLabelZh] = useState('')
  const [customLabelEn, setCustomLabelEn] = useState('')

  const isEditing = !!work

  const { data: typesData } = useQuery({
    queryKey: ['work-types'],
    queryFn: worksApi.listTypes,
    enabled: open,
  })
  const types: WorkType[] = useMemo(() => typesData?.types ?? [], [typesData])

  // Derive form from props using the "reset when key changes" pattern.
  const resetKey = open ? `${work?.id ?? 'new'}` : '__closed__'
  const [lastResetKey, setLastResetKey] = useState<string>('__closed__')
  if (lastResetKey !== resetKey) {
    setLastResetKey(resetKey)
    if (open) {
      setForm(work ? toFormState(work) : EMPTY_FORM)
      setCustomOpen(false)
      setCustomKey('')
      setCustomLabelZh('')
      setCustomLabelEn('')
    }
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = toPayload(form)
      if (isEditing && work) {
        return worksApi.update(work.id, payload)
      }
      return worksApi.create(payload)
    },
    onSuccess: response => {
      queryClient.invalidateQueries({ queryKey: ['works'] })
      onSaved(response.work, !isEditing)
    },
    onError: (err: unknown) => {
      console.error(err)
      onError?.(t.characterLibrary.works.flash.saveFailed)
    },
  })

  const addTypeMutation = useMutation({
    mutationFn: () =>
      worksApi.addCustomType({
        key: customKey.trim(),
        label_zh: customLabelZh.trim() || customKey.trim(),
        label_en: customLabelEn.trim() || customKey.trim(),
      }),
    onSuccess: response => {
      queryClient.setQueryData(['work-types'], response)
      const newKey = customKey.trim()
      setForm(f => ({ ...f, type: newKey }))
      setCustomOpen(false)
      setCustomKey('')
      setCustomLabelZh('')
      setCustomLabelEn('')
      onTypeAdded?.(newKey)
    },
    onError: (err: unknown) => {
      console.error(err)
      onError?.(t.characterLibrary.works.flash.saveFailed)
    },
  })

  if (!open) return null

  function handleTypeChange(value: string) {
    if (value === ADD_CUSTOM_SENTINEL) {
      setCustomOpen(true)
      return
    }
    setForm(f => ({ ...f, type: value }))
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!form.title.trim()) return
    await saveMutation.mutateAsync()
  }

  return (
    <div
      data-testid="work-editor-backdrop"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <form
        data-testid="work-editor"
        onClick={event => event.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-lg overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="text-base font-semibold text-slate-800">
            {isEditing
              ? t.characterLibrary.works.drawer.editTitle
              : t.characterLibrary.works.drawer.createTitle}
          </h2>
          <button
            type="button"
            data-testid="work-editor-close"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={16} />
          </button>
        </div>

        <div className="grid max-h-[60vh] gap-4 overflow-y-auto px-5 py-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.title}
            </label>
            <input
              data-testid="work-field-title"
              type="text"
              required
              value={form.title}
              onChange={event => setForm(f => ({ ...f, title: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.title}
              className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.type}
            </label>
            <select
              data-testid="work-field-type"
              value={form.type}
              onChange={event => handleTypeChange(event.target.value)}
              className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
            >
              {types.map(wt => (
                <option key={wt.key} value={wt.key}>
                  {wt.label_zh} ({wt.key})
                </option>
              ))}
              <option value={ADD_CUSTOM_SENTINEL}>
                {t.characterLibrary.works.actions.addType}
              </option>
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.year}
            </label>
            <input
              data-testid="work-field-year"
              type="text"
              inputMode="numeric"
              value={form.year}
              onChange={event => setForm(f => ({ ...f, year: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.year}
              className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
            />
          </div>

          {customOpen && (
            <div
              data-testid="work-type-add-custom"
              className="flex flex-col gap-2 rounded-lg border border-dashed border-[#3b5bdb] bg-[#3b5bdb]/5 p-3 sm:col-span-2"
            >
              <div className="text-xs font-semibold text-[#3b5bdb]">
                {t.characterLibrary.works.customType.title}
              </div>
              <input
                data-testid="work-type-custom-key"
                type="text"
                value={customKey}
                onChange={event => setCustomKey(event.target.value)}
                placeholder={t.characterLibrary.works.customType.key}
                className="h-8 rounded-md border border-slate-200 bg-white px-2.5 text-xs outline-none focus:border-[#3b5bdb]"
              />
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  data-testid="work-type-custom-label-zh"
                  type="text"
                  value={customLabelZh}
                  onChange={event => setCustomLabelZh(event.target.value)}
                  placeholder={t.characterLibrary.works.customType.labelZh}
                  className="h-8 rounded-md border border-slate-200 bg-white px-2.5 text-xs outline-none focus:border-[#3b5bdb]"
                />
                <input
                  data-testid="work-type-custom-label-en"
                  type="text"
                  value={customLabelEn}
                  onChange={event => setCustomLabelEn(event.target.value)}
                  placeholder={t.characterLibrary.works.customType.labelEn}
                  className="h-8 rounded-md border border-slate-200 bg-white px-2.5 text-xs outline-none focus:border-[#3b5bdb]"
                />
              </div>
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  data-testid="work-type-custom-cancel"
                  onClick={() => setCustomOpen(false)}
                  className="h-7 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
                >
                  {t.characterLibrary.works.customType.cancel}
                </button>
                <button
                  type="button"
                  data-testid="work-type-custom-save"
                  disabled={!customKey.trim() || addTypeMutation.isPending}
                  onClick={() => addTypeMutation.mutate()}
                  className="h-7 rounded-md bg-[#3b5bdb] px-2 text-[11px] font-medium text-white hover:bg-[#3451c5] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t.characterLibrary.works.customType.save}
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.coverEmoji}
            </label>
            <input
              data-testid="work-field-cover-emoji"
              type="text"
              value={form.cover_emoji}
              onChange={event => setForm(f => ({ ...f, cover_emoji: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.coverEmoji}
              className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.color}
            </label>
            <input
              data-testid="work-field-color"
              type="color"
              value={form.color || '#94a3b8'}
              onChange={event => setForm(f => ({ ...f, color: event.target.value }))}
              className="h-9 w-full cursor-pointer rounded-md border border-slate-200 bg-white p-1"
            />
          </div>

          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.aliases}
            </label>
            <input
              data-testid="work-field-aliases"
              type="text"
              value={form.aliases}
              onChange={event => setForm(f => ({ ...f, aliases: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.aliases}
              className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
            />
          </div>

          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.tags}
            </label>
            <input
              data-testid="work-field-tags"
              type="text"
              value={form.tags}
              onChange={event => setForm(f => ({ ...f, tags: event.target.value }))}
              className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
            />
          </div>

          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <label className="text-xs font-medium text-slate-600">
              {t.characterLibrary.works.fields.note}
            </label>
            <textarea
              data-testid="work-field-note"
              rows={3}
              value={form.note}
              onChange={event => setForm(f => ({ ...f, note: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.note}
              className="rounded-md border border-slate-200 bg-white px-2.5 py-2 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">
          <button
            type="button"
            data-testid="work-editor-cancel"
            onClick={onClose}
            className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
          >
            {t.characterLibrary.works.actions.cancel}
          </button>
          <button
            type="submit"
            data-testid="work-editor-save"
            disabled={!form.title.trim() || saveMutation.isPending}
            className="h-9 rounded-md bg-[#3b5bdb] px-3 text-sm font-medium text-white transition hover:bg-[#3451c5] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t.characterLibrary.works.actions.save}
          </button>
        </div>
      </form>
    </div>
  )
}
