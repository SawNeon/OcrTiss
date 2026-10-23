# TISS OCR

Lê guias médicas em **PDF ou imagem** e devolve os campos estruturados, com origem,
confiança e validação por campo. A leitura dos campos codificados (carteirinha,
código do procedimento, CRM, CBO, datas) é **local**: não depende de nuvem nem de IA
generativa. O modelo de visão é opcional e cobre apenas texto livre.

## Como rodar

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m uvicorn app.main:app --port 8077
```

Abra `http://127.0.0.1:8077/` — a interface de revisão é servida pela própria API
quando `web/dist` existe.

Para desenvolver o front com recarga automática:

```bash
npm install --prefix web
npm run dev --prefix web
```

O Vite sobe em `http://localhost:5173` e encaminha `/api` para a porta 8077.

## Configuração (`.env`)

| Variável | Padrão | Para quê |
|---|---|---|
| `TEMPLATE_READER_ENABLED` | `true` | Leitura local por gabarito |
| `LLM_FALLBACK_ENABLED` | `false` | Leitura de texto livre por modelo de visão |
| `OPENAI_API_KEY` | — | Só necessária com a flag acima ligada |
| `OPENAI_MODEL` | `gpt-4o` | Modelo usado no texto livre |
| `RENDER_DPI` | `300` | Resolução de renderização da página |

Com `LLM_FALLBACK_ENABLED=false` nenhuma imagem sai da máquina.

## Tabelas oficiais

Coloque os arquivos em `data/`, um código por linha:

- `data/tuss.txt` — procedimentos
- `data/cid10.txt` — diagnósticos

São usados para validar o que foi lido: entre os candidatos de cada caractere, o
sistema escolhe a combinação que existe na tabela. Os arquivos que acompanham o
repositório são exemplos curtos; substitua pelos oficiais.

## Modelo de reconhecimento

O classificador de caractere fica em `models/character_mlp.pkl`. Para treinar de novo:

```bash
venv\Scripts\python.exe scripts\build_cell_dataset.py --guides 70 --validation 15
venv\Scripts\python.exe scripts\train_character_model.py --dataset data\cells.npz
```

O treino usa guias sintéticas geradas pelo próprio projeto, com valores conhecidos —
nenhum dado real de paciente é necessário.

## Medir a precisão

```bash
venv\Scripts\python.exe scripts\generate_synthetic_dataset.py DATASET
venv\Scripts\python.exe scripts\evaluate_local_reader.py DATASET --profile scan_good
```

Última medição (guias sintéticas, 300 dpi): 60% dos campos codificados exatos,
86% dos caracteres, zero valores inventados.

## API

| Rota | Para quê |
|---|---|
| `GET /api/health` | Estado e formatos aceitos |
| `POST /api/extractions` | Envia a guia (campo `file`) e recebe os campos |
| `GET /api/extractions` | Lista as processadas na sessão |
| `GET /api/extractions/{id}` | Resultado completo |
| `GET /api/extractions/{id}/page.png` | Imagem da página, para conferência |
| `PATCH /api/extractions/{id}/fields/{campo}` | Correção do revisor |
| `POST /api/extractions/{id}/decision` | Aprovar, negar ou deixar pendente |
| `GET /api/extractions/{id}/tiss.xml` | Mensagem TISS (rascunho) |

Documentação interativa em `/docs`.

## Cadastro de profissionais e aprendizado

Importe a planilha de cooperados uma vez:

```bash
venv\Scripts\python.exe scripts\import_professionals.py data\profissionais.csv
```

Colunas aceitas (sem distinção de acento ou maiúscula): `nome`, `crm`, `uf`, `especialidade`.
Também lê `.xlsx` (use `--sheet` para escolher a aba).

A partir daí, o cadastro é consultado em toda leitura:

- **registro encontrado** → nome, UF e especialidade são preenchidos automaticamente
- **nome confere e o registro difere em um dígito** → o número é corrigido pelo cadastro
- **só o nome é parecido** → vira sugestão na tela, nunca aplicada sozinha

Essa última regra existe por medida, feita no cadastro real da operadora: entre os
392 cooperados há dois com **nome idêntico** (CRMs diferentes), um pai e um filho
que só diferem por "JUNIOR" e irmãos com o mesmo sobrenome — enquanto um nome
correto porém mal lido pelo OCR pontua *abaixo* desses pares. Nome não identifica
ninguém; ele apenas encurta a lista que o revisor escolhe.

Para ver os homônimos do seu cadastro:

```bash
curl http://127.0.0.1:8077/api/learning/registry-issues
```

Cada correção e cada aprovação alimentam `var/learning.db`:

```bash
curl http://127.0.0.1:8077/api/learning/stats
```

A resposta traz o acerto por campo, os erros mais frequentes (o que foi lido × o que
o revisor escreveu) e o tamanho do cadastro. Guia aprovada também registra o
profissional que assinou, então o cadastro cresce com o uso.

## Limites conhecidos

- O gabarito existente é da **guia de solicitação de internação**. Outros layouts são
  recusados com "layout não reconhecido" em vez de devolver dados inventados.
- Fotos de baixa resolução (abaixo de 200 dpi no documento) não são lidas de forma
  confiável. A captura é o maior limitador: foto enquadrada e enviada como documento,
  não como imagem comprimida.
- O XML TISS é um rascunho até confirmar a versão do schema e validar contra o XSD.
- Armazenamento das extrações é em memória: reiniciar o servidor as descarta. O
  cadastro e o histórico de correções ficam em `var/learning.db` e persistem.
- O aprendizado não altera limiares sozinho: ele acumula a evidência para a decisão
  ser tomada com número na mão.
