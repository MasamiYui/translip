import {
  AudioLines,
  Blend,
  Captions,
  Eraser,
  FileVideo,
  Film,
  Gauge,
  Flame,
  Globe,
  Languages,
  Mic,
  ScanEye,
  ScanText,
  Scissors,
  SpellCheck,
  Subtitles,
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
  'detect-language': { icon: Globe, zh: '语种识别', en: 'Language ID' },
  'transcript-correction': { icon: SpellCheck, zh: '台词校正', en: 'Correction' },
  translation: { icon: Languages, zh: '翻译', en: 'Translation' },
  tts: { icon: Mic, zh: '语音合成', en: 'TTS' },
  mixing: { icon: Blend, zh: '音频混合', en: 'Mixing' },
  muxing: { icon: Film, zh: '音视频合并', en: 'Muxing' },
  'dub-render': { icon: AudioLines, zh: '配音渲染', en: 'Dub Render' },
  'subtitle-detect': { icon: ScanText, zh: '字幕识别', en: 'Subtitle Detect' },
  'subtitle-erase': { icon: Eraser, zh: '字幕擦除', en: 'Subtitle Erase' },
  'subtitle-burn': { icon: Flame, zh: '字幕烧录', en: 'Burn Subs' },
  'subtitle-embed': { icon: Subtitles, zh: '字幕封装', en: 'Embed Subs' },
  'video-analyze': { icon: ScanEye, zh: '视频分析', en: 'Video Analyze' },
  probe: { icon: Gauge, zh: '媒体探测', en: 'Probe' },
  'm3u8-to-mp4': { icon: FileVideo, zh: 'HLS 转 MP4', en: 'M3U8 → MP4' },
  'video-trim': { icon: Scissors, zh: '视频裁剪', en: 'Video Trim' },
}

export const FALLBACK_TOOL_ICON: LucideIcon = Gauge
