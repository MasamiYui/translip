import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookUser, PlusCircle, Search, Trash2, Pencil, X } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { worksApi } from '../api/works'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { WorksSidebar, type WorkSelection } from '../components/character-library/WorksSidebar'
import { WorkEditorDrawer } from '../components/character-library/WorkEditorDrawer'
import { useI18n } from '../i18n/useI18n'
import type { GlobalPersona, GlobalPersonasListResponse, Work } from '../types'

const EMPTY_FORM: PersonaFormState = {
  id: '',
  name: '',
  actor_name: '',
  role: '',
  gender: '',
  age_hint: '',
  avatar_emoji: '',
  color: '',
  aliases: '',
  tags: '',
  tts_voice_id: '',
  note: '',
}

interface PersonaFormState {
  id: string
  name: string
  actor_name: string
  role: string
  gender: string
  age_hint: string
  avatar_emoji: string
  color: string
  aliases: string
  tags: string
  tts_voice_id: string
  note: string
}

function toFormState(persona: GlobalPersona): PersonaFormState {
  return {
    id: persona.id ?? '',
    name: persona.name ?? '',
    actor_name: persona.actor_name ?? '',
    role: persona.role ?? '',
    gender: persona.gender ?? '',
    age_hint: persona.age_hint ?? '',
    avatar_emoji: persona.avatar_emoji ?? '',
    color: persona.color ?? '',
    aliases: (persona.aliases ?? []).join(', '),
    tags: (persona.tags ?? []).join(', '),
    tts_voice_id: persona.tts_voice_id ?? '',
    note: persona.note ?? '',
  }
}

function splitCsv(value: string): string[] {
  return value
    .split(/[,，]/)
    .map(s => s.trim())
    .filter(Boolean)
}

function toPersonaPayload(form: PersonaFormState, workId?: string | null): GlobalPersona {
  const payload: GlobalPersona = {
    id: form.id || `persona_${Date.now().toString(36)}`,
    name: form.name.trim(),
  }
  if (form.actor_name.trim()) payload.actor_name = form.actor_name.trim()
  if (form.role.trim()) payload.role = form.role.trim()
  if (form.gender.trim()) payload.gender = form.gender.trim()
  if (form.age_hint.trim()) payload.age_hint = form.age_hint.trim()
  if (form.avatar_emoji.trim()) payload.avatar_emoji = form.avatar_emoji.trim()
  if (form.color.trim()) payload.color = form.color.trim()
  const aliases = splitCsv(form.aliases)
  if (aliases.length) payload.aliases = aliases
  const tags = splitCsv(form.tags)
  if (tags.length) payload.tags = tags
  if (form.tts_voice_id.trim()) payload.tts_voice_id = form.tts_voice_id.trim()
  if (form.note.trim()) payload.note = form.note.trim()
  if (workId) payload.work_id = workId
  return payload
}

function formatUpdatedAt(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback
  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return date.toLocaleString()
  } catch {
    return value
  }
}

