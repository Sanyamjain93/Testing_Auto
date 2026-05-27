import { useState } from 'react'
import styles from './ProgressStatus.module.css'

const STAGES = [
  { id: 'loading_documents', label: 'Loading documents', icon: '📂' },
  { id: 'rag_retrieval', label: 'Running RAG retrieval', icon: '🔍' },
  { id: 'generating_tests', label: 'Generating test cases', icon: '✍️' },
  { id: 'generating_scripts', label: 'Generating scripts', icon: '⚡' },
]

const STATUS_ICONS = {
  pending: '⏳',
  running: '⚙️',
  done: '✅',
  error: '❌',
}

export default function ProgressStatus({ progress, errorMsg, showLogs, onToggleLogs }) {
  const getStageStatus = (stageId) => {
    if (!progress.currentStage) return 'pending'
    const currentIdx = STAGES.findIndex(s => s.id === progress.currentStage)
    const stageIdx = STAGES.findIndex(s => s.id === stageId)

    if (stageIdx < currentIdx) return 'done'
    if (stageIdx === currentIdx) return progress.currentStatus || 'running'
    // If current stage is done and this is the very next stage, keep it pending
    return 'pending'
  }

  return (
    <div className={styles.container}>
      <div className={styles.statusGrid}>
        {STAGES.map(stage => {
          const status = getStageStatus(stage.id)
          return (
            <div key={stage.id} className={`${styles.statusItem} ${styles[status]}`}>
              <div className={styles.icon}>
                {status === 'running' ? (
                  <span className={styles.spinner}>⚙️</span>
                ) : (
                  <span>{STATUS_ICONS[status]}</span>
                )}
              </div>
              <div className={styles.label}>{stage.label}</div>
            </div>
          )
        })}
      </div>

      {errorMsg && (
        <div className={styles.errorBox}>
          <div className={styles.errorIcon}>❌</div>
          <div className={styles.errorText}>{errorMsg}</div>
        </div>
      )}

      <button
        className={styles.logsToggle}
        onClick={onToggleLogs}
        title={showLogs ? 'Hide detailed logs' : 'Show detailed logs'}
      >
        <span className={styles.toggleIcon}>{showLogs ? '▼' : '▶'}</span>
        View Detailed Logs
      </button>
    </div>
  )
}
