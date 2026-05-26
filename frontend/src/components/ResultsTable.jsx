import { useState, useMemo } from 'react'
import styles from './ResultsTable.module.css'

const COLUMNS = [
  { key: 'Requirement ID', label: 'Req ID', width: 90 },
  { key: 'Test Name', label: 'Test Name', width: 160 },
  { key: 'Test Description', label: 'Description', width: 200 },
  { key: 'Step Name', label: 'Step', width: 120 },
  { key: 'Action', label: 'Action', width: 180 },
  { key: 'Expected Result', label: 'Expected Result', width: 180 },
  { key: 'Quality Score', label: 'Score', width: 60 },
  { key: 'Quality Verdict', label: 'Verdict', width: 80 },
  { key: 'Quality Flags', label: 'Flags', width: 100 },
]

export default function ResultsTable({ rows }) {
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState(null)
  const [sortDir, setSortDir] = useState('asc')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 20

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter(r =>
      Object.values(r).some(v => String(v ?? '').toLowerCase().includes(q))
    )
  }, [rows, search])

  const sorted = useMemo(() => {
    if (!sortCol) return filtered
    return [...filtered].sort((a, b) => {
      const va = String(a[sortCol] ?? '')
      const vb = String(b[sortCol] ?? '')
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    })
  }, [filtered, sortCol, sortDir])

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const pageRows = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
    setPage(0)
  }

  const handleSearch = (e) => {
    setSearch(e.target.value)
    setPage(0)
  }

  const verdictClass = (v) => {
    const val = String(v ?? '').toLowerCase()
    if (val.includes('pass') || val.includes('good')) return styles.verdictPass
    if (val.includes('fail') || val.includes('bad')) return styles.verdictFail
    if (val.includes('warn') || val.includes('review')) return styles.verdictWarn
    return ''
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.toolbar}>
        <input
          className={styles.searchInput}
          type="text"
          placeholder="Search results…"
          value={search}
          onChange={handleSearch}
        />
        <span className={styles.count}>{sorted.length} rows</span>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              {COLUMNS.map(col => (
                <th
                  key={col.key}
                  style={{ minWidth: col.width }}
                  className={styles.th}
                  onClick={() => toggleSort(col.key)}
                >
                  {col.label}
                  <span className={styles.sortIcon}>
                    {sortCol === col.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ' ⇅'}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length} className={styles.empty}>
                  No results found
                </td>
              </tr>
            ) : pageRows.map((row, i) => (
              <tr key={i} className={styles.tr}>
                {COLUMNS.map(col => (
                  <td key={col.key} className={`${styles.td} ${col.key === 'Quality Verdict' ? verdictClass(row[col.key]) : ''}`}>
                    {col.key === 'Quality Score'
                      ? <ScorePill score={row[col.key]} />
                      : <span className={styles.cellText}>{row[col.key] ?? '—'}</span>
                    }
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className={styles.pagination}>
          <button
            className={styles.pageBtn}
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            ‹ Prev
          </button>
          <span className={styles.pageInfo}>
            Page {page + 1} of {totalPages}
          </span>
          <button
            className={styles.pageBtn}
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
          >
            Next ›
          </button>
        </div>
      )}
    </div>
  )
}

function ScorePill({ score }) {
  const val = parseFloat(score)
  if (isNaN(val)) return <span className={styles.cellText}>—</span>
  const pct = Math.min(100, Math.max(0, val * 10))
  const color = val >= 7 ? 'var(--success)' : val >= 4 ? 'var(--warning)' : 'var(--error)'
  return (
    <div className={styles.scorePill} style={{ '--score-color': color }}>
      <div className={styles.scoreBar} style={{ width: `${pct}%`, background: color }} />
      <span className={styles.scoreLabel}>{val.toFixed(1)}</span>
    </div>
  )
}
