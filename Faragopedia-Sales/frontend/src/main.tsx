import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { OperationToastProvider } from './OperationToastContext'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OperationToastProvider>
      <App />
    </OperationToastProvider>
  </React.StrictMode>,
)
