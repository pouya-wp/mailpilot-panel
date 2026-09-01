import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to IPv4 loopback. With the default ("localhost") Vite listened on
    // ::1 only, so http://127.0.0.1:<port> was refused.
    host: '127.0.0.1',
    // Dedicated port: 5173-5175 are taken by other dev servers on this machine.
    // strictPort keeps the URL predictable instead of silently drifting.
    port: Number(process.env.PORT) || 4300,
    strictPort: true,
    open: true,
    // Same path in dev as in production, where nginx proxies /api to the
    // backend — so the client never needs to know where it is running, and
    // there is no environment-specific base URL to get wrong.
    proxy: {
      // the Python API (backend/): auth, campaigns, contacts, agents, stats…
      '/api': {
        target: process.env.API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        // the dashboard's live feed is server-sent events; buffering the
        // proxy response would hold every frame until the stream closed
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
            }
          })
        },
      },
      // the Node text-to-speech service the support agent talks through,
      // kept on its own path now that /api belongs to the Python backend
      '/tts': {
        target: process.env.TTS_TARGET || 'http://127.0.0.1:8787',
        changeOrigin: true,
        // the voice server's own routes are /api/tts and /api/tts/health
        rewrite: (path) => path.replace(/^\/tts/, '/api/tts'),
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4301,
    strictPort: true,
  },
})
