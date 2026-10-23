import { useCallback, useEffect, useState } from 'react'
import BrandBar from './components/BrandBar'
import UploadPanel from './components/UploadPanel'
import ReviewPanel from './components/ReviewPanel'
import DocumentPanel from './components/DocumentPanel'
import RecentList from './components/RecentList'
import { correctField, health, listExtractions, readExtraction, registerDecision, uploadGuide } from './api'
import './styles.css'

export default function App() {
  const [status, setStatus] = useState(null)
  const [extraction, setExtraction] = useState(null)
  const [recent, setRecent] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const refreshRecent = useCallback(() => {
    listExtractions().then(setRecent).catch(() => setRecent([]))
  }, [])

  useEffect(() => { health().then(setStatus).catch(() => setStatus(null)) }, [])
  useEffect(() => { refreshRecent() }, [refreshRecent])

  const run = async (action) => {
    setError(null)
    setBusy(true)
    try {
      setExtraction(await action())
      refreshRecent()
    } catch (falha) {
      setError(falha.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <BrandBar status={status} />

      <main className="conteudo">
        <UploadPanel busy={busy} onUpload={(arquivo) => run(() => uploadGuide(arquivo))} />

        {error && <p className="erro">{error}</p>}

        <RecentList items={recent} currentId={extraction?.id} onOpen={(id) => run(() => readExtraction(id))} />

        {extraction && (
          <div className="trabalho">
            <ReviewPanel
              extraction={extraction}
              onConfirm={(nome, valor) => run(() => correctField(extraction.id, nome, valor))}
              onDecision={(decisao, nota) => run(() => registerDecision(extraction.id, decisao, nota))}
            />
            <DocumentPanel extraction={extraction} />
          </div>
        )}
      </main>

      <footer className="rodape">Unimed Varginha · conferência assistida de guias</footer>
    </div>
  )
}
