import { api } from './client'

export interface JournalCandidate {
  id: string
  name: string
  publisher_id: string
  publisher_name: string
  issn: string | null
  eissn: string | null
  website_url: string | null
  identity_status: 'UNVERIFIED' | 'VERIFIED' | 'NEEDS_CONFIRMATION' | 'CONFLICT' | 'INACTIVE' | 'UNKNOWN'
  match_reasons: string[]
  conflict_reason: string | null
  updated_at: string
  verified_at: string | null
}

export interface EvidenceSummary {
  source_type: string
  url: string
  title?: string | null
  http_status?: number | null
  content_sha256?: string | null
}

export type DiscoveryCandidate = Partial<JournalCandidate> & {
  candidate_key?: string
  name: string
  publisher_name?: string | null
  identity_status: JournalCandidate['identity_status']
  author_guidelines_url?: string | null
  submission_url?: string | null
  platform_code?: string | null
  platform_confidence?: number
  portal_original_url?: string | null
  portal_verification_status?: string
  portal_access_status?: string
  redirect_chain?: string[]
  sources?: string[]
  evidence?: EvidenceSummary[]
}

export interface IdentifyRequest {
  publisher_name?: string
  journal_name: string
  issn?: string
  eissn?: string
  website_url?: string
  article_type?: string
  idempotency_key?: string
}

export interface IdentifyResponse {
  task_id: string
  status: string
  journal_id?: string | null
  candidates: DiscoveryCandidate[]
}

export interface DiscoveryTask {
  task_id: string
  task_type: string
  status: string
  progress: number
  message: string | null
  stage?: string | null
  warnings?: string[]
  retryable?: boolean
  journal_id?: string | null
  candidates: DiscoveryCandidate[]
}

export interface PublisherOption {
  id: string
  name: string
}

export interface JournalOption {
  id: string
  publisher_id: string
  name: string
  issn: string | null
  eissn: string | null
  website_url: string | null
}

export async function getPublisherOptions(name = ''): Promise<PublisherOption[]> {
  const response = await api.get<{ items: PublisherOption[] }>('/publishers/options', {
    params: { name: name || undefined, limit: 20 },
  })
  return response.data.items
}

export async function getJournalOptions(publisherId: string, name = ''): Promise<JournalOption[]> {
  const response = await api.get<{ items: JournalOption[] }>('/journals/options', {
    params: { publisher_id: publisherId, name: name || undefined, limit: 20 },
  })
  return response.data.items
}

export async function identifyJournal(payload: IdentifyRequest): Promise<IdentifyResponse> {
  const response = await api.post<IdentifyResponse>('/journals/identify', payload)
  return response.data
}

export async function confirmIdentity(
  journalId: string,
  expectedUpdatedAt: string,
  confirmationNote?: string,
): Promise<JournalCandidate> {
  const response = await api.post<JournalCandidate>(`/journals/${journalId}/confirm-identity`, {
    expected_updated_at: expectedUpdatedAt,
    confirmation_note: confirmationNote ?? null,
  })
  return response.data
}

export async function getDiscoveryTask(taskId: string): Promise<DiscoveryTask> {
  const response = await api.get<DiscoveryTask>(`/tasks/${taskId}`)
  return response.data
}

export async function retryDiscoveryTask(taskId: string): Promise<DiscoveryTask> {
  const response = await api.post<DiscoveryTask>(`/tasks/${taskId}/retry`)
  return response.data
}

export async function cancelDiscoveryTask(taskId: string): Promise<DiscoveryTask> {
  const response = await api.post<DiscoveryTask>(`/tasks/${taskId}/cancel`)
  return response.data
}

export async function confirmTaskCandidate(
  taskId: string,
  candidateKey: string,
  confirmationNote?: string,
): Promise<DiscoveryTask> {
  const response = await api.post<DiscoveryTask>(`/tasks/${taskId}/confirm-candidate`, {
    candidate_key: candidateKey,
    confirmation_note: confirmationNote ?? null,
  })
  return response.data
}
