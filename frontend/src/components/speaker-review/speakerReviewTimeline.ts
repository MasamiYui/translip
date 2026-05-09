import type {
  SpeakerReviewDecisionPayload,
  SpeakerReviewSegment,
  SpeakerReviewSpeaker,
} from '../../types'

export function sortTranscriptSegments(segments: SpeakerReviewSegment[]): SpeakerReviewSegment[] {
  return [...segments].sort((a, b) => a.start - b.start || a.end - b.end || a.index - b.index)
}

export function findActiveTranscriptSegment(
  segments: SpeakerReviewSegment[],
  playheadSec: number,
): SpeakerReviewSegment | null {
  if (!segments.length) return null
  const active = segments.find(segment => segment.start <= playheadSec && segment.end > playheadSec)
  if (active) return active

  return (
    segments.find(segment => segment.start > playheadSec) ??
    segments[segments.length - 1] ??
    null
  )
}

export function buildSpeakerChoices(
  speakers: SpeakerReviewSpeaker[],
  active: SpeakerReviewSegment | null,
  limit = 5,
): SpeakerReviewSpeaker[] {
  const byLabel = new Map(speakers.map(speaker => [speaker.speaker_label, speaker]))
  const labels = [
    active?.speaker_label,
    active?.previous_speaker_label,
    active?.next_speaker_label,
    ...speakers.map(speaker => speaker.speaker_label),
  ].filter((label): label is string => Boolean(label))

  const seen = new Set<string>()
  const choices: SpeakerReviewSpeaker[] = []
  for (const label of labels) {
    if (seen.has(label)) continue
    const speaker = byLabel.get(label)
    if (!speaker) continue
    seen.add(label)
    choices.push(speaker)
    if (choices.length >= limit) break
  }
  return choices
}

export function buildSegmentRelabelDecision(
  segment: SpeakerReviewSegment,
  targetSpeakerLabel: string,
): SpeakerReviewDecisionPayload {
  return {
    item_id: segment.segment_id,
    item_type: 'segment',
    decision: 'relabel',
    source_speaker_label: segment.speaker_label,
    target_speaker_label: targetSpeakerLabel,
    segment_ids: [segment.segment_id],
    payload: {
      source_speaker: segment.speaker_label,
      target_speaker: targetSpeakerLabel,
      source: 'video_timeline',
    },
  }
}
