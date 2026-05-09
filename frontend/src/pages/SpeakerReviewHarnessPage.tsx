import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { SpeakerReviewDrawer } from '../components/speaker-review/SpeakerReviewDrawer'

interface SpeakerReviewRouteState {
  from?: string
}

export function SpeakerReviewHarnessPage() {
  const { taskId = 'harness-task' } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const routeState = location.state as SpeakerReviewRouteState | null
  const fallbackPath = taskId === 'harness-task' ? '/tasks' : `/tasks/${taskId}`

  return (
    <SpeakerReviewDrawer
      taskId={taskId}
      isOpen={true}
      onClose={() => {
        navigate(routeState?.from ?? fallbackPath, { replace: true })
      }}
    />
  )
}

export default SpeakerReviewHarnessPage
