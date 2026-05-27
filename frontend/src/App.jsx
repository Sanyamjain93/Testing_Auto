import { useState, useRef, useCallback, useEffect } from 'react'
import UploadSection from './components/UploadSection'
import ProgressStatus from './components/ProgressStatus'
import LogStream from './components/LogStream'
import ResultsTable from './components/ResultsTable'
import styles from './App.module.css'

const PHASE = {
  IDLE: 'idle',
  UPLOADING: 'uploading',
  RUNNING: 'running',
  DONE: 'done',
  ERROR: 'error',
}

const LLM_OPTIONS = [
  { label: 'Ollama — llama3',                          provider: 'ollama',      model: 'llama3' },
  { label: 'Groq — llama-3.1-8b-instant',             provider: 'groq',        model: 'llama-3.1-8b-instant' },
  { label: 'Groq — llama-3.3-70b-versatile',          provider: 'groq',        model: 'llama-3.3-70b-versatile' },
  { label: 'Groq — llama-4-scout-17b-16e-instruct',   provider: 'groq',        model: 'meta-llama/llama-4-scout-17b-16e-instruct' },
  { label: 'HuggingFace — Llama-3.3-70B-Instruct',    provider: 'huggingface', model: 'meta-llama/Llama-3.3-70B-Instruct' },
]
const DEFAULT_LLM = LLM_OPTIONS[3]  // Groq llama-4-scout

