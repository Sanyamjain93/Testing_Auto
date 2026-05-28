import { useState, useRef, useCallback, useEffect } from 'react'
import UploadSection from './components/UploadSection'
import ProgressStatus from './components/ProgressStatus'
import TestSummary from './components/TestSummary'
import LogStream from './components/LogStream'
import ResultsTable from './components/ResultsTable'
import ScriptViewer from './components/ScriptViewer'
import Login from './components/Login'
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
  // ── Auth state ──────────────────────────────────────────────────────────
  const [isAuthenticated, setIsAuthenticated] = useState(null) // null=checking, false=login, true=authed
  const [currentUser, setCurrentUser] = useState('')

  // Check existing session on mount
  useEffect(() => {
    fetch('/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.authenticated) {
          setCurrentUser(data.username)
          setIsAuthenticated(true)
        } else {
          setIsAuthenticated(false)
        }
      })
      .catch(() => setIsAuthenticated(false))
  }, [])

  const handleLogin = (username) => {
    setCurrentUser(username)
    setIsAuthenticated(true)
  }

  const handleLogout = async () => {
    try { await fetch('/logout', { method: 'POST', credentials: 'include' }) } catch (_) {}
    setIsAuthenticated(false)
    setCurrentUser('')
    setFiles([])
    setPhase(PHASE.IDLE)
    setLogs([])
    setResults([])
    setErrorMsg('')
    setUploadedNames([])
    setScriptStatus('')
    setScripts([])
    setProgress({ currentStage: null, currentStatus: null })
    setActiveTab('progress')
    if (esRef.current) { esRef.current.close(); esRef.current = null }
  }

  // ── Pipeline state ───────────────────────────────────────────────────────
  const [files, setFiles] = useState([])
  const [phase, setPhase] = useState(PHASE.IDLE)
  const [logs, setLogs] = useState([])
  const [results, setResults] = useState([])
  const [errorMsg, setErrorMsg] = useState('')
  const [uploadedNames, setUploadedNames] = useState([])
  const [ragStatus, setRagStatus] = useState('') // '' | 'refreshing' | 'done' | 'error'
  const [scriptStatus, setScriptStatus] = useState('') // '' | 'generating' | 'done' | 'error'
  const [scripts, setScripts] = useState([])
  const [scriptsLoading, setScriptsLoading] = useState(false)
  const [scriptsError, setScriptsError] = useState('')
  const [selectedScriptName, setSelectedScriptName] = useState('')
  const [selectedLlm, setSelectedLlm] = useState(DEFAULT_LLM)
  const [progress, setProgress] = useState({ currentStage: null, currentStatus: null })
  const [activeTab, setActiveTab] = useState('progress') // 'progress' | 'results' | 'scripts' | 'logs'
  const esRef = useRef(null)

  // Poll status on mount — only when authenticated
  useEffect(() => {
    if (!isAuthenticated) return
    fetch('/status', { credentials: 'include' })
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
  }, [isAuthenticated]) // eslint-disable-line react-hooks/exhaustive-deps

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
    fetch('/results', { credentials: 'include' })
      .then(r => r.json())
      .then(data => setResults(data.test_cases || []))
      .catch(() => setErrorMsg('Failed to load results.'))
  }, [])

  const loadScripts = useCallback(async () => {
    setScriptsLoading(true)
    setScriptsError('')
    try {
      const res = await fetch('/scripts', { credentials: 'include' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to load scripts')
      const list = data.scripts || []
      setScripts(list)
      setSelectedScriptName(prev => prev || (list[0]?.name || ''))
    } catch (e) {
      setScripts([])
      setScriptsError(e.message)
    } finally {
      setScriptsLoading(false)
    }
  }, [])

  const handleUploadAndRun = useCallback(async () => {
    if (files.length === 0) return

    setLogs([])
    setResults([])
    setErrorMsg('')
    setProgress({ currentStage: null, currentStatus: null })
    setActiveTab('logs')

    // ── Upload ──────────────────────────────────────────────────────────────
    setPhase(PHASE.UPLOADING)
    const form = new FormData()
    files.forEach(f => form.append('files', f))

    let uploadRes
    try {
      const res = await fetch('/upload', { method: 'POST', body: form, credentials: 'include' })
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
      const res = await fetch('/run', { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error('Failed to start pipeline')
    } catch (e) {
      setErrorMsg(e.message)
      setPhase(PHASE.ERROR)
      return
    }

    setPhase(PHASE.RUNNING)
    openStream()
  }, [files, openStream])

  const handleReset = async () => {
    if (esRef.current) esRef.current.close()
    setFiles([])
    setPhase(PHASE.IDLE)
    setLogs([])
    setResults([])
    setErrorMsg('')
    setUploadedNames([])
    setScriptStatus('')
    setScripts([])
    // Tell backend to clear its done-state so old results don't reload on remount
    try { await fetch('/reset', { method: 'POST', credentials: 'include' }) } catch (_) {}
    setScriptsLoading(false)
    setScriptsError('')
    setSelectedScriptName('')
    setProgress({ currentStage: null, currentStatus: null })
    setActiveTab('progress')
  }

  const handleRefreshRag = useCallback(async () => {
    setRagStatus('refreshing')
    try {
      const res = await fetch('/rag-index', { method: 'DELETE', credentials: 'include' })
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
        credentials: 'include',
        body: JSON.stringify({ provider: opt.provider, model: opt.model }),
      })
    } catch (_) {}
  }, [])

  const handleDownload = () => {
    window.open('/download', '_blank')
  }

  const handleGenerateScripts = useCallback(async () => {
    setScriptStatus('generating')
    setScriptsError('')
    setActiveTab('scripts')
    setProgress({ currentStage: 'generating_scripts', currentStatus: 'running' })
    try {
      const res = await fetch('/generate-scripts', { method: 'POST', credentials: 'include' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Script generation failed')
      setLogs(prev => [...prev, `[SCRIPT] ${data.count} Playwright script(s) generated ✅`])
      setProgress({ currentStage: 'generating_scripts', currentStatus: 'done' })
      setScriptStatus('done')
      await loadScripts()
    } catch (e) {
      setLogs(prev => [...prev, `[SCRIPT ERROR] ${e.message}`])
      setProgress({ currentStage: 'generating_scripts', currentStatus: 'error' })
      setScriptStatus('error')
      setScriptsError(e.message)
    }
  }, [loadScripts])

  const handleDownloadScripts = () => {
    window.open('/download-scripts', '_blank')
  }

  useEffect(() => {
    if (activeTab === 'scripts' && scriptStatus === 'done' && scripts.length === 0 && !scriptsLoading) {
      loadScripts()
    }
  }, [activeTab, scriptStatus, scripts.length, scriptsLoading, loadScripts])

  const isRunning = phase === PHASE.RUNNING || phase === PHASE.UPLOADING
  const canRun = files.length > 0 && !isRunning

  // Auth gates
  if (isAuthenticated === null) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#0f1117', color: '#8892a4', fontSize: '1rem' }}>
        Checking session…
      </div>
    )
  }
  if (isAuthenticated === false) {
    return <Login onLogin={handleLogin} />
  }

  return (
    <div className={styles.layout}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.headerBrand}>
            <div className={styles.infosysLabel}>INFOSYS</div>
            <h1 className={styles.headerTitle}>AI Test Automation Platform</h1>
            <p className={styles.headerSubtitle}>Powered by AI + RAG</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <StatusBadge phase={phase} />
            <span style={{ color: 'white', fontSize: '0.85rem', fontWeight: 500 }}>
              👤 {currentUser}
            </span>
            <button
              onClick={handleLogout}
              style={{ padding: '0.35rem 0.85rem', background: 'transparent', border: '1px solid rgba(255,255,255,0.6)', borderRadius: '6px', color: 'white', fontSize: '0.8rem', cursor: 'pointer', fontWeight: 500 }}
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        {/* ── Left Panel (Controls) ──────────────────────────────────────── */}
        <aside className={styles.leftPanel}>
          <div className={styles.panelSection}>
            <h3 className={styles.sectionTitle}>📁 Upload Files</h3>
            <UploadSection
              files={files}
              setFiles={setFiles}
              disabled={isRunning}
            />
          </div>

          <div className={styles.panelSection}>
            <h3 className={styles.sectionTitle}>⚙️ Configuration</h3>
            {uploadedNames.length > 0 && (
              <p className={styles.uploadedHint}>
                ✓ {uploadedNames.length} file{uploadedNames.length > 1 ? 's' : ''} uploaded
              </p>
            )}
            <div className={styles.configGroup}>
              <label className={styles.configLabel} htmlFor="llm-select">AI Model</label>
              <select
                id="llm-select"
                className={styles.configSelect}
                value={selectedLlm.model}
                onChange={handleLlmChange}
                disabled={isRunning}
              >
                {LLM_OPTIONS.map(o => (
                  <option key={o.model} value={o.model}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className={styles.panelSection}>
            <h3 className={styles.sectionTitle}>🚀 Actions</h3>
            <button
              className={styles.primaryBtn}
              onClick={handleUploadAndRun}
              disabled={!canRun}
            >
              {phase === PHASE.UPLOADING ? (
                <><Spinner /> Uploading…</>
              ) : phase === PHASE.RUNNING ? (
                <><Spinner /> Running…</>
              ) : (
                '▶ Generate Test Cases'
              )}
            </button>

            <button
              className={styles.secondaryBtn}
              onClick={handleRefreshRag}
              disabled={isRunning || ragStatus === 'refreshing'}
              title="Clear FAISS index and rebuild on next run"
            >
              {ragStatus === 'refreshing' ? <><Spinner /> Clearing…</> :
               ragStatus === 'done'       ? '✅ Cleared' :
               ragStatus === 'error'      ? '❌ Failed' :
               '🔄 Refresh RAG'}
            </button>

            {(phase === PHASE.DONE || phase === PHASE.ERROR) && (
              <button className={styles.secondaryBtn} onClick={handleReset}>
                ↺ Reset
              </button>
            )}

            {phase === PHASE.DONE && results.length > 0 && (
              <>
                <button className={styles.primaryBtn} onClick={handleDownload}>
                  ⬇ Download Excel
                </button>
                <button
                  className={styles.primaryBtn}
                  onClick={handleGenerateScripts}
                  disabled={scriptStatus === 'generating'}
                >
                  {scriptStatus === 'generating'
                    ? <><Spinner /> Generating…</>
                    : '⚡ Generate Scripts'}
                </button>
                {scriptStatus === 'done' && (
                  <button className={styles.primaryBtn} onClick={handleDownloadScripts}>
                    ⬇ Download Scripts
                  </button>
                )}
              </>
            )}
          </div>

          {phase === PHASE.ERROR && (
            <div className={styles.panelSection}>
              <div className={styles.errorAlert}>
                <div className={styles.errorTitle}>❌ Error</div>
                <p className={styles.errorMsg}>{errorMsg}</p>
              </div>
            </div>
          )}
        </aside>

        {/* ── Right Panel (Output - Tabbed) ──────────────────────────────── */}
        <section className={styles.rightPanel}>
          {/* Tab Navigation */}
          <div className={styles.tabBar}>
            <button
              className={`${styles.tab} ${activeTab === 'progress' ? styles.tabActive : ''}`}
              onClick={() => setActiveTab('progress')}
            >
              📊 Progress
            </button>
            {results.length > 0 && (
              <button
                className={`${styles.tab} ${activeTab === 'results' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('results')}
              >
                ✅ Test Cases ({new Set(results.map(r => `${r['Requirement ID']}_${r['Test Name']}`)).size})
              </button>
            )}
            {(scriptStatus === 'done' || scriptStatus === 'generating') && (
              <button
                className={`${styles.tab} ${activeTab === 'scripts' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('scripts')}
              >
                ⚡ Scripts
              </button>
            )}
            {(logs.length > 0 || isRunning) && (
              <button
                className={`${styles.tab} ${activeTab === 'logs' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('logs')}
              >
                📜 Logs
              </button>
            )}
          </div>

          {/* Tab Content */}
          <div className={styles.tabContent}>
            {/* Progress Tab */}
            {activeTab === 'progress' && (
              <div className={styles.tabPane}>
                {(logs.length > 0 || isRunning) ? (
                  <ProgressStatus
                    progress={progress}
                    errorMsg={errorMsg}
                    showLogs={activeTab === 'logs'}
                    onToggleLogs={() => setActiveTab('logs')}
                  />
                ) : (
                  <div className={styles.emptyState}>
                    <span className={styles.emptyIcon}>🧪</span>
                    <p>Upload documents and click "Generate Test Cases" to start the pipeline.</p>
                    <p className={styles.emptyHint}>Supported: PDF, DOCX, TXT, MD</p>
                  </div>
                )}
              </div>
            )}

            {/* Results Tab */}
            {activeTab === 'results' && results.length > 0 && (
              <div className={styles.tabPane}>
                <TestSummary rows={results} scriptStatus={scriptStatus} />
                <ResultsTable rows={results} />
              </div>
            )}

            {/* Scripts Tab */}
            {activeTab === 'scripts' && (scriptStatus === 'done' || scriptStatus === 'generating' || scriptStatus === 'error') && (
              <div className={styles.tabPane}>
                <ScriptViewer
                  scripts={scripts}
                  loading={scriptStatus === 'generating' || scriptsLoading}
                  error={scriptsError}
                  onDownloadAll={handleDownloadScripts}
                  selectedScriptName={selectedScriptName}
                  onSelectScript={setSelectedScriptName}
                />
              </div>
            )}

            {/* Logs Tab */}
            {activeTab === 'logs' && (logs.length > 0 || isRunning) && (
              <div className={styles.tabPane}>
                <LogStream logs={logs} running={isRunning} />
              </div>
            )}
          </div>
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
