import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { motion } from 'framer-motion'
import {
  Scissors,
  MicVocal,
  Users,
  Languages,
  Headphones,
  Clapperboard,
  Film,
  ScanText,
  FileOutput,
  Eraser,
  AudioWaveform,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import type { WorkflowGraphNode } from '../../types'

// ─── constants ────────────────────────────────────────────────────────────────

export const COMPACT_NODE_WIDTH = 78
export const FULL_NODE_WIDTH = 96
export const COMPACT_CIRCLE = 52
export const FULL_CIRCLE = 66

// ─── status colours ───────────────────────────────────────────────────────────

const STATUS_CIRCLE: Record<WorkflowGraphNode['status'], string> = {
  pending:   'border-slate-200 bg-white text-slate-400',
  running:   'border-sky-400 bg-sky-50 text-sky-600 shadow-[0_0_20px_4px_rgba(14,165,233,0.35)]',
  succeeded: 'border-emerald-400 bg-emerald-50 text-emerald-600 shadow-[0_0_18px_4px_rgba(16,185,129,0.3)]',
  cached:    'border-violet-400 bg-violet-50 text-violet-600 shadow-[0_0_18px_4px_rgba(139,92,246,0.28)]',
  failed:    'border-rose-400 bg-rose-50 text-rose-600 shadow-[0_0_18px_4px_rgba(244,63,94,0.3)]',
  skipped:   'border-amber-300 bg-amber-50 text-amber-500 shadow-[0_0_14px_4px_rgba(245,158,11,0.22)]',
}

// ─── icons ────────────────────────────────────────────────────────────────────

/** Per-node icon: each stage gets a unique icon reflecting its purpose */
const NODE_ICON: Record<string, typeof AudioWaveform> = {
  'stage1':          Scissors,      // 音频分离
  'task-a':          MicVocal,      // 语音转写
  'asr-ocr-correct': ScanText,      // 文稿校正
  'task-b':          Users,          // 说话人注册
  'task-c':          Languages,      // 翻译
  'task-d':          Headphones,    // 语音合成
  'task-e':          Clapperboard,  // 时间线装配
  'task-g':          Film,          // 视频交付
  'ocr-detect':      ScanText,      // 字幕定位
  'ocr-translate':   FileOutput,    // 字幕翻译
  'subtitle-erase':  Eraser,        // 字幕擦除
}

// ─── data shape ───────────────────────────────────────────────────────────────

export interface WorkflowFlowNodeData extends Record<string, unknown> {
  node: WorkflowGraphNode
  compact: boolean
  shortLabel: string
  isSelected: boolean
  onSelect?: (id: string) => void
}

// ─── component ────────────────────────────────────────────────────────────────

function _WorkflowFlowNode({ data }: NodeProps) {
  const d = data as WorkflowFlowNodeData
  const { node, compact, shortLabel, isSelected, onSelect } = d

  const Icon = NODE_ICON[node.id] ?? AudioWaveform
  const circleSize = compact ? COMPACT_CIRCLE : FULL_CIRCLE
  const nodeWidth = compact ? COMPACT_NODE_WIDTH : FULL_NODE_WIDTH
  const iconSize = compact ? 18 : 22
  const r = (circleSize - 10) / 2    // progress ring radius
  const circumference = 2 * Math.PI * r

  // Invisible handles sit at the circle's mid-height so edges look connected
  // to the circle perimeter, not the label area below.
  const handleTop = circleSize / 2 - 4  // -4 to centre the 8px handle dot
  const handleSide = (nodeWidth - circleSize) / 2 - 4

  return (
    <div style={{ width: nodeWidth, cursor: 'default' }}>
      {/* Invisible target handle – left side of circle */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          top: handleTop,
          left: handleSide,
          width: 8,
          height: 8,
          opacity: 0,
          pointerEvents: 'none',
        }}
      />

      <div className="flex flex-col items-center gap-1">
        {/* ── circle ── */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => onSelect?.(node.id)}
          onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && onSelect?.(node.id)}
          aria-label={shortLabel}
          className={cn(
            'relative flex items-center justify-center rounded-full border-2 cursor-pointer select-none',
            'transition-shadow duration-300',
            STATUS_CIRCLE[node.status],
            isSelected && 'ring-[3px] ring-sky-400/80 ring-offset-2 ring-offset-white',
          )}
          style={{ width: circleSize, height: circleSize }}
        >
          <Icon size={iconSize} strokeWidth={2} />

          {/* Running progress ring */}
          {node.status === 'running' && (
            <svg
              className="absolute inset-0 -rotate-90"
              style={{ width: circleSize, height: circleSize }}
              viewBox={`0 0 ${circleSize} ${circleSize}`}
            >
              <circle
                cx={circleSize / 2}
                cy={circleSize / 2}
                r={r}
                fill="none"
                stroke="rgba(14,165,233,0.18)"
                strokeWidth={4}
              />
              <motion.circle
                cx={circleSize / 2}
                cy={circleSize / 2}
                r={r}
                fill="none"
                stroke="rgb(14,165,233)"
                strokeWidth={4}
                strokeLinecap="round"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{ strokeDashoffset: circumference * (1 - node.progress_percent / 100) }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
              />
            </svg>
          )}

          {/* Required / optional badge — full mode only */}
          {!compact && (
            <span
              className={cn(
                'absolute -top-1.5 -right-1.5 rounded-full px-1.5 py-0.5 text-[8px] font-bold leading-none uppercase tracking-wide',
                node.required
                  ? 'bg-slate-600/90 text-white'
                  : 'border border-dashed border-slate-300 bg-white text-slate-400',
              )}
            >
              {node.required ? '必' : '选'}
            </span>
          )}
        </div>

        {/* Label */}
        <div
          className={cn(
            'text-center font-medium leading-tight text-slate-600 break-words',
            compact ? 'text-[9px] max-w-[74px]' : 'text-[11px] max-w-[88px]',
          )}
        >
          {shortLabel}
        </div>

        {/* Running percentage */}
        {node.status === 'running' && (
          <div className={cn('font-bold text-sky-500', compact ? 'text-[8px]' : 'text-[10px]')}>
            {node.progress_percent.toFixed(0)}%
          </div>
        )}
      </div>

      {/* Invisible source handle – right side of circle */}
      <Handle
        type="source"
        position={Position.Right}
        style={{
          top: handleTop,
          right: handleSide,
          width: 8,
          height: 8,
          opacity: 0,
          pointerEvents: 'none',
        }}
      />
    </div>
  )
}

export const WorkflowFlowNode = memo(_WorkflowFlowNode)
