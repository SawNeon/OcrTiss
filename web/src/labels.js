/* A tela é usada por quem atende, não por quem construiu o sistema:
   cada termo técnico vira a frase que explica o que fazer. */

const ORIGENS = {
  text_layer: 'veio do arquivo digital',
  ocr: 'leitura automática',
  llm: 'leitura automática',
  checkbox: 'marcação no formulário',
  registry: 'cadastro de cooperados',
  human: 'conferido por você',
}

const LEITURAS = {
  text_layer: 'Guia digital: os dados vieram do próprio arquivo, sem leitura de imagem.',
  template: 'Leitura automática do formulário.',
  llm: 'Leitura automática do texto da guia.',
  hybrid: 'Leitura automática do formulário e do texto.',
  manual: 'Não foi possível ler esta guia: os campos precisam ser digitados.',
}

const AVISOS = [
  [/resolução baixa/i, 'A imagem está em baixa resolução. Campos preenchidos à mão podem não ter sido lidos.'],
  [/layout não reconhecido/i, 'Este formulário não é um dos modelos conhecidos, então os campos em caixinhas não foram lidos.'],
  [/modelo de visão indisponível/i, 'A leitura de texto automática não está disponível agora.'],
  [/carimbo diverge/i, 'O carimbo do profissional não bate com o que está escrito no formulário.'],
  [/cadastro sugere/i, 'Há um cooperado parecido no cadastro. Confira a sugestão no campo.'],
  [/nenhum campo extraído/i, 'Nada pôde ser lido automaticamente nesta página.'],
  [/página em paisagem/i, null],
  [/imagem fatiada/i, null],
]

export function origemDoCampo(origem) {
  return ORIGENS[origem] ?? origem ?? ''
}

export function comoFoiLida(estrategia) {
  return LEITURAS[estrategia] ?? 'Leitura automática.'
}

export function avisoEmPortugues(aviso) {
  for (const [padrao, texto] of AVISOS) {
    if (padrao.test(aviso)) return texto
  }
  return aviso
}

/** Por que este campo caiu na fila de conferência. */
export function motivoDaConferencia(campo) {
  if (campo.note) return campo.note
  if (!campo.value) return 'Não foi lido'
  if (campo.validated === false) return 'O valor lido não tem o formato esperado'
  if (campo.confidence != null && campo.confidence < 0.6) return 'Leitura pouco nítida'
  return 'Confirme se está correto'
}
