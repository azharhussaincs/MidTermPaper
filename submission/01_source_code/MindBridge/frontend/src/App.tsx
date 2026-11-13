import { useCallback, useState } from 'react'
import { api } from './api/client'
import { ClinicianWorkspace } from './components/ClinicianWorkspace'
import { Home } from './components/Home'
import { PatientWorkspace } from './components/PatientWorkspace'
import { TopBar, type Workspace } from './components/TopBar'
import { usePolling } from './hooks/usePolling'

const WORKSPACE_KEY = 'mindbridge:workspace'

function initialWorkspace(): Workspace {
  try {
    const stored = localStorage.getItem(WORKSPACE_KEY)
    return stored === 'clinician' || stored === 'patient' ? stored : 'home'
  } catch {
    return 'home'
  }
}

export default function App() {
  const [workspace, setWorkspace] = useState<Workspace>(initialWorkspace)
  // One queue poll feeds both the nav badge and the clinician portal.
  const fetchQueue = useCallback((signal: AbortSignal) => api.clinician.queue(20, signal), [])
  const queue = usePolling(fetchQueue, 8_000)

  function switchWorkspace(next: Workspace) {
    setWorkspace(next)
    try {
      localStorage.setItem(WORKSPACE_KEY, next)
    } catch {
      // Remembering the workspace is a convenience only.
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-canvas lg:h-dvh">
      <TopBar
        workspace={workspace}
        onWorkspaceChange={switchWorkspace}
        awaitingReviewCount={queue.data?.awaiting_review.length ?? 0}
      />
      <div className="min-h-0 flex-1">
        {workspace === 'home' ? (
          <Home
            awaitingReviewCount={queue.data?.awaiting_review.length ?? 0}
            onStartCheckIn={() => switchWorkspace('patient')}
            onOpenReview={() => switchWorkspace('clinician')}
          />
        ) : workspace === 'patient' ? (
          <PatientWorkspace onQueueChanged={() => void queue.refresh()} />
        ) : (
          <ClinicianWorkspace queue={queue.data} queueError={queue.error} refreshQueue={queue.refresh} />
        )}
      </div>
    </div>
  )
}
