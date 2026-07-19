const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

/**
 * @typedef {'dashboard' | 'chat' | 'patch' | 'clarification_needed' | 'error'} ResponseType
 */

/**
 * @typedef {Object} UIComponent
 * @property {string} id
 * @property {string} component_type  - 'metric_card' | 'pillar_card' | 'risk_card' | 'sentiment_block' | 'text_block' | 'macro_block'
 * @property {string} size            - 'small' | 'medium' | 'large' | 'full'
 * @property {string} data_path       - dot-notation path into SharedState e.g. 'quantitative_result.data.raw_ratios.NIM_pct'
 * @property {string} label
 * @property {string|null} status     - 'green' | 'yellow' | 'red' | null
 * @property {number} order
 */

/**
 * @typedef {Object} UIManifest
 * @property {Object.<string, UIComponent[]>} layout_sections
 */

/**
 * @typedef {Object} StatePatch
 * @property {Object.<string, any>} changed_paths
 * @property {Object.<string, UIComponent[]>|null} patch_manifest
 * @property {string} patch_summary
 */

/**
 * @typedef {Object} DashboardResponse
 * @property {'success'} status
 * @property {'dashboard'} response_type
 * @property {string} session_id
 * @property {string} ticker
 * @property {string} company_name
 * @property {string} sector
 * @property {string} industry
 * @property {string} currency
 * @property {number|null} current_price
 * @property {number} orchestrator_confidence
 * @property {string} investment_verdict
 * @property {string} confidence_level
 * @property {string} final_thesis
 * @property {Object|null} quantitative
 * @property {Object|null} qualitative
 * @property {Object|null} risk_governance
 * @property {Object|null} sentiment
 * @property {Object.<string, string>} agent_statuses
 * @property {UIManifest|null} ui_manifest
 * @property {null} state_patch        - always null for dashboard
 * @property {number} analysis_duration_seconds
 */

/**
 * @typedef {Object} ChatResponse
 * @property {'success'} status
 * @property {'chat'} response_type
 * @property {string} session_id
 * @property {string} targeted_answer
 * @property {null} ui_manifest       - always null for chat
 * @property {null} state_patch       - always null for chat
 */

/**
 * @typedef {Object} PatchResponse
 * @property {'success'} status
 * @property {'patch'} response_type
 * @property {string} session_id
 * @property {StatePatch} state_patch
 * @property {null} ui_manifest       - always null for patch
 */

/**
 * @typedef {Object} ClarificationResponse
 * @property {'clarification_needed'} status
 * @property {string} clarification_message
 * @property {Array<{ticker: string, company_name: string}>} candidates
 * @property {null} session_id        - no session created
 */

/**
 * @typedef {DashboardResponse | ChatResponse | PatchResponse | ClarificationResponse} AnalyzeResponse
 */

/**
 * @returns {Promise<boolean>}
 */
export async function checkHealth() {
  try {
    const res = await fetch(`${BASE_URL}/`, { method: 'GET' })
    return res.ok
  } catch {
    return false
  }
}

/**
 * @param {string} ticker
 * @returns {Promise<Object|null>}
 */
export async function fetchStockSnapshot(ticker) {
  try {
    const res = await fetch(`${BASE_URL}/api/stock/${encodeURIComponent(ticker)}`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

/**
 * @param {string} query
 * @param {string|null} session_id
 * @param {string|null} existing_state_hash
 * @returns {Promise<AnalyzeResponse>}
 */
export async function analyze(query, session_id = null, existing_state_hash = null) {
  try {
    const res = await fetch(`${BASE_URL}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        session_id,
        existing_state_hash,
      }),
    })

    if (!res.ok) {
      // Backend returned HTTP 500 or similar
      const detail = await res.text()
      return {
        status: 'error',
        response_type: 'error',
        error_message: detail || `HTTP ${res.status}`,
      }
    }

    const data = await res.json()
    return data   // already shaped as one of the four response types

  } catch (err) {
    // Network failure - backend unreachable
    return {
      status: 'error',
      response_type: 'error',
      error_message: err.message || 'Network error',
    }
  }
}

/**
 * @param {File} file
 * @param {string} company_id
 * @param {string} fiscal_year
 * @returns {Promise<{document_id: string, status: string}|null>}
 */
export async function uploadDocument(file, company_id, fiscal_year) {
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('company_id', company_id)
    form.append('fiscal_year', fiscal_year)

    const res = await fetch(`${BASE_URL}/api/documents/upload`, {
      method: 'POST',
      body: form,
      // Do NOT set Content-Type header - browser sets it with boundary automatically
    })

    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

/**
 * @param {string} document_id
 * @returns {Promise<{status: string, progress: number}|null>}
 */
export async function fetchDocumentStatus(document_id) {
  try {
    const res = await fetch(`${BASE_URL}/api/documents/${encodeURIComponent(document_id)}/status`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

/**
 * @returns {Promise<Array<{id: string, company_id: string, fiscal_year: number, report_type: string, ingestion_status: string, total_pages: number, error_message: string, created_at: string}>|null>}
 */
export async function fetchAllDocuments() {
  try {
    const res = await fetch(`${BASE_URL}/api/documents/`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}
