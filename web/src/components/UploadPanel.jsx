import { useRef, useState } from 'react'

export default function UploadPanel({ onUpload, busy }) {
  const input = useRef(null)
  const [arrastando, setArrastando] = useState(false)

  function enviar(arquivos) {
    if (arquivos && arquivos.length) onUpload(arquivos[0])
  }

  return (
    <div
      className={`entrada ${arrastando ? 'entrada--ativa' : ''} ${busy ? 'entrada--ocupada' : ''}`}
      onDragOver={(evento) => { evento.preventDefault(); setArrastando(true) }}
      onDragLeave={() => setArrastando(false)}
      onDrop={(evento) => { evento.preventDefault(); setArrastando(false); enviar(evento.dataTransfer.files) }}
      onClick={() => !busy && input.current?.click()}
    >
      <input
        ref={input}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp"
        hidden
        onChange={(evento) => enviar(evento.target.files)}
      />
      <strong className="entrada__titulo">
        {busy ? 'Lendo a guia…' : 'Solte a guia aqui ou clique para escolher'}
      </strong>
      <span className="entrada__ajuda">PDF ou foto · até 25 MB</span>
    </div>
  )
}
