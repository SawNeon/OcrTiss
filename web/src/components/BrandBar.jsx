export default function BrandBar({ status }) {
  return (
    <header className="topo">
      <div className="marca">
        <span className="marca__nome">Unimed</span>
        <span className="marca__unidade">Varginha</span>
      </div>
      <div className="topo__divisor" />
      <span className="topo__titulo">Conferência de guias</span>
      {status && (
        <div className="topo__estado">
          <span className={`ponto ${status.llm_enabled ? '' : 'ponto--off'}`} />
          {status.llm_enabled ? 'leitura completa' : 'leitura local'}
        </div>
      )}
    </header>
  )
}