export function CharacterLibraryPage() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [form, setForm] = useState<PersonaFormState>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [flash, setFlash] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [selectedWork, setSelectedWork] = useState<WorkSelection>('__all__')
  const [workEditorOpen, setWorkEditorOpen] = useState(false)
  const [editingWork, setEditingWork] = useState<Work | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['global-personas'],
    queryFn: tasksApi.listGlobalPersonas,
  })

  const { data: worksData, isLoading: isWorksLoading } = useQuery({
    queryKey: ['works'],
    queryFn: () => worksApi.list(),
  })

  const personas = useMemo(() => data?.personas ?? [], [data])
  const storagePath = data?.path ?? ''
  const works: Work[] = useMemo(() => worksData?.works ?? [], [worksData])
  const unassignedCount = useMemo(
    () => worksData?.unassigned_count ?? personas.filter(p => !p.work_id).length,
    [worksData, personas],
  )

  const upsertMutation = useMutation({
    mutationFn: (persona: GlobalPersona) =>
      tasksApi.importGlobalPersonas({ personas: [persona], mode: 'merge' }),
    onSuccess: response => {
      queryClient.setQueryData<GlobalPersonasListResponse>(
        ['global-personas'],
        prev => (prev ? { ...prev, personas: response.personas, updated_at: new Date().toISOString() } : prev),
      )
      queryClient.invalidateQueries({ queryKey: ['global-personas'] })
      queryClient.invalidateQueries({ queryKey: ['works'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (personaId: string) => tasksApi.deleteGlobalPersona(personaId),
    onSuccess: response => {
      queryClient.setQueryData<GlobalPersonasListResponse>(
        ['global-personas'],
        prev => (prev ? { ...prev, personas: response.personas, updated_at: new Date().toISOString() } : prev),
      )
      queryClient.invalidateQueries({ queryKey: ['global-personas'] })
      queryClient.invalidateQueries({ queryKey: ['works'] })
    },
  })

  const deleteWorkMutation = useMutation({
    mutationFn: (workId: string) => worksApi.remove(workId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['works'] })
      queryClient.invalidateQueries({ queryKey: ['global-personas'] })
    },
  })

  useEffect(() => {
    if (!flash) return
    const timer = window.setTimeout(() => setFlash(null), 3500)
    return () => window.clearTimeout(timer)
  }, [flash])

  const scopedPersonas = useMemo(() => {
    if (selectedWork === '__all__') return personas
    if (selectedWork === '__unassigned__') return personas.filter(p => !p.work_id)
    return personas.filter(p => p.work_id === selectedWork)
  }, [personas, selectedWork])

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase()
    if (!kw) return scopedPersonas
    return scopedPersonas.filter(p => {
      const name = (p.name ?? '').toLowerCase()
      const actor = (p.actor_name ?? '').toLowerCase()
      const role = (p.role ?? '').toLowerCase()
      const aliases = (p.aliases ?? []).join(' ').toLowerCase()
      const tags = (p.tags ?? []).join(' ').toLowerCase()
      return (
        name.includes(kw) ||
        actor.includes(kw) ||
        role.includes(kw) ||
        aliases.includes(kw) ||
        tags.includes(kw)
      )
    })
  }, [scopedPersonas, search])

  function openCreate() {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setEditorOpen(true)
  }

  function openEdit(persona: GlobalPersona) {
    setForm(toFormState(persona))
    setEditingId(persona.id)
    setEditorOpen(true)
  }

  function closeEditor() {
    setEditorOpen(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!form.name.trim()) return
    try {
      const targetWorkId =
        selectedWork === '__all__' || selectedWork === '__unassigned__'
          ? null
          : selectedWork
      const payload = toPersonaPayload(form, editingId ? undefined : targetWorkId)
      await upsertMutation.mutateAsync(payload)
      const isCreate = !editingId
      setFlash({
        type: 'success',
        text: isCreate
          ? t.characterLibrary.flash.created(payload.name)
          : t.characterLibrary.flash.updated(payload.name),
      })
      closeEditor()
    } catch (err) {
      console.error(err)
      setFlash({ type: 'error', text: t.characterLibrary.flash.saveFailed })
    }
  }

  async function handleDelete(persona: GlobalPersona) {
    if (!window.confirm(t.characterLibrary.deleteConfirm(persona.name))) return
    try {
      await deleteMutation.mutateAsync(persona.id)
      setFlash({
        type: 'success',
        text: t.characterLibrary.flash.deleted(persona.name),
      })
    } catch (err) {
      console.error(err)
      setFlash({ type: 'error', text: t.characterLibrary.flash.deleteFailed })
    }
  }

  function openCreateWork() {
    setEditingWork(null)
    setWorkEditorOpen(true)
  }

  function openEditWork(work: Work) {
    setEditingWork(work)
    setWorkEditorOpen(true)
  }

  async function handleDeleteWork(work: Work) {
    const count = work.persona_count ?? 0
    if (!window.confirm(t.characterLibrary.works.deleteConfirm(work.title, count))) return
    try {
      await deleteWorkMutation.mutateAsync(work.id)
      setFlash({
        type: 'success',
        text: t.characterLibrary.works.flash.deleted(work.title),
      })
      if (selectedWork === work.id) setSelectedWork('__all__')
    } catch (err) {
      console.error(err)
      setFlash({ type: 'error', text: t.characterLibrary.works.flash.deleteFailed })
    }
  }

  function handleWorkSaved(work: Work, isCreate: boolean) {
    setFlash({
      type: 'success',
      text: isCreate
        ? t.characterLibrary.works.flash.created(work.title)
        : t.characterLibrary.works.flash.updated(work.title),
    })
    setWorkEditorOpen(false)
    setEditingWork(null)
    if (isCreate) setSelectedWork(work.id)
  }

  const noKeyword = search.trim().length === 0

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <BookUser size={18} className="text-[#3b5bdb]" />
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            {t.characterLibrary.title}
          </h1>
        </div>
        <span
          data-testid="character-library-count"
          className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600"
        >
          {t.characterLibrary.countHint(personas.length)}
        </span>
        <p className="basis-full text-xs text-slate-500">{t.characterLibrary.subtitle}</p>
        {storagePath && (
          <p
            data-testid="character-library-storage"
            className="basis-full text-[11px] text-slate-400"
          >
            {t.characterLibrary.storageHint(storagePath)}
          </p>
        )}
      </div>

      {flash && (
        <div
          data-testid={`character-library-flash-${flash.type}`}
          className={
            flash.type === 'success'
              ? 'mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700'
              : 'mb-4 rounded-md border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700'
          }
        >
          {flash.text}
        </div>
      )}

      <div className="flex gap-4">
        <WorksSidebar
          works={works}
          selected={selectedWork}
          onSelect={setSelectedWork}
          onCreate={openCreateWork}
          onEdit={openEditWork}
          onDelete={handleDeleteWork}
          totalPersonas={personas.length}
          unassignedCount={unassignedCount}
          isLoading={isWorksLoading}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                data-testid="character-library-search"
                type="search"
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder={t.characterLibrary.placeholders.search}
                className="h-9 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
              />
            </div>
            <button
              type="button"
              data-testid="character-library-create"
              onClick={openCreate}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-[#3b5bdb] px-3 text-sm font-medium text-white transition hover:bg-[#3451c5]"
            >
              <PlusCircle size={14} />
              {t.characterLibrary.actions.create}
            </button>
          </div>

          <div
            data-testid="character-library-list"
            className="overflow-hidden rounded-xl border border-slate-200 bg-white"
          >
            {isLoading ? (
              <div className="px-6 py-10 text-center text-sm text-slate-400">
                Loading…
              </div>
            ) : filtered.length === 0 ? (
              noKeyword ? (
                <div
                  data-testid="character-library-page-empty"
                  className="flex flex-col items-center gap-3 px-6 py-12 text-center"
                >
                  <BookUser size={28} className="text-slate-300" />
                  <div className="text-base font-medium text-slate-700">
                    {t.characterLibrary.empty.title}
                  </div>
                  <div className="max-w-sm text-sm text-slate-500">
                    {t.characterLibrary.empty.description}
                  </div>
                  <button
                    type="button"
                    data-testid="character-library-empty-cta"
                    onClick={openCreate}
                    className="mt-2 inline-flex h-9 items-center gap-2 rounded-md bg-[#3b5bdb] px-3 text-sm font-medium text-white transition hover:bg-[#3451c5]"
                  >
                    <PlusCircle size={14} />
                    {t.characterLibrary.empty.cta}
                  </button>
                </div>
              ) : (
                <div
                  data-testid="character-library-empty-filtered"
                  className="px-6 py-12 text-center text-sm text-slate-400"
                >
                  {t.characterLibrary.emptyFiltered}
                </div>
              )
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-2 text-left font-medium">
                      {t.characterLibrary.columns.avatar}
                    </th>
                    <th className="px-4 py-2 text-left font-medium">
                      {t.characterLibrary.columns.name}
                    </th>
                    <th className="px-4 py-2 text-left font-medium">
                      {t.characterLibrary.columns.actor}
                    </th>
                    <th className="px-4 py-2 text-left font-medium">
                      {t.characterLibrary.columns.role}
                    </th>
                    <th className="px-4 py-2 text-left font-medium">
                      {t.characterLibrary.columns.gender}
                    </th>
                    <th className="px-4 py-2 text-left font-medium">
                      {t.characterLibrary.columns.tags}
                    </th>
                    <th className="px-4 py-2 text-left font-medium">
                      {t.characterLibrary.columns.updatedAt}
                    </th>
                    <th className="px-4 py-2 text-right font-medium">
                      {t.characterLibrary.columns.actions}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(persona => (
                    <tr
                      key={persona.id}
                      data-testid={`character-row-${persona.id}`}
                      className="border-t border-slate-100 text-slate-700"
                    >
                      <td className="px-4 py-3">
                        <span
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-lg"
                          style={{
                            backgroundColor: persona.color ? `${persona.color}22` : '#f1f5f9',
                            color: persona.color ?? '#334155',
                          }}
                        >
                          {persona.avatar_emoji || '👤'}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-800">
                        <div>{persona.name}</div>
                        {persona.aliases && persona.aliases.length > 0 && (
                          <div className="mt-0.5 text-[11px] text-slate-400">
                            {persona.aliases.join(' · ')}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {persona.actor_name || '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{persona.role || '—'}</td>
                      <td className="px-4 py-3 text-slate-600">
                        {persona.gender
                          ? (t.characterLibrary.gender as Record<string, string>)[persona.gender] ??
                            persona.gender
                          : '—'}
                      </td>
                      <td className="px-4 py-3">
                        {persona.tags && persona.tags.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {persona.tags.map(tag => (
                              <span
                                key={tag}
                                className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-[12px] text-slate-500">
                        {formatUpdatedAt(persona.updated_at, '—')}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-2">
                          <button
                            type="button"
                            data-testid={`character-edit-${persona.id}`}
                            onClick={() => openEdit(persona)}
                            className="inline-flex h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
                          >
                            <Pencil size={12} />
                            {t.characterLibrary.actions.edit}
                          </button>
                          <button
                            type="button"
                            data-testid={`character-delete-${persona.id}`}
                            onClick={() => handleDelete(persona)}
                            className="inline-flex h-8 items-center gap-1 rounded-md border border-rose-200 bg-white px-2.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50"
                          >
                            <Trash2 size={12} />
                            {t.characterLibrary.actions.delete}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {editorOpen && (
        <div
          data-testid="character-editor-backdrop"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
          onClick={closeEditor}
        >
          <form
            data-testid="character-editor"
            onClick={event => event.stopPropagation()}
            onSubmit={handleSubmit}
            className="w-full max-w-lg overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
              <h2 className="text-base font-semibold text-slate-800">
                {editingId
                  ? t.characterLibrary.drawer.editTitle
                  : t.characterLibrary.drawer.createTitle}
              </h2>
              <button
                type="button"
                data-testid="character-editor-close"
                onClick={closeEditor}
                className="rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              >
                <X size={16} />
              </button>
            </div>
            <div className="grid max-h-[60vh] gap-4 overflow-y-auto px-5 py-4 sm:grid-cols-2">
              <LabeledInput
                label={t.characterLibrary.fields.name}
                placeholder={t.characterLibrary.placeholders.name}
                value={form.name}
                onChange={v => setForm(f => ({ ...f, name: v }))}
                dataTestId="character-field-name"
                required
              />
              <LabeledInput
                label={t.characterLibrary.fields.actor}
                placeholder={t.characterLibrary.placeholders.actor}
                value={form.actor_name}
                onChange={v => setForm(f => ({ ...f, actor_name: v }))}
                dataTestId="character-field-actor"
              />
              <LabeledInput
                label={t.characterLibrary.fields.role}
                placeholder={t.characterLibrary.placeholders.role}
                value={form.role}
                onChange={v => setForm(f => ({ ...f, role: v }))}
                dataTestId="character-field-role"
              />
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-slate-600">
                  {t.characterLibrary.fields.gender}
                </label>
                <select
                  data-testid="character-field-gender"
                  value={form.gender}
                  onChange={event => setForm(f => ({ ...f, gender: event.target.value }))}
                  className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
                >
                  <option value="">{t.characterLibrary.gender.none}</option>
                  <option value="female">{t.characterLibrary.gender.female}</option>
                  <option value="male">{t.characterLibrary.gender.male}</option>
                  <option value="other">{t.characterLibrary.gender.other}</option>
                </select>
              </div>
              <LabeledInput
                label={t.characterLibrary.fields.ageHint}
                placeholder={t.characterLibrary.placeholders.ageHint}
                value={form.age_hint}
                onChange={v => setForm(f => ({ ...f, age_hint: v }))}
                dataTestId="character-field-age"
              />
              <LabeledInput
                label={t.characterLibrary.fields.avatarEmoji}
                placeholder={t.characterLibrary.placeholders.avatarEmoji}
                value={form.avatar_emoji}
                onChange={v => setForm(f => ({ ...f, avatar_emoji: v }))}
                dataTestId="character-field-avatar"
              />
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-slate-600">
                  {t.characterLibrary.fields.color}
                </label>
                <input
                  data-testid="character-field-color"
                  type="color"
                  value={form.color || '#94a3b8'}
                  onChange={event => setForm(f => ({ ...f, color: event.target.value }))}
                  className="h-9 w-full cursor-pointer rounded-md border border-slate-200 bg-white p-1"
                />
              </div>
              <LabeledInput
                label={t.characterLibrary.fields.ttsVoiceId}
                placeholder=""
                value={form.tts_voice_id}
                onChange={v => setForm(f => ({ ...f, tts_voice_id: v }))}
                dataTestId="character-field-voice"
              />
              <LabeledInput
                label={t.characterLibrary.fields.aliases}
                placeholder={t.characterLibrary.placeholders.aliases}
                value={form.aliases}
                onChange={v => setForm(f => ({ ...f, aliases: v }))}
                dataTestId="character-field-aliases"
                className="sm:col-span-2"
              />
              <LabeledInput
                label={t.characterLibrary.fields.tags}
                placeholder={t.characterLibrary.placeholders.tags}
                value={form.tags}
                onChange={v => setForm(f => ({ ...f, tags: v }))}
                dataTestId="character-field-tags"
                className="sm:col-span-2"
              />
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <label className="text-xs font-medium text-slate-600">
                  {t.characterLibrary.fields.note}
                </label>
                <textarea
                  data-testid="character-field-note"
                  rows={3}
                  value={form.note}
                  onChange={event => setForm(f => ({ ...f, note: event.target.value }))}
                  placeholder={t.characterLibrary.placeholders.note}
                  className="rounded-md border border-slate-200 bg-white px-2.5 py-2 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
                />
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">
              <button
                type="button"
                data-testid="character-editor-cancel"
                onClick={closeEditor}
                className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
              >
                {t.characterLibrary.actions.cancel}
              </button>
              <button
                type="submit"
                data-testid="character-editor-save"
                disabled={!form.name.trim() || upsertMutation.isPending}
                className="h-9 rounded-md bg-[#3b5bdb] px-3 text-sm font-medium text-white transition hover:bg-[#3451c5] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t.characterLibrary.actions.save}
              </button>
            </div>
          </form>
        </div>
      )}

      <WorkEditorDrawer
        open={workEditorOpen}
        work={editingWork}
        onClose={() => {
          setWorkEditorOpen(false)
          setEditingWork(null)
        }}
        onSaved={handleWorkSaved}
        onError={text => setFlash({ type: 'error', text })}
        onTypeAdded={key =>
          setFlash({
            type: 'success',
            text: t.characterLibrary.works.flash.typeAdded(key),
          })
        }
      />
    </PageContainer>
  )
}

interface LabeledInputProps {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  dataTestId?: string
  className?: string
  required?: boolean
}

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
  dataTestId,
  className = '',
  required = false,
}: LabeledInputProps) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <label className="text-xs font-medium text-slate-600">{label}</label>
      <input
        data-testid={dataTestId}
        type="text"
        value={value}
        required={required}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-9 rounded-md border border-slate-200 bg-white px-2.5 text-sm outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
      />
    </div>
  )
}