export default function App() {
  const [files, setFiles] = useState([])
  const [phase, setPhase] = useState(PHASE.IDLE)
  const [logs, setLogs] = useState([])
  const [results, setResults] = useState([])
  const [errorMsg, setErrorMsg] = useState('')
  const [uploadedNames, setUploadedNames] = useState([])
  const [ragStatus, setRagStatus] = useState('') // '' | 'refreshing' | 'done' | 'error'
  const [scriptStatus, setScriptStatus] = useState('') // '' | 'generating' | 'done' | 'error'
  const [selectedLlm, setSelectedLlm] = useState(DEFAULT_LLM)
  const [progress, setProgress] = useState({ currentStage: null, currentStatus: null })
  const [showLogs, setShowLogs] = useState(false)
  const esRef = useRef(null)

  // Poll status on mount (resume if pipeline was already running)
  useEffect(() => {
    fetch('/status')
      .then(r => r.json())
      .then(data => {
        if (data.running) {
          setPhase(PHASE.RUNNING)
          openStream()
        } else if (data.done) {
          setPhase(PHASE.DONE)
          loadResults()
        }
      })
      .catch(() => {}) // backend not up yet – ignore
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const openStream = useCallback(() => {
    if (esRef.current) esRef.current.close()
    const es = new EventSource('/stream')
    esRef.current = es

    es.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.progress) {
        setProgress({ currentStage: data.progress.stage, currentStatus: data.progress.status })
      }
      if (data.log) {
        setLogs(prev => [...prev, data.log])
      }
      if (data.error) {
        setErrorMsg(data.error)
        setPhase(PHASE.ERROR)
        es.close()
      }
      if (data.done) {
        setPhase(PHASE.DONE)
        loadResults()
        es.close()
      }
    }
    es.onerror = () => {
      es.close()
      // Only flip to error if we are still in running state
      setPhase(prev => prev === PHASE.RUNNING ? PHASE.ERROR : prev)
      setErrorMsg(prev => prev || 'Connection to backend lost.')
    }
  }, [])

  const loadResults = useCallback(() => {
    fetch('/results')
      .then(r => r.json())
      .then(data => setResults(data.test_cases || []))
      .catch(() => setErrorMsg('Failed to load results.'))
  }, [])

  const handleUploadAndRun = useCallback(async () => {
    if (files.length === 0) return

    setLogs([])
    setResults([])
    setErrorMsg('')
    setProgress({ currentStage: null, currentStatus: null })
    setShowLogs(false)

    // ── Upload ──────────────────────────────────────────────────────────────
    setPhase(PHASE.UPLOADING)
    const form = new FormData()
    files.forEach(f => form.append('files', f))

    let uploadRes
    try {
      const res = await fetch('/upload', { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Upload failed')
      }
      uploadRes = await res.json()
    } catch (e) {
      setErrorMsg(e.message)
      setPhase(PHASE.ERROR)
      return
    }
    setUploadedNames(uploadRes.uploaded || [])

    // ── Run pipeline ────────────────────────────────────────────────────────
    try {
      const res = await fetch('/run', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to start pipeline')
    } catch (e) {
      setErrorMsg(e.message)
      setPhase(PHASE.ERROR)
      return
    }

    setPhase(PHASE.RUNNING)
    openStream()
  }, [files, openStream])

  const handleReset = () => {
    if (esRef.current) esRef.current.close()
    setFiles([])
    setPhase(PHASE.IDLE)
    setLogs([])
    setResults([])
    setErrorMsg('')
    setUploadedNames([])
    setScriptStatus('')
    setProgress({ currentStage: null, currentStatus: null })
    setShowLogs(false)
  }

  const handleRefreshRag = useCallback(async () => {
    setRagStatus('refreshing')
    try {
      const res = await fetch('/rag-index', { method: 'DELETE' })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to clear RAG index')
      }
      setRagStatus('done')
    } catch (e) {
      setRagStatus('error')
    }
    setTimeout(() => setRagStatus(''), 3000)
  }, [])

  const handleLlmChange = useCallback(async (e) => {
    const opt = LLM_OPTIONS.find(o => o.model === e.target.value)
    if (!opt) return
    setSelectedLlm(opt)
    try {
      await fetch('/set-llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: opt.provider, model: opt.model }),
      })
    } catch (_) {}
  }, [])

  const handleDownload = () => {
    window.open('/download', '_blank')
  }

  const handleGenerateScripts = useCallback(async () => {
    setScriptStatus('generating')
    try {
      const res = await fetch('/generate-scripts', { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Script generation failed')
      setLogs(prev => [...prev, `[SCRIPT] ${data.count} Playwright script(s) generated ✅`])
      setScriptStatus('done')
    } catch (e) {
      setLogs(prev => [...prev, `[SCRIPT ERROR] ${e.message}`])
      setScriptStatus('error')
    }
  }, [])

  const handleDownloadScripts = () => {
    window.open('/download-scripts', '_blank')
  }

  const isRunning = phase === PHASE.RUNNING || phase === PHASE.UPLOADING
  const canRun = files.length > 0 && !isRunning

  return (
    <div className={styles.layout}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.logo}>
            <span className={styles.logoIcon}>⚡</span>
            <div>
              <h1 className={styles.logoTitle}>AI Test Case Generator</h1>
              <p className={styles.logoSub}>Powered by Mistral LLM · RAG Pipeline</p>
            </div>
          </div>
          <StatusBadge phase={phase} />
        </div>
      </header>

      <main className={styles.main}>
        {/* ── Left column ──────────────────────────────────────────────────── */}
        <section className={styles.leftCol}>
          <Card title="1 · Upload Requirements">
            <UploadSection
              files={files}
              setFiles={setFiles}
              disabled={isRunning}
            />
          </Card>

          <Card title="2 · Generate Test Cases">
            <div className={styles.actionArea}>
              {uploadedNames.length > 0 && (
                <p className={styles.uploadedHint}>
                  ✓ {uploadedNames.length} file{uploadedNames.length > 1 ? 's' : ''} uploaded
                </p>
              )}

              <div className={styles.llmRow}>
                <label className={styles.llmLabel} htmlFor="llm-select">Model</label>
                <select
                  id="llm-select"
                  className={styles.llmSelect}
                  value={selectedLlm.model}
                  onChange={handleLlmChange}
                  disabled={isRunning}
                >
                  {LLM_OPTIONS.map(o => (
                    <option key={o.model} value={o.model}>{o.label}</option>
                  ))}
                </select>
              </div>

              <button
                className={styles.runBtn}
                onClick={handleUploadAndRun}
                disabled={!canRun}
              >
                {phase === PHASE.UPLOADING ? (
                  <><Spinner /> Uploading…</>
                ) : phase === PHASE.RUNNING ? (
                  <><Spinner /> Running pipeline…</>
                ) : (
                  '▶ Generate Test Cases'
                )}
              </button>

              <button
                className={styles.refreshRagBtn}
                onClick={handleRefreshRag}
                disabled={isRunning || ragStatus === 'refreshing'}
              >
                {ragStatus === 'refreshing' ? <><Spinner /> Clearing RAG index…</> :
                 ragStatus === 'done'       ? '✅ RAG index cleared — will rebuild on next Run' :
                 ragStatus === 'error'      ? '❌ Failed to clear RAG index' :
                 '🔄 Refresh RAG'}
              </button>

              {(phase === PHASE.DONE || phase === PHASE.ERROR) && (
                <button className={styles.resetBtn} onClick={handleReset}>
                  ↺ Reset
                </button>
              )}
            </div>

            {phase === PHASE.ERROR && (
              <div className={styles.errorBox}>
                <strong>Error:</strong> {errorMsg}
              </div>
            )}
          </Card>

          {phase === PHASE.DONE && results.length > 0 && (
            <Card title="3 · Download Results">
              <div className={styles.downloadArea}>
                <p className={styles.downloadHint}>
                  {results.length} test step{results.length !== 1 ? 's' : ''} generated
                </p>
                <button className={styles.downloadBtn} onClick={handleDownload}>
                  ⬇ Download Excel
                </button>
              </div>
            </Card>
          )}

          {phase === PHASE.DONE && results.length > 0 && (
            <Card title="4 · Playwright Scripts">
              <div className={styles.downloadArea}>
                <p className={styles.downloadHint}>
                  Generate Playwright (JavaScript) automation scripts for all test cases.
                </p>
                <button
                  className={styles.generateScriptsBtn}
                  onClick={handleGenerateScripts}
                  disabled={scriptStatus === 'generating'}
                >
                  {scriptStatus === 'generating'
                    ? <><Spinner /> Generating scripts…</>
                    : '⚡ Generate Playwright Scripts'}
                </button>
                {scriptStatus === 'done' && (
                  <button className={styles.downloadBtn} onClick={handleDownloadScripts}>
                    ⬇ Download Scripts (.zip)
                  </button>
                )}
                {scriptStatus === 'error' && (
                  <p className={styles.downloadHint} style={{ color: 'var(--error)' }}>
                    ❌ Script generation failed. Check logs for details.
                  </p>
                )}
              </div>
            </Card>
          )}
        </section>

        {/* ── Right column ─────────────────────────────────────────────────── */}
        <section className={styles.rightCol}>
          {(logs.length > 0 || isRunning) && (
            <Card title="Pipeline Logs" accent>
              <ProgressStatus
                progress={progress}
                errorMsg={errorMsg}
                showLogs={showLogs}
                onToggleLogs={() => setShowLogs(!showLogs)}
              />
              {showLogs && (
                <div style={{ marginTop: '16px' }}>
                  <LogStream logs={logs} running={isRunning} />
                </div>
              )}
            </Card>
          )}

          {phase === PHASE.DONE && results.length > 0 && (
            <Card title={`Results — ${results.length} rows`}>
              <ResultsTable rows={results} />
            </Card>
          )}

          {phase === PHASE.IDLE && logs.length === 0 && (
            <div className={styles.emptyState}>
              <span className={styles.emptyIcon}>🧪</span>
              <p>Upload requirement documents and click Generate to start.</p>
              <p className={styles.emptyFormats}>Supported formats: PDF · DOCX · TXT · MD</p>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

// ── Small reusable pieces ─────────────────────────────────────────────────────

function Card({ title, children, accent }) {
  return (
    <div className={`${styles.card} ${accent ? styles.cardAccent : ''}`}>
      <h2 className={styles.cardTitle}>{title}</h2>
      {children}
    </div>
  )
}

function StatusBadge({ phase }) {
  const map = {
    [PHASE.IDLE]: { label: 'Idle', color: 'var(--text-muted)' },
    [PHASE.UPLOADING]: { label: 'Uploading…', color: 'var(--warning)' },
    [PHASE.RUNNING]: { label: 'Running', color: 'var(--accent)' },
    [PHASE.DONE]: { label: 'Done', color: 'var(--success)' },
    [PHASE.ERROR]: { label: 'Error', color: 'var(--error)' },
  }
  const { label, color } = map[phase] || map[PHASE.IDLE]
  return (
    <div className={styles.badge} style={{ '--badge-color': color }}>
      <span className={styles.badgeDot} />
      {label}
    </div>
  )
}

function Spinner() {
  return <span className={styles.spinner} />
}
