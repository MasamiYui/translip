import {
  AudioLines,
  Blend,
  Captions,
  Eraser,
  FileVideo,
  Film,
  Gauge,
  Languages,
  Mic,
  ScanEye,
  ScanText,
  SpellCheck,
  type LucideIcon,
} from 'lucide-react'

export interface ToolMeta {
  icon: LucideIcon
  zh: string
  en: string
}

// Lightweight icon + label map for the call-chain diagram. Falls back to a
// generic icon for any tool not listed here.
export const TOOL_META: Record<string, ToolMeta> = {
  separation: { icon: AudioLines, zh: '人声分离', en: 'Separation' },
  transcription: { icon: Captions, zh: '语音转文字', en: 'Transcription' },
  'transcript-correction': { icon: SpellCheck, zh: '台词校正', en: 'Correction' },
  translation: { icon: Languages, zh: '翻译', en: 'Translation' },
  tts: { icon: Mic, zh: '语音合成', en: 'TTS' },
  mixing: { icon: Blend, zh: '音频混合', en: 'Mixing' },
  muxing: { icon: Film, zh: '音视频合并', en: 'Muxing' },
  'subtitle-detect': { icon: ScanText, zh: '字幕识别', en: 'Subtitle Detect' },
  'subtitle-erase': { icon: Eraser, zh: '字幕擦除', en: 'Subtitle Erase' },
  'video-analyze': { icon: ScanEye, zh: '视频分析', en: 'Video Analyze' },
  probe: { icon: Gauge, zh: '媒体探测', en: 'Probe' },
  'm3u8-to-mp4': { icon: FileVideo, zh: 'HLS 转 MP4', en: 'M3U8 → MP4' },
}

export const FALLBACK_TOOL_ICON: LucideIcon = Gauge
