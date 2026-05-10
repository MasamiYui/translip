import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import { worksApi, type CreateWorkPayload } from '../../api/works'
import type { Work, WorkType } from '../../types'
import { ColorSwatchPicker } from './pickers/ColorSwatchPicker'
import { CoverIconPicker } from './pickers/CoverIconPicker'
import { ChipInput } from './ChipInput'

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
  aliases: string[]
  cover_emoji: string
  color: string
  note: string
  tags: string[]
}

const EMPTY_FORM: WorkFormState = {
  title: '',
  type: 'tv',
  year: '',
  aliases: [],
  cover_emoji: '',
  color: '',
  note: '',
  tags: [],
}

function toFormState(work: Work): WorkFormState {
  return {
    title: work.title ?? '',
    type: work.type ?? 'tv',
    year: work.year != null ? String(work.year) : '',
    aliases: [...(work.aliases ?? [])],
    cover_emoji: work.cover_emoji ?? '',
    color: work.color ?? '',
    note: work.note ?? '',
    tags: [...(work.tags ?? [])],
  }
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
  if (form.aliases.length) payload.aliases = [...form.aliases]
  if (form.cover_emoji.trim()) payload.cover_emoji = form.cover_emoji.trim()
  if (form.color.trim()) payload.color = form.color.trim()
  if (form.note.trim()) payload.note = form.note.trim()
  if (form.tags.length) payload.tags = [...form.tags]
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
        className="w-full max-w-lg overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_8px_24px_rgba(0,0,0,.12)]"
      >
        <div className="flex items-center justify-between border-b border-[#e5e7eb] px-5 py-3">
          <h2 className="text-base font-semibold text-slate-800">
            {isEditing
              ? t.characterLibrary.works.drawer.editTitle
              : t.characterLibrary.works.drawer.createTitle}
          </h2>
          <button
            type="button"
            data-testid="work-editor-close"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition-all hover:bg-[#f3f4f6] hover:text-[#374151]"
          >
            <X size={16} />
          </button>
        </div>

        <div className="grid max-h-[60vh] gap-4 overflow-y-auto px-5 py-4 sm:grid-cols-2">
          <div className="flex flex-col sm:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.title}
            </label>
            <input
              data-testid="work-field-title"
              type="text"
              required
              value={form.title}
              onChange={event => setForm(f => ({ ...f, title: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.title}
              className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
            />
          </div>

          <div className="flex flex-col">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.type}
            </label>
            <select
              data-testid="work-field-type"
              value={form.type}
              onChange={event => handleTypeChange(event.target.value)}
              className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
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

          <div className="flex flex-col">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.year}
            </label>
            <input
              data-testid="work-field-year"
              type="text"
              inputMode="numeric"
              value={form.year}
              onChange={event => setForm(f => ({ ...f, year: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.year}
              className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
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
                className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
              />
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  data-testid="work-type-custom-label-zh"
                  type="text"
                  value={customLabelZh}
                  onChange={event => setCustomLabelZh(event.target.value)}
                  placeholder={t.characterLibrary.works.customType.labelZh}
                  className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
                />
                <input
                  data-testid="work-type-custom-label-en"
                  type="text"
                  value={customLabelEn}
                  onChange={event => setCustomLabelEn(event.target.value)}
                  placeholder={t.characterLibrary.works.customType.labelEn}
                  className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
                />
              </div>
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  data-testid="work-type-custom-cancel"
                  onClick={() => setCustomOpen(false)}
                  className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-1 text-[11px] font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
                >
                  {t.characterLibrary.works.customType.cancel}
                </button>
                <button
                  type="button"
                  data-testid="work-type-custom-save"
                  disabled={!customKey.trim() || addTypeMutation.isPending}
                  onClick={() => addTypeMutation.mutate()}
                  className="rounded-lg bg-[#3b5bdb] px-3 py-1 text-[11px] font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t.characterLibrary.works.customType.save}
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-col">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.coverEmoji}
            </label>
            <CoverIconPicker
              value={form.cover_emoji}
              onChange={v => setForm(f => ({ ...f, cover_emoji: v }))}
              color={form.color}
              dataTestId="work-field-cover-emoji"
            />
          </div>

          <div className="flex flex-col">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.color}
            </label>
            <ColorSwatchPicker
              value={form.color}
              onChange={v => setForm(f => ({ ...f, color: v }))}
              dataTestId="work-field-color"
            />
          </div>

          <div className="flex flex-col sm:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.aliases}
            </label>
            <ChipInput
              dataTestId="work-field-aliases"
              value={form.aliases}
              onChange={next => setForm(f => ({ ...f, aliases: next }))}
              placeholder={t.characterLibrary.works.placeholders.aliases}
              ariaLabel={t.characterLibrary.works.fields.aliases}
              removeLabel={t.characterLibrary.works.fields.aliases}
            />
          </div>

          <div className="flex flex-col sm:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.tags}
            </label>
            <ChipInput
              dataTestId="work-field-tags"
              value={form.tags}
              onChange={next => setForm(f => ({ ...f, tags: next }))}
              ariaLabel={t.characterLibrary.works.fields.tags}
              removeLabel={t.characterLibrary.works.fields.tags}
            />
          </div>

          <div className="flex flex-col sm:col-span-2">
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.characterLibrary.works.fields.note}
            </label>
            <textarea
              data-testid="work-field-note"
              rows={3}
              value={form.note}
              onChange={event => setForm(f => ({ ...f, note: event.target.value }))}
              placeholder={t.characterLibrary.works.placeholders.note}
              className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#e5e7eb] px-5 py-3">
          <button
            type="button"
            data-testid="work-editor-cancel"
            onClick={onClose}
            className="rounded-lg border border-[#e5e7eb] bg-white px-4 py-2 text-sm font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
          >
            {t.characterLibrary.works.actions.cancel}
          </button>
          <button
            type="submit"
            data-testid="work-editor-save"
            disabled={!form.title.trim() || saveMutation.isPending}
            className="rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t.characterLibrary.works.actions.save}
          </button>
        </div>
      </form>
    </div>
  )
}
