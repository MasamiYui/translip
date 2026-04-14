import type { ProgressEvent } from '../types'

export function subscribeToProgress(
  taskId: string,
  onEvent: (evt: ProgressEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(`/api/tasks/${taskId}/progress`)

  const handle = (e: MessageEvent, type: string) => {
    try {
      const data = JSON.parse(e.data)
      onEvent({ type: type as ProgressEvent['type'], ...data })
    } catch {}
  }

  es.addEventListener('progress', e => handle(e as MessageEvent, 'progress'))
  es.addEventListener('done', e => handle(e as MessageEvent, 'done'))
  es.addEventListener('error', e => {
    if (onError) onError(e)
  })

  return () => es.close()
}
