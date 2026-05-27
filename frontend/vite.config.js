import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/status': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      '/run': 'http://localhost:8000',
      '/stream': 'http://localhost:8000',
      '/results': 'http://localhost:8000',
      '/download': 'http://localhost:8000',
      '/rag-index': 'http://localhost:8000',
      '/llm-options': 'http://localhost:8000',
      '/generate-scripts': 'http://localhost:8000',
      '/download-scripts': 'http://localhost:8000',
      '/scripts': 'http://localhost:8000',
      '/set-llm': 'http://localhost:8000',
    },
  },
})
