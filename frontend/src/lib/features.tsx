import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { featuresApi } from './api'

type Flags = Record<string, boolean>

const FeaturesContext = createContext<{ flags: Flags; loading: boolean; enabled: (key: string) => boolean }>({
  flags: {},
  loading: true,
  enabled: () => true,
})

export function FeaturesProvider({ children }: { children: ReactNode }) {
  const [flags, setFlags] = useState<Flags>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    featuresApi
      .list()
      .then((list) => {
        const map: Flags = {}
        list.forEach((f) => {
          map[f.key] = f.enabled
        })
        setFlags(map)
      })
      .catch(() => setFlags({}))
      .finally(() => setLoading(false))
  }, [])

  const enabled = (key: string) => flags[key] !== false // default true if unknown

  return (
    <FeaturesContext.Provider value={{ flags, loading, enabled }}>
      {children}
    </FeaturesContext.Provider>
  )
}

export function useFeatures() {
  return useContext(FeaturesContext)
}
