import { useMemo, useState } from 'react'
import Prism from 'prismjs'
import 'prismjs/components/prism-javascript'
import styles from './ScriptViewer.module.css'

function downloadScriptFile(name, content) {
  const blob = new Blob([content], { type: 'text/javascript;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export default function ScriptViewer({
  scripts,
  loading,
  error,
  onDownloadAll,
  selectedScriptName,
  onSelectScript,
}) {
  const [copyState, setCopyState] = useState('')

  const selectedScript = useMemo(() => {
    if (!scripts.length) return null
    return scripts.find(s => s.name === selectedScriptName) || scripts[0]
  }, [scripts, selectedScriptName])

  const highlightedCode = useMemo(() => {
    if (!selectedScript?.content) return ''
    return Prism.highlight(selectedScript.content, Prism.languages.javascript, 'javascript')
  }, [selectedScript])

  const handleCopy = async () => {
    if (!selectedScript?.content) return
    try {
      await navigator.clipboard.writeText(selectedScript.content)
      setCopyState('copied')
      setTimeout(() => setCopyState(''), 1200)
    } catch (_) {
      setCopyState('failed')
      setTimeout(() => setCopyState(''), 1200)
    }
  }

  if (loading) {
    return (
      <div className={styles.loadingBox}>
        <div className={styles.loader} />
        <p>Generating Playwright scripts...</p>
      </div>
    )
  }

  if (error) {
    return <div className={styles.errorBox}>{error}</div>
  }

  if (!scripts.length) {
    return (
      <div className={styles.emptyBox}>
        <p>No scripts found yet. Click "Generate Scripts" to create Playwright files.</p>
      </div>
    )
  }

  return (
    <div className={styles.viewer}>
      <div className={styles.toolbar}>
        <div className={styles.selectorWrap}>
          <label htmlFor="script-picker" className={styles.selectorLabel}>Script</label>
          <select
            id="script-picker"
            className={styles.selector}
            value={selectedScript?.name || ''}
            onChange={(e) => onSelectScript(e.target.value)}
          >
            {scripts.map(script => (
              <option key={script.name} value={script.name}>
                {script.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.actions}>
          <button className={styles.actionBtn} onClick={handleCopy}>
            {copyState === 'copied' ? 'Copied' : 'Copy Script'}
          </button>
          <button
            className={styles.actionBtn}
            onClick={() => downloadScriptFile(selectedScript.name, selectedScript.content)}
          >
            Download Script
          </button>
          <button className={styles.primaryBtn} onClick={onDownloadAll}>
            Download All (ZIP)
          </button>
        </div>
      </div>

      <div className={styles.scriptLabel}>Script: {selectedScript.label}</div>

      <div className={styles.codeContainer}>
        <pre className={`${styles.codeBlock} language-javascript`}>
          <code dangerouslySetInnerHTML={{ __html: highlightedCode }} />
        </pre>
      </div>
    </div>
  )
}
