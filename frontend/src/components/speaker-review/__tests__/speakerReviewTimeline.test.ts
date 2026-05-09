import { describe, expect, it } from 'vitest'

import type { SpeakerReviewSegment, SpeakerReviewSpeaker } from '../../../types'
import {
  buildSegmentRelabelDecision,
  buildSpeakerChoices,
  findActiveTranscriptSegment,
  sortTranscriptSegments,
} from '../speakerReviewTimeline'

const speakers: SpeakerReviewSpeaker[] = [
  {
    speaker_label: 'SPEAKER_00',
    segment_count: 2,
    segment_ids: ['seg-1', 'seg-3'],
    total_speech_sec: 5,
    avg_duration_sec: 2.5,
    short_segment_count: 0,
    risk_flags: [],
    risk_level: 'low',
    cloneable_by_default: true,
  },
  {
    speaker_label: 'SPEAKER_01',
    segment_count: 1,
    segment_ids: ['seg-2'],
    total_speech_sec: 2,
    avg_duration_sec: 2,
    short_segment_count: 0,
    risk_flags: [],
    risk_level: 'low',
    cloneable_by_default: true,
  },
]

const segments: SpeakerReviewSegment[] = [
  {
    segment_id: 'seg-2',
    index: 2,
    speaker_label: 'SPEAKER_01',
    start: 3,
    end: 5,
    duration: 2,
    text: '第二句',
    previous_speaker_label: 'SPEAKER_00',
    next_speaker_label: 'SPEAKER_00',
    risk_flags: ['speaker_boundary_risk'],
    risk_level: 'medium',
  },
  {
    segment_id: 'seg-1',
    index: 1,
    speaker_label: 'SPEAKER_00',
    start: 0,
    end: 2,
    duration: 2,
    text: '第一句',
    next_speaker_label: 'SPEAKER_01',
    risk_flags: [],
    risk_level: 'low',
  },
  {
    segment_id: 'seg-3',
    index: 3,
    speaker_label: 'SPEAKER_00',
    start: 5.2,
    end: 8.2,
    duration: 3,
    text: '第三句',
    previous_speaker_label: 'SPEAKER_01',
    risk_flags: [],
    risk_level: 'low',
  },
]

describe('speaker review timeline helpers', () => {
  it('sorts transcript segments and finds the active segment under the playhead', () => {
    const sorted = sortTranscriptSegments(segments)

    expect(sorted.map(segment => segment.segment_id)).toEqual(['seg-1', 'seg-2', 'seg-3'])
    expect(findActiveTranscriptSegment(sorted, 3.4)?.segment_id).toBe('seg-2')
    expect(findActiveTranscriptSegment(sorted, 5.1)?.segment_id).toBe('seg-3')
  })

  it('prioritizes the current, previous, and next speakers for fast number-key reassignment', () => {
    const active = sortTranscriptSegments(segments)[1]
    const choices = buildSpeakerChoices(speakers, active, 3)

    expect(choices.map(choice => choice.speaker_label)).toEqual([
      'SPEAKER_01',
      'SPEAKER_00',
    ])
  })

  it('builds an explicit relabel decision for the active segment', () => {
    const active = sortTranscriptSegments(segments)[1]

    expect(buildSegmentRelabelDecision(active, 'SPEAKER_00')).toMatchObject({
      item_id: 'seg-2',
      item_type: 'segment',
      decision: 'relabel',
      source_speaker_label: 'SPEAKER_01',
      target_speaker_label: 'SPEAKER_00',
      segment_ids: ['seg-2'],
    })
  })
})
