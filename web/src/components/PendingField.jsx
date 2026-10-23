import { useEffect, useRef, useState } from 'react'
import { motivoDaConferencia, origemDoCampo } from '../labels'

const CAMPOS_DO_PROFISSIONAL = new Set([
  'requesting_professional_name',
  'council_number',
  'council_state',
  'professional_council',
  'professional_specialty',
])

function valorSugerido(campo, sugestao) {
  if (campo.name === 'requesting_professional_name') return sugestao.label.split(' (')[0]
  if (campo.name === 'council_number') return sugestao.label.match(/(\d+)\)$/)?.[1] ?? ''
  if (campo.name === 'professional_specialty') return sugestao.specialty ?? ''
  return ''
}

export default function PendingField({ campo, sugestoes, ativo, onFocus, onConfirm }) {
  // rascunho é null enquanto ninguém digitou: assim o valor vindo do servidor
  // continua mandando, sem precisar de efeito para sincronizar.
  const [rascunho, setRascunho] = useState(null)
  const entrada = useRef(null)
  const valor = rascunho ?? campo.value ?? ''

  useEffect(() => { if (ativo) entrada.current?.focus() }, [ativo])

  const aplicaveis = CAMPOS_DO_PROFISSIONAL.has(campo.name)
    ? sugestoes.filter((item) => valorSugerido(campo, item))
    : []

  return (
    <div className={`campo ${ativo ? 'campo--ativo' : ''}`} onFocus={() => onFocus(campo.name)}>
      <div className="campo__titulo">
        {campo.number && <span className="campo__numero">{campo.number}</span>}
        <span className="campo__nome">{campo.label}</span>
        <span className="campo__secao">{campo.section}</span>
      </div>

      <div className="campo__linha">
        <input
          ref={entrada}
          className={`campo__valor ${campo.value ? '' : 'campo__valor--vazio'}`}
          value={valor}
          placeholder="digite o valor"
          onChange={(evento) => setRascunho(evento.target.value)}
          onKeyDown={(evento) => {
            if (evento.key === 'Enter') onConfirm(campo.name, valor)
          }}
        />
        <button type="button" className="botao botao--principal" onClick={() => onConfirm(campo.name, valor)}>
          Confirmar
        </button>
      </div>

      <p className="campo__motivo">
        <strong>{motivoDaConferencia(campo)}</strong>
        {campo.source && <span>· {origemDoCampo(campo.source)}</span>}
      </p>

      {aplicaveis.length > 0 && (
        <div className="sugestoes">
          <span className="sugestoes__rotulo">No cadastro:</span>
          {aplicaveis.map((sugestao) => (
            <button
              key={sugestao.label}
              type="button"
              className="sugestao"
              onClick={() => setRascunho(valorSugerido(campo, sugestao))}
            >
              {valorSugerido(campo, sugestao)}
              <small>{sugestao.label}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
