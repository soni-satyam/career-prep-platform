import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './lib/auth'
import { FeaturesProvider } from './lib/features'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <FeaturesProvider>
          <App />
        </FeaturesProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
