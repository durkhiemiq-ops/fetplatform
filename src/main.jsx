import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryProvider } from './lib/QueryProvider'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryProvider>
      <App />
    </QueryProvider>
  </React.StrictMode>,
)