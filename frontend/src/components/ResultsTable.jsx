import { useState, useMemo } from 'react'
import styles from './ResultsTable.module.css'

export default function ResultsTable({ rows }) {
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('name')

  // Group rows by test case (same test can have multiple steps)
  const testMap = useMemo(() => {
    const map = new Map()
    rows.forEach(row => {
      const key = `${row['Requirement ID']}_${row['Test Name']}`
      if (!map.has(key)) {
        map.set(key, {
          requirementId: row['Requirement ID'],
          testName: row['Test Name'],
          testDescription: row['Test Description'] || '',
          testType: row['Test Type'] || 'functional',
          score: row['Quality Score'],
          verdict: row['Quality Verdict'],
          flags: row['Quality Flags'],
          steps: []
        })
      }
      map.get(key).steps.push({
        name: row['Step Name'],
        action: row['Action'],
        expected: row['Expected Result']
      })
    })
    return map
  }, [rows])

  const tests = Array.from(testMap.values())

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return tests
    return tests.filter(t =>
      t.testName.toLowerCase().includes(q) ||
      t.testDescription.toLowerCase().includes(q) ||
      t.requirementId.toLowerCase().includes(q)
    )
  }, [tests, search])

  const sorted = useMemo(() => {
    const arr = [...filtered]
    if (sortBy === 'name') {
      arr.sort((a, b) => a.testName.localeCompare(b.testName))
    } else if (sortBy === 'score') {
      arr.sort((a, b) => (parseFloat(b.score) || 0) - (parseFloat(a.score) || 0))
    }
    return arr
  }, [filtered, sortBy])

  const handleSearch = (e) => {
    setSearch(e.target.value)
  }

  const getVerdictClass = (verdict) => {
    const v = String(verdict ?? '').toLowerCase()
    if (v.includes('pass') || v.includes('good')) return styles.borderPass
    if (v.includes('fail') || v.includes('bad')) return styles.borderFail
    if (v.includes('warn') || v.includes('review')) return styles.borderWarn
    return styles.borderNeutral
  }

  const getScoreColor = (score) => {
    const val = parseFloat(score)
    if (isNaN(val)) return 'var(--text-tertiary)'
    if (val >= 7) return '#10b981'  // green
    if (val >= 4) return '#f59e0b'  // orange
    return '#ef4444'  // red
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.toolbar}>
        <input
          className={styles.searchInput}
          type="text"
          placeholder="Search test cases…"
          value={search}
          onChange={handleSearch}
        />
        <div className={styles.sortButtons}>
          <button
            className={`${styles.sortBtn} ${sortBy === 'name' ? styles.active : ''}`}
            onClick={() => setSortBy('name')}
          >
            📋 Name
          </button>
          <button
            className={`${styles.sortBtn} ${sortBy === 'score' ? styles.active : ''}`}
            onClick={() => setSortBy('score')}
          >
            ⭐ Score
          </button>
        </div>
        <span className={styles.count}>{sorted.length} cases</span>
      </div>

      {sorted.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>📭</span>
          <p>No test cases match your search.</p>
        </div>
      ) : (
        <div className={styles.grid}>
          {sorted.map((test, idx) => (
            <div
              key={idx}
              className={`${styles.card} ${getVerdictClass(test.verdict)}`}
            >
              <div className={styles.cardHeader}>
                <div className={styles.cardTitle}>
                  <div className={styles.testName}>{test.testName}</div>
                  <div className={styles.testReqId}>{test.requirementId}</div>
                </div>
                <div className={styles.cardScore} style={{ color: getScoreColor(test.score) }}>
                  {parseFloat(test.score || 0).toFixed(1)}
                </div>
              </div>

              {test.testDescription && (
                <div className={styles.cardDescription}>{test.testDescription}</div>
              )}

              <div className={styles.cardMeta}>
                <span className={`${styles.badge} ${styles[`badge${test.testType}`]}`}>
                  {test.testType}
                </span>
                <span className={`${styles.verdict} ${styles[`verdict${getVerdictName(test.verdict)}`]}`}>
                  {test.verdict || 'Pending'}
                </span>
              </div>

              <div className={styles.stepsSection}>
                <div className={styles.stepsTitle}>Steps ({test.steps.length})</div>
                <div className={styles.stepsList}>
                  {test.steps.map((step, i) => (
                    <div key={i} className={styles.step}>
                      <div className={styles.stepNum}>{i + 1}</div>
                      <div className={styles.stepContent}>
                        {step.name && <div className={styles.stepName}>{step.name}</div>}
                        {step.action && <div className={styles.stepAction}>→ {step.action}</div>}
                        {step.expected && <div className={styles.stepExpected}>✓ {step.expected}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {test.flags && (
                <div className={styles.flags}>
                  <span className={styles.flagsLabel}>Flags:</span>
                  <span className={styles.flagsValue}>{test.flags}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function getVerdictName(verdict) {
  const v = String(verdict ?? '').toLowerCase()
  if (v.includes('pass') || v.includes('good')) return 'Pass'
  if (v.includes('fail') || v.includes('bad')) return 'Fail'
  if (v.includes('warn') || v.includes('review')) return 'Warn'
  return 'Neutral'
}
