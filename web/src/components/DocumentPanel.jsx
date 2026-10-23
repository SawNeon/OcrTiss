import { useState } from 'react'
import { pageImageUrl } from '../api'

const NIVEIS = [100, 150, 220, 320]

export default function DocumentPanel({ extraction }) {
  const [nivel, setNivel] = useState(0)

  return (
    <aside className="cartao documento">
      <div className="documento__topo">
        <h2>Guia recebida</h2>
        <span className="revisao__origem">{extraction.page_count} pág.</span>
        <div className="documento__zoom">
          <button
            type="button"
            onClick={() => setNivel((atual) => Math.max(0, atual - 1))}
            disabled={nivel === 0}
            aria-label="Diminuir"
          >
            −
          </button>
          <button
            type="button"
            onClick={() => setNivel((atual) => Math.min(NIVEIS.length - 1, atual + 1))}
            disabled={nivel === NIVEIS.length - 1}
            aria-label="Aumentar"
          >
            +
          </button>
        </div>
      </div>
      <div className="documento__moldura">
        <img src={pageImageUrl(extraction.id)} alt="Imagem da guia" style={{ width: `${NIVEIS[nivel]}%` }} />
      </div>
    </aside>
  )
}
