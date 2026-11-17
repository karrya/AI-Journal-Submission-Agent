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
  candidates: JournalCandidate[]
}

export interface DiscoveryTask {
  task_id: string
  task_type: string
  status: string
  progress: number
  message: string | null
  candidates: JournalCandidate[]
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
