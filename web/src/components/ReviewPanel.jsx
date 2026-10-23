import { useState } from 'react'
import PendingField from './PendingField'
import { avisoEmPortugues, comoFoiLida, origemDoCampo } from '../labels'
import { tissXmlUrl } from '../api'

const SELOS = { human: 'selo--humano', registry: 'selo--cadastro' }

export default function ReviewPanel({ extraction, onConfirm, onDecision }) {
  const [observacao, setObservacao] = useState('')
  const [emFoco, setEmFoco] = useState(null)

  const payload = extraction.payload
  const campos = payload.fields ?? []

  const [extras, setExtras] = useState(() => new Set())

  const pendentes = campos.filter((campo) => campo.needs_review || extras.has(campo.name))
  const conferidos = campos.filter((campo) => campo.value && !campo.needs_review && !extras.has(campo.name))
  const vazios = campos.filter((campo) => !campo.value && !campo.needs_review && !extras.has(campo.name))
  const procedimentos = (payload.procedures ?? []).filter((linha) => linha.code?.value)

  const total = pendentes.length + conferidos.length
  const progresso = total ? Math.round((conferidos.length / total) * 100) : 0
  const avisos = (payload.warnings ?? []).map(avisoEmPortugues).filter(Boolean)
  const decisao = payload.decision

  const ativo = emFoco ?? pendentes[0]?.name

  function confirmar(nome, valor) {
    const indice = pendentes.findIndex((campo) => campo.name === nome)
    const proximo = pendentes[indice + 1] ?? pendentes[indice - 1]
    setExtras((atual) => {
      if (!atual.has(nome)) return atual
      const restantes = new Set(atual)
      restantes.delete(nome)
      return restantes
    })
    setEmFoco(proximo?.name ?? null)
    onConfirm(nome, valor)
  }

  return (
    <section className="cartao">
      <header className="revisao__topo">
        <div className="revisao__arquivo">
          <h1>{extraction.original_name}</h1>
          <span className="revisao__origem">{comoFoiLida(payload.strategy)}</span>
        </div>

        <div className="progresso">
          <div className="progresso__texto">
            <span>
              <span className="progresso__numero">{conferidos.length}</span> de {total} campos conferidos
            </span>
            <span>{progresso}%</span>
          </div>
          <div className="progresso__barra">
            <div className="progresso__preenchido" style={{ width: `${progresso}%` }} />
          </div>
        </div>

        {avisos.length > 0 && (
          <div className="avisos">
            <ul>
              {avisos.map((aviso) => <li key={aviso}>{aviso}</li>)}
            </ul>
          </div>
        )}
      </header>

      {pendentes.length > 0 ? (
        <div className="secao">
          <h2 className="secao__titulo">
            Conferir <span className="secao__contador">{pendentes.length}</span>
          </h2>
          <p className="secao__ajuda">Ajuste o que estiver errado e pressione Enter para ir ao próximo.</p>
          {pendentes.map((campo) => (
            <PendingField
              key={campo.name}
              campo={campo}
              sugestoes={payload.suggestions ?? []}
              ativo={campo.name === ativo}
              onFocus={setEmFoco}
              onConfirm={confirmar}
            />
          ))}
        </div>
      ) : (
        <div className="secao">
          <h2 className="secao__titulo">
            Tudo conferido <span className="secao__contador secao__contador--ok">✓</span>
          </h2>
          <p className="secao__ajuda">Nenhum campo pendente. Você pode aprovar a guia.</p>
        </div>
      )}

      {vazios.length > 0 && (
        <div className="secao">
          <details>
            <summary className="vazios__resumo">
              {vazios.length} campos não preenchidos na guia
            </summary>
            <p className="secao__ajuda">
              Em branco no papel. Clique para preencher algum que precise ir para o Cardio.
            </p>
            <div className="vazios__lista">
              {vazios.map((campo) => (
                <button
                  key={campo.name}
                  type="button"
                  className="vazio"
                  onClick={() => setExtras((atual) => new Set(atual).add(campo.name))}
                >
                  {campo.label}
                </button>
              ))}
            </div>
          </details>
        </div>
      )}

      {conferidos.length > 0 && (
        <div className="secao">
          <h2 className="secao__titulo">Conferidos</h2>
          <table className="conferidos">
            <tbody>
              {conferidos.map((campo) => (
                <tr key={campo.name}>
                  <td className="conferidos__campo">{campo.label}</td>
                  <td className="conferidos__valor">
                    {campo.value}
                    {SELOS[campo.source] && (
                      <span className={`selo ${SELOS[campo.source]}`}>{origemDoCampo(campo.source)}</span>
                    )}
                  </td>
                  <td style={{ width: 70, textAlign: 'right' }}>
                    <button
                      type="button"
                      className="conferidos__editar"
                      onClick={() => {
                        setExtras((atual) => new Set(atual).add(campo.name))
                        setEmFoco(campo.name)
                      }}
                    >
                      alterar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {procedimentos.length > 0 && (
        <div className="secao">
          <h2 className="secao__titulo">Procedimentos solicitados</h2>
          <table className="procedimentos">
            <thead>
              <tr><th>Tabela</th><th>Código</th><th>Descrição</th><th>Qtde</th></tr>
            </thead>
            <tbody>
              {procedimentos.map((linha) => (
                <tr key={linha.row}>
                  <td>{linha.table?.value ?? '—'}</td>
                  <td className={linha.code?.needs_review ? 'conferir' : ''}>{linha.code?.value ?? '—'}</td>
                  <td>{linha.description?.value ?? '—'}</td>
                  <td>{linha.requested_quantity?.value ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer className="decisao">
        {decisao ? (
          <p className="aprovada">
            Guia <strong>{decisao.status}</strong>
            {decisao.registered_professional && <> · cooperado registrado: {decisao.registered_professional}</>}
          </p>
        ) : (
          <>
            {pendentes.length > 0 && (
              <span className="pendencia">
                {pendentes.length} {pendentes.length === 1 ? 'campo ainda precisa' : 'campos ainda precisam'} de conferência
              </span>
            )}
            <input
              className="decisao__observacao"
              placeholder="Observação para a auditoria (opcional)"
              value={observacao}
              onChange={(evento) => setObservacao(evento.target.value)}
            />
          </>
        )}

        <div className="decisao__botoes">
          <button
            type="button"
            className="botao botao--principal"
            disabled={pendentes.length > 0 || Boolean(decisao)}
            onClick={() => onDecision('aprovado', observacao)}
          >
            Aprovar guia
          </button>
          <button
            type="button"
            className="botao botao--recusar"
            disabled={Boolean(decisao)}
            onClick={() => onDecision('negado', observacao)}
          >
            Negar
          </button>
          <button
            type="button"
            className="botao"
            disabled={Boolean(decisao)}
            onClick={() => onDecision('pendente', observacao)}
          >
            Deixar pendente
          </button>
          <a className="botao" href={tissXmlUrl(extraction.id)} target="_blank" rel="noreferrer">
            Baixar XML
          </a>
        </div>
      </footer>
    </section>
  )
}
