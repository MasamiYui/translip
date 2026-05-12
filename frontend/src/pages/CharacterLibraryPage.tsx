import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookUser, Mic2, PlusCircle, Search, Trash2, Pencil, X } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { worksApi } from '../api/works'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { WorksSidebar, type WorkSelection } from '../components/character-library/WorksSidebar'
import { WorkEditorDrawer } from '../components/character-library/WorkEditorDrawer'
import { ChipInput } from '../components/character-library/ChipInput'
import { AgeBandSelector } from '../components/character-library/pickers/AgeBandSelector'
import { ColorSwatchPicker } from '../components/character-library/pickers/ColorSwatchPicker'
import { EmojiAvatarPicker } from '../components/character-library/pickers/EmojiAvatarPicker'
import {
  DEFAULT_COLOR,
  firstGlyphOf,
  hexWithAlpha,
  normalizeHex,
  ROLE_PRESET_KEYS,
} from '../components/character-library/pickers/presets'
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
  avatar_url: '',
  color: '',
  aliases: [],
  tags: [],
  tts_voice_id: '',
  note: '',
  work_id: '',
}

interface PersonaFormState {
  id: string
  name: string
  actor_name: string
  role: string
  gender: string
  age_hint: string
  avatar_emoji: string
  avatar_url: string
  color: string
  aliases: string[]
  tags: string[]
  tts_voice_id: string
  note: string
  work_id: string
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
    avatar_url: persona.avatar_url ?? '',
    color: persona.color ?? '',
    aliases: [...(persona.aliases ?? [])],
    tags: [...(persona.tags ?? [])],
    tts_voice_id: persona.tts_voice_id ?? '',
    note: persona.note ?? '',
    work_id: persona.work_id ?? '',
  }
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
  if (form.avatar_url.trim()) payload.avatar_url = form.avatar_url.trim()
  if (form.color.trim()) payload.color = form.color.trim()
  if (form.aliases.length) payload.aliases = [...form.aliases]
  if (form.tags.length) payload.tags = [...form.tags]
  if (form.tts_voice_id.trim()) payload.tts_voice_id = form.tts_voice_id.trim()
  if (form.note.trim()) payload.note = form.note.trim()
  // work_id: use the form value if set, else fall back to explicit workId arg
  const resolvedWorkId = form.work_id.trim() || workId || null
  if (resolvedWorkId) payload.work_id = resolvedWorkId
  return payload
}

