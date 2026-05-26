import { useEffect, useRef } from 'react'
import styles from './LogStream.module.css'

export default function LogStream({ logs, running }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const formatLine = (line) => {
    if (line.startsWith('ERROR') || line.includes('❌')) return 'error'
    if (line.includes('✅') || line.includes('Done') || line.includes('complete')) return 'success'
    if (line.includes('⚠') || line.includes('warn')) return 'warning'
    if (line.startsWith('📂') || line.startsWith('📄') || line.startsWith('🔍') ||
        line.startsWith('🧩') || line.startsWith('🤖') || line.startsWith('✍') ||
        line.startsWith('⚡') || line.startsWith('💾')) return 'info'
    return 'default'
  }

  return (
    <div className={styles.terminal}>
      {logs.length === 0 && running && (
        <div className={styles.waiting}>
          <span className={styles.cursor} />
          Waiting for output…
        </div>
      )}
      {logs.map((line, i) => (
        <div key={i} className={`${styles.line} ${styles[formatLine(line)]}`}>
          <span className={styles.lineNum}>{String(i + 1).padStart(3, '0')}</span>
          <span className={styles.lineText}>{line}</span>
        </div>
      ))}
      {running && logs.length > 0 && (
        <div className={styles.runningIndicator}>
          <span className={styles.cursor} /> Running…
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
