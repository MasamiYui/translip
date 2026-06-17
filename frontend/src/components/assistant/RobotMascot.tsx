import { cn } from '../../lib/utils'

export type MascotState = 'idle' | 'thinking' | 'running' | 'done'

interface RobotMascotProps {
  state?: MascotState
  size?: number
  className?: string
}

/**
 * A friendly little robot drawn entirely in SVG/CSS — no image assets.
 * Eyes blink on idle, the antenna pulses while it's thinking/running, and the
 * mouth turns into a happy curve when a run completes.
 */
export function RobotMascot({ state = 'idle', size = 40, className }: RobotMascotProps) {
  const active = state === 'thinking' || state === 'running'
  const happy = state === 'done'
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      role="img"
      aria-hidden="true"
      className={cn('select-none', className)}
    >
      {/* antenna */}
      <line x1="24" y1="6" x2="24" y2="12" stroke="#3b5bdb" strokeWidth="2" strokeLinecap="round" />
      <circle
        cx="24"
        cy="5"
        r="3"
        fill="#5b8def"
        className={active ? 'assistant-antenna' : undefined}
      />
      {/* head */}
      <rect x="8" y="12" width="32" height="26" rx="9" fill="#eef2ff" stroke="#3b5bdb" strokeWidth="2" />
      {/* ears */}
      <rect x="4" y="20" width="4" height="9" rx="2" fill="#3b5bdb" />
      <rect x="40" y="20" width="4" height="9" rx="2" fill="#3b5bdb" />
      {/* face screen */}
      <rect x="13" y="17" width="22" height="16" rx="6" fill="#1f2a55" />
      {/* eyes */}
      <g fill="#7fe7ff">
        <circle cx="20" cy="24" r="2.4" className="assistant-eye" />
        <circle cx="28" cy="24" r="2.4" className="assistant-eye" />
      </g>
      {/* mouth */}
      {happy ? (
        <path d="M19 28.5 Q24 32 29 28.5" stroke="#7fe7ff" strokeWidth="1.8" strokeLinecap="round" fill="none" />
      ) : (
        <rect x="20" y="29" width="8" height="1.8" rx="0.9" fill="#7fe7ff" opacity={active ? 0.9 : 0.6} />
      )}
    </svg>
  )
}