function PersonaAvatar({
  persona,
  resolvedColor,
}: {
  persona: Pick<GlobalPersona, 'id' | 'name' | 'avatar_emoji' | 'avatar_url'>
  resolvedColor: string
}) {
  const avatarUrl = (persona.avatar_url ?? '').trim()
  const [failedAvatarUrl, setFailedAvatarUrl] = useState<string | null>(null)

  if (avatarUrl && failedAvatarUrl !== avatarUrl) {
    return (
      <img
        data-testid={`character-avatar-image-${persona.id}`}
        src={avatarUrl}
        alt={persona.name || ''}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailedAvatarUrl(avatarUrl)}
        className="h-9 w-9 rounded-full object-cover ring-1 ring-slate-200"
      />
    )
  }

  const glyph = persona.avatar_emoji?.trim()
    ? persona.avatar_emoji
    : firstGlyphOf(persona.name || '?')

  return (
    <span
      data-testid={`character-avatar-fallback-${persona.id}`}
      className="inline-flex h-9 w-9 items-center justify-center rounded-full text-base font-semibold"
      style={{
        backgroundColor: hexWithAlpha(resolvedColor, 0.15),
        color: resolvedColor,
      }}
    >
      {glyph}
    </span>
  )
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
  const voiceIdHistory = useMemo(() => {
    const seen = new Map<string, number>()
    for (const p of personas) {
      const v = (p.tts_voice_id ?? '').trim()
      if (!v) continue
      seen.set(v, (seen.get(v) ?? 0) + 1)
    }
    return Array.from(seen.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([v]) => v)
  }, [personas])

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
      // For new personas, default work_id to the sidebar-selected work.
      // For edits, use whatever the form says (allows reassignment).
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <BookUser size={17} className="text-[#3b5bdb]" />
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            {t.characterLibrary.title}
          </h1>
          <span
            data-testid="character-library-count"
            className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500"
          >
            {t.characterLibrary.countHint(personas.length)}
          </span>
        </div>
        <div
          data-testid="character-library-toolbar"
          className="ml-auto flex flex-wrap items-center justify-end gap-2"
        >
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
          <div className="relative w-52">
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
              className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
            />
          </div>
          <button
            type="button"
            data-testid="character-library-create"
            onClick={openCreate}
            className="inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
          >
            <PlusCircle size={14} />
            {t.characterLibrary.actions.create}
          </button>
        </div>
        {(t.characterLibrary.subtitle || storagePath) && (
          <p
            data-testid="character-library-storage"
            className="w-full text-[11px] text-slate-400"
          >
            {t.characterLibrary.subtitle}
            {t.characterLibrary.subtitle && storagePath && ' · '}
            {storagePath && t.characterLibrary.storageHint(storagePath)}
          </p>
        )}
      </div>

      {flash && (
        <div
          data-testid={`character-library-flash-${flash.type}`}
          className={
            flash.type === 'success'
              ? 'mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700'
              : 'mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700'
          }
        >
          {flash.text}
        </div>
      )}

      <div data-testid="character-library-main" className="flex flex-col gap-3">
        <div
          data-testid="character-library-list"
          className="overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]"
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
                    className="mt-2 inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
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
              <table className="w-full min-w-[940px] border-collapse text-sm">
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
                      {t.characterLibrary.columns.ttsStatus}
                    </th>
                    <th className="px-4 py-2 text-right font-medium">
                      {t.characterLibrary.columns.actions}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(persona => {
                    const resolvedColor = normalizeHex(persona.color) || DEFAULT_COLOR
                    return (
                    <tr
                      key={persona.id}
                      data-testid={`character-row-${persona.id}`}
                      className="border-t border-[#e5e7eb] text-slate-700 transition-colors hover:bg-[#f9fafb]"
                    >
                      <td className="px-4 py-3">
                        <PersonaAvatar persona={persona} resolvedColor={resolvedColor} />
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
                      <td className="px-4 py-3">
                        {persona.tts_voice_id ? (
                          <span
                            className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                            title={persona.tts_voice_id}
                            data-testid={`character-tts-ready-${persona.id}`}
                          >
                            <Mic2 size={10} />
                            已绑定
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-400"
                            data-testid={`character-tts-missing-${persona.id}`}
                          >
                            未绑定
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-2">
                          <button
                            type="button"
                            data-testid={`character-edit-${persona.id}`}
                            onClick={() => openEdit(persona)}
                            className="inline-flex items-center gap-1 rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
                          >
                            <Pencil size={12} />
                            {t.characterLibrary.actions.edit}
                          </button>
                          <button
                            type="button"
                            data-testid={`character-delete-${persona.id}`}
                            onClick={() => handleDelete(persona)}
                            className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-600 transition-all hover:bg-rose-50"
                          >
                            <Trash2 size={12} />
                            {t.characterLibrary.actions.delete}
                          </button>
                        </div>
                      </td>
                    </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
        </div>
      </div>

      {editorOpen && (
        <>
          <div
            data-testid="character-editor-backdrop"
            className="fixed inset-0 z-40 bg-slate-900/40"
            onClick={closeEditor}
          />
          <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l border-[#e5e7eb] bg-white shadow-2xl">
            <form
              data-testid="character-editor"
              onSubmit={handleSubmit}
              className="flex h-full flex-col"
            >
              <div className="flex items-center justify-between border-b border-[#e5e7eb] px-5 py-3">
                <h2 className="text-base font-semibold text-slate-800">
                  {editingId
                    ? t.characterLibrary.drawer.editTitle
                    : t.characterLibrary.drawer.createTitle}
                </h2>
                <button
                  type="button"
                  data-testid="character-editor-close"
                  onClick={closeEditor}
                  className="rounded-lg p-1.5 text-slate-400 transition-all hover:bg-[#f3f4f6] hover:text-[#374151]"
                >
                  <X size={16} />
                </button>
              </div>
              <div className="grid flex-1 gap-4 overflow-y-auto px-5 py-4 sm:grid-cols-2">
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
                <div className="flex flex-col">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700" htmlFor="character-field-role">
                    {t.characterLibrary.fields.role}
                  </label>
                  <input
                    id="character-field-role"
                    list="character-role-presets"
                    data-testid="character-field-role"
                    type="text"
                    value={form.role}
                    onChange={event => setForm(f => ({ ...f, role: event.target.value }))}
                    placeholder={t.characterLibrary.placeholders.role}
                    className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
                  />
                  <datalist id="character-role-presets">
                    {ROLE_PRESET_KEYS.map(key => (
                      <option key={key} value={t.characterLibrary.rolePresets[key]} />
                    ))}
                  </datalist>
                </div>
                <div className="flex flex-col">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.characterLibrary.fields.gender}
                  </label>
                  <select
                    data-testid="character-field-gender"
                    value={form.gender}
                    onChange={event => setForm(f => ({ ...f, gender: event.target.value }))}
                    className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
                  >
                    <option value="">{t.characterLibrary.gender.none}</option>
                    <option value="female">{t.characterLibrary.gender.female}</option>
                    <option value="male">{t.characterLibrary.gender.male}</option>
                    <option value="other">{t.characterLibrary.gender.other}</option>
                  </select>
                </div>
                <div className="flex flex-col sm:col-span-2">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.characterLibrary.fields.ageHint}
                  </label>
                  <AgeBandSelector
                    value={form.age_hint}
                    onChange={v => setForm(f => ({ ...f, age_hint: v }))}
                    dataTestId="character-field-age"
                  />
                </div>
                <div className="flex flex-col">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.characterLibrary.fields.avatarEmoji}
                  </label>
                  <EmojiAvatarPicker
                    value={form.avatar_emoji}
                    onChange={v => setForm(f => ({ ...f, avatar_emoji: v }))}
                    color={form.color}
                    nameForFallback={form.name}
                    dataTestId="character-field-avatar"
                  />
                </div>
                <LabeledInput
                  label={t.characterLibrary.fields.avatarUrl}
                  placeholder={t.characterLibrary.placeholders.avatarUrl}
                  value={form.avatar_url}
                  onChange={v => setForm(f => ({ ...f, avatar_url: v }))}
                  dataTestId="character-field-avatar-url"
                />
                <div className="flex flex-col">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.characterLibrary.fields.color}
                  </label>
                  <ColorSwatchPicker
                    value={form.color}
                    onChange={v => setForm(f => ({ ...f, color: v }))}
                    dataTestId="character-field-color"
                  />
                </div>
                <div className="flex flex-col sm:col-span-2">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700" htmlFor="character-field-voice">
                    {t.characterLibrary.fields.ttsVoiceId}
                  </label>
                  <input
                    id="character-field-voice"
                    list="character-tts-voice-history"
                    data-testid="character-field-voice"
                    type="text"
                    value={form.tts_voice_id}
                    onChange={event => setForm(f => ({ ...f, tts_voice_id: event.target.value }))}
                    placeholder={t.characterLibrary.placeholders.ttsVoiceId}
                    className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
                  />
                  <datalist id="character-tts-voice-history">
                    {voiceIdHistory.map(v => (
                      <option key={v} value={v} />
                    ))}
                  </datalist>
                  {voiceIdHistory.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      <span className="text-[10px] uppercase tracking-wider text-slate-400">
                        {t.characterLibrary.tts.recentLabel}
                      </span>
                      {voiceIdHistory.slice(0, 6).map(v => (
                        <button
                          key={v}
                          type="button"
                          data-testid={`character-tts-history-${v}`}
                          onClick={() => setForm(f => ({ ...f, tts_voice_id: v }))}
                          className="h-6 rounded-full border border-[#e5e7eb] bg-white px-2 text-[11px] font-mono text-slate-600 transition-all hover:border-[#3b5bdb]/40 hover:text-[#3b5bdb]"
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {works.length > 0 && (
                  <div className="flex flex-col sm:col-span-2">
                    <label className="mb-1.5 block text-sm font-medium text-slate-700">
                      {t.characterLibrary.works.belongsTo}
                    </label>
                    <select
                      data-testid="character-field-work"
                      value={form.work_id}
                      onChange={event => setForm(f => ({ ...f, work_id: event.target.value }))}
                      className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
                    >
                      <option value="">{t.characterLibrary.works.belongsToNone}</option>
                      {works.map(w => (
                        <option key={w.id} value={w.id}>{w.title}</option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="flex flex-col sm:col-span-2">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.characterLibrary.fields.aliases}
                  </label>
                  <ChipInput
                    dataTestId="character-field-aliases"
                    value={form.aliases}
                    onChange={next => setForm(f => ({ ...f, aliases: next }))}
                    placeholder={t.characterLibrary.placeholders.aliases}
                    ariaLabel={t.characterLibrary.fields.aliases}
                    removeLabel={t.characterLibrary.fields.aliases}
                  />
                </div>
                <div className="flex flex-col sm:col-span-2">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.characterLibrary.fields.tags}
                  </label>
                  <ChipInput
                    dataTestId="character-field-tags"
                    value={form.tags}
                    onChange={next => setForm(f => ({ ...f, tags: next }))}
                    placeholder={t.characterLibrary.placeholders.tags}
                    ariaLabel={t.characterLibrary.fields.tags}
                    removeLabel={t.characterLibrary.fields.tags}
                  />
                </div>
                <div className="flex flex-col sm:col-span-2">
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.characterLibrary.fields.note}
                  </label>
                  <textarea
                    data-testid="character-field-note"
                    rows={3}
                    value={form.note}
                    onChange={event => setForm(f => ({ ...f, note: event.target.value }))}
                    placeholder={t.characterLibrary.placeholders.note}
                    className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
                  />
                </div>
              </div>
              <div className="flex items-center justify-end gap-2 border-t border-[#e5e7eb] px-5 py-3">
                <button
                  type="button"
                  data-testid="character-editor-cancel"
                  onClick={closeEditor}
                  className="rounded-lg border border-[#e5e7eb] bg-white px-4 py-2 text-sm font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
                >
                  {t.characterLibrary.actions.cancel}
                </button>
                <button
                  type="submit"
                  data-testid="character-editor-save"
                  disabled={!form.name.trim() || upsertMutation.isPending}
                  className="rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t.characterLibrary.actions.save}
                </button>
              </div>
            </form>
          </div>
        </>
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
    <div className={`flex flex-col ${className}`}>
      <label className="mb-1.5 block text-sm font-medium text-slate-700">{label}</label>
      <input
        data-testid={dataTestId}
        type="text"
        value={value}
        required={required}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
      />
    </div>
  )
}
