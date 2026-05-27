import styles from './TestSummary.module.css'

export default function TestSummary({ rows, scriptStatus }) {
  // Group rows by test to get unique test cases
  const testMap = new Map()
  rows.forEach(row => {
    const key = `${row['Requirement ID']}_${row['Test Name']}`
    if (!testMap.has(key)) {
      testMap.set(key, row)
    }
  })

  const uniqueTests = Array.from(testMap.values())
  const requirements = new Set(rows.map(r => r['Requirement ID']))
  
  // Calculate coverage (unique test cases / unique requirements * 100)
  const coverage = requirements.size > 0 
    ? Math.round((uniqueTests.length / requirements.size) * 100) 
    : 0

  return (
    <div className={styles.summary}>
      <div className={styles.metrics}>
        <div className={styles.metric}>
          <div className={styles.metricValue}>{requirements.size}</div>
          <div className={styles.metricLabel}>Requirements</div>
        </div>
        <div className={styles.metric}>
          <div className={styles.metricValue}>{uniqueTests.length}</div>
          <div className={styles.metricLabel}>Test Cases</div>
        </div>
        <div className={styles.metric}>
          <div className={styles.metricValue}>{coverage}%</div>
          <div className={styles.metricLabel}>Coverage</div>
        </div>
        <div className={styles.metric}>
          <div className={`${styles.metricValue} ${styles[scriptStatus === 'done' ? 'success' : 'pending']}`}>
            {scriptStatus === 'done' ? '✅' : '○'}
          </div>
          <div className={styles.metricLabel}>Scripts</div>
        </div>
      </div>
    </div>
  )
}
