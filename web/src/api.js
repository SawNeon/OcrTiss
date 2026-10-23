const BASE = '/api'

async function handle(response) {
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(detail.detail || 'falha na requisição')
  }
  return response.json()
}

export function health() {
  return fetch(`${BASE}/health`).then(handle)
}

export function listExtractions() {
  return fetch(`${BASE}/extractions`).then(handle)
}

export function uploadGuide(file) {
  const form = new FormData()
  form.append('file', file)
  return fetch(`${BASE}/extractions`, { method: 'POST', body: form }).then(handle)
}

export function readExtraction(id) {
  return fetch(`${BASE}/extractions/${id}`).then(handle)
}

export function correctField(id, fieldName, value) {
  return fetch(`${BASE}/extractions/${id}/fields/${fieldName}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value, author: 'revisor' }),
  }).then(handle)
}

export function registerDecision(id, decision, note) {
  return fetch(`${BASE}/extractions/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note, author: 'revisor' }),
  }).then(handle)
}

export function pageImageUrl(id, page = 1) {
  return `${BASE}/extractions/${id}/page.png?page=${page}`
}

export function tissXmlUrl(id) {
  return `${BASE}/extractions/${id}/tiss.xml`
}
