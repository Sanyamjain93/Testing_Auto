import { useCallback, useState } from 'react'
import styles from './UploadSection.module.css'

const ALLOWED = ['.pdf', '.docx', '.txt', '.md', '.xlsx']

function validateFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  return ALLOWED.includes(ext)
}

export default function UploadSection({ files, setFiles, disabled }) {
  const [dragging, setDragging] = useState(false)
  const [rejectMsg, setRejectMsg] = useState('')

  const addFiles = useCallback((incoming) => {
    setRejectMsg('')
    const valid = []
    const invalid = []
    for (const f of incoming) {
      if (validateFile(f)) valid.push(f)
      else invalid.push(f.name)
    }
    if (invalid.length) {
      setRejectMsg(`Unsupported: ${invalid.join(', ')}`)
    }
    if (valid.length) {
      setFiles(prev => {
        const existing = new Set(prev.map(f => f.name))
        return [...prev, ...valid.filter(f => !existing.has(f.name))]
      })
    }
  }, [setFiles])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    addFiles([...e.dataTransfer.files])
  }, [disabled, addFiles])

  const onDragOver = (e) => {
    e.preventDefault()
    if (!disabled) setDragging(true)
  }

  const onDragLeave = () => setDragging(false)

  const onInputChange = (e) => {
    addFiles([...e.target.files])
    e.target.value = ''
  }

  const removeFile = (name) => {
    setFiles(prev => prev.filter(f => f.name !== name))
  }

  const fileIcon = (name) => {
    const ext = name.split('.').pop().toLowerCase()
    const map = { pdf: '📄', docx: '📝', doc: '📝', txt: '📃', md: '📋' }
    return map[ext] || '📁'
  }

  return (
    <div className={styles.wrapper}>
      <label
        className={`${styles.dropZone} ${dragging ? styles.dragging : ''} ${disabled ? styles.disabled : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
      >
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md,.xlsx"
          className={styles.hiddenInput}
          onChange={onInputChange}
          disabled={disabled}
        />
        <span className={styles.dropIcon}>📂</span>
        <span className={styles.dropMain}>
          {dragging ? 'Drop files here' : 'Drag & drop files'}
        </span>
        <span className={styles.dropSub}>
          or <span className={styles.browseLink}>browse</span> · PDF, DOCX, TXT, MD, XLSX
        </span>
      </label>

      {rejectMsg && (
        <p className={styles.rejectMsg}>⚠ {rejectMsg}</p>
      )}

      {files.length > 0 && (
        <ul className={styles.fileList}>
          {files.map(f => (
            <li key={f.name} className={styles.fileItem}>
              <span className={styles.fileIcon}>{fileIcon(f.name)}</span>
              <span className={styles.fileName}>{f.name}</span>
              <span className={styles.fileSize}>{formatBytes(f.size)}</span>
              {!disabled && (
                <button
                  className={styles.removeBtn}
                  onClick={() => removeFile(f.name)}
                  title="Remove"
                >
                  ✕
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
