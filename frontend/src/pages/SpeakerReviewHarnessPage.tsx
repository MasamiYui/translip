import { useParams } from 'react-router-dom'
import { SpeakerReviewDrawer } from '../components/speaker-review/SpeakerReviewDrawer'

export function SpeakerReviewHarnessPage() {
  const { taskId = 'harness-task' } = useParams<{ taskId: string }>()
  return (
    <SpeakerReviewDrawer
      taskId={taskId}
      isOpen={true}
      onClose={() => {
        window.history.back()
      }}
    />
  )
}

export default SpeakerReviewHarnessPage
