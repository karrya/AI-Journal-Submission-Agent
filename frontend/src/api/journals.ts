import { api } from './client'
import { fetchAllPages } from './pagination'
import type { Page, SortOrder } from './authors'

export interface PublisherCreate {
  name: string
  website_url?: string | null
  notes?: string | null
}

export interface PublisherUpdate {
  name?: string
  website_url?: string | null
  notes?: string | null
}

export interface PublisherResponse {
  id: string
  name: string
  website_url?: string | null
  notes?: string | null
  created_at: string
  updated_at: string
}

export interface PublisherListQuery {
  page?: number
  page_size?: number
  name?: string
  sort?: 'name' | 'created_at' | 'updated_at'
  order?: SortOrder
}

export interface JournalPlatformCreate {
  code: string
  name: string
  description?: string
  status?: 'active' | 'needs_review' | 'disabled'
}

export interface JournalPlatformUpdate {
  code?: string
  name?: string
  description?: string | null
  status?: 'active' | 'needs_review' | 'disabled'
}

export interface JournalPlatformResponse {
  id: string
  code: string
  name: string
  description: string
  status: 'active' | 'needs_review' | 'disabled'
  created_at: string
  updated_at: string
}

export interface PlatformListQuery {
  page?: number
  page_size?: number
  code?: string
  name?: string
  status?: 'active' | 'needs_review' | 'disabled'
  sort?: 'code' | 'name' | 'created_at' | 'updated_at'
  order?: SortOrder
}

export interface JournalRequirement {
  key: string
  value: string | number | boolean
  scope: string
  source_url: string
  verified_at: string
}

interface JournalOptionalFields {
  platform_id?: string | null
  issn?: string | null
  eissn?: string | null
  website_url?: string | null
  submission_url?: string | null
  author_guidelines_url?: string | null
  requirements_source_url?: string | null
  requirements_verified_at?: string | null
  notes?: string | null
}

export interface JournalCreate extends JournalOptionalFields {
  publisher_id: string
  name: string
  subject_categories?: string[]
  article_types?: string[]
  requirements?: JournalRequirement[]
  status?: string
}

export interface JournalUpdate extends JournalOptionalFields {
  publisher_id?: string
  name?: string
  subject_categories?: string[]
  article_types?: string[]
  requirements?: JournalRequirement[]
  status?: string
}

export interface JournalResponse {
  id: string
  publisher_id: string
  platform_id?: string | null
  name: string
  issn?: string | null
  eissn?: string | null
  website_url?: string | null
  submission_url?: string | null
  author_guidelines_url?: string | null
  subject_categories: string[]
  article_types: string[]
  requirements: JournalRequirement[]
  requirements_source_url?: string | null
  requirements_verified_at?: string | null
  status: string
  notes?: string | null
  created_at: string
  updated_at: string
}

export interface JournalListQuery {
  page?: number
  page_size?: number
  name?: string
  publisher_id?: string
  platform_id?: string
  issn?: string
  status?: string
  sort?: 'name' | 'created_at' | 'updated_at'
  order?: SortOrder
}

export async function listPublishers(
  query: PublisherListQuery = {},
): Promise<Page<PublisherResponse>> {
  const response = await api.get<Page<PublisherResponse>>('/publishers', {
    params: { page: 1, page_size: 20, sort: 'name', order: 'asc', ...query },
  })
  return response.data
}

export async function listAllPublishers(): Promise<PublisherResponse[]> {
  const result = await fetchAllPages((page, pageSize) => listPublishers({ page, page_size: pageSize }))
  return result.items
}

export async function createPublisher(payload: PublisherCreate): Promise<PublisherResponse> {
  const response = await api.post<PublisherResponse>('/publishers', payload)
  return response.data
}

export async function updatePublisher(
  publisherId: string,
  payload: PublisherUpdate,
): Promise<PublisherResponse> {
  const response = await api.patch<PublisherResponse>(`/publishers/${publisherId}`, payload)
  return response.data
}

export async function deletePublisher(publisherId: string): Promise<void> {
  await api.delete(`/publishers/${publisherId}`)
}

export async function listPlatforms(
  query: PlatformListQuery = {},
): Promise<Page<JournalPlatformResponse>> {
  const response = await api.get<Page<JournalPlatformResponse>>('/journal-platforms', {
    params: { page: 1, page_size: 20, sort: 'code', order: 'asc', ...query },
  })
  return response.data
}

export async function listAllPlatforms(): Promise<JournalPlatformResponse[]> {
  const result = await fetchAllPages((page, pageSize) => listPlatforms({ page, page_size: pageSize }))
  return result.items
}

export async function createPlatform(
  payload: JournalPlatformCreate,
): Promise<JournalPlatformResponse> {
  const response = await api.post<JournalPlatformResponse>('/journal-platforms', payload)
  return response.data
}

export async function updatePlatform(
  platformId: string,
  payload: JournalPlatformUpdate,
): Promise<JournalPlatformResponse> {
  const response = await api.patch<JournalPlatformResponse>(`/journal-platforms/${platformId}`, payload)
  return response.data
}

export async function deletePlatform(platformId: string): Promise<void> {
  await api.delete(`/journal-platforms/${platformId}`)
}

export async function listJournals(query: JournalListQuery = {}): Promise<Page<JournalResponse>> {
  const response = await api.get<Page<JournalResponse>>('/journals', {
    params: { page: 1, page_size: 20, sort: 'name', order: 'asc', ...query },
  })
  return response.data
}

export async function createJournal(payload: JournalCreate): Promise<JournalResponse> {
  const response = await api.post<JournalResponse>('/journals', payload)
  return response.data
}

export async function updateJournal(
  journalId: string,
  payload: JournalUpdate,
): Promise<JournalResponse> {
  const response = await api.patch<JournalResponse>(`/journals/${journalId}`, payload)
  return response.data
}

export async function deleteJournal(journalId: string): Promise<void> {
  await api.delete(`/journals/${journalId}`)
}
