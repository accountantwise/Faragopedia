import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '../')
  
  // Extract hostname if a full URL is provided for allowedHosts
  const rawAllowedHost = env.VITE_ALLOWED_HOST || process.env.VITE_ALLOWED_HOST;
  const allowedHost = rawAllowedHost 
    ? rawAllowedHost.replace(/^https?:\/\//, '').split('/')[0]
    : null

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      allowedHosts: true,
      proxy: {
        // This proxies all requests starting with /api to the backend container
        '/api': {
          target: 'http://backend:8300',
          changeOrigin: true,
          secure: false,
        }
      },
      watch: {
        usePolling: true,
      },
    },
  }
})
