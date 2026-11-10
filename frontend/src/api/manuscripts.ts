import { api } from './client'
import type { Page, SortOrder } from './authors'

export interface ManuscriptListQuery {
  page?: number
  page_size?: number
  status?: ManuscriptStatus
  sort?: 'created_at' | 'updated_at' | 'title'
  order?: SortOrder
}

export interface ManuscriptVersionCreate {
  label?: string | null
  change_note?: string | null
}

export type ManuscriptStatus = 'draft' | 'active' | 'archived'

export interface ManuscriptAuthorInput {
  author_id: string
  position: number
  is_corresponding: boolean
}

export interface ManuscriptAuthor extends ManuscriptAuthorInput {
  display_name: string
}

export interface ManuscriptAuthorsUpdate {
  authors: ManuscriptAuthorInput[]
  confirm_authorship_change: true
}

export interface ManuscriptMetadata {
  title: string
  abstract: string
  keywords: string[]
  article_type: string
  subject_field?: string | null
  language: string
  funding_statement?: string | null
  funding_number?: string | null
  funding_name?: string | null
  publication_statement?: string | null
  acknowledgements?: string | null
  author_contributions?: string | null
  clinical_trial_number?: string | null
  conflict_of_interest_statement?: string | null
  ethics_statement?: string | null
  data_availability_statement?: string | null
  notes?: string | null
}

export interface ManuscriptCreate extends ManuscriptMetadata {
  owner_author_id: string
  authors?: ManuscriptAuthorInput[]
}

export type ManuscriptUpdate = Partial<ManuscriptMetadata>

export interface Manuscript extends ManuscriptMetadata {
  id: string
  internal_number: string
  owner_author_id: string
  status: ManuscriptStatus
  current_version_id: string | null
  authors: ManuscriptAuthor[]
  created_at: string
  updated_at: string
}

export interface ManuscriptSnapshot extends ManuscriptMetadata {
  owner_author_id: string
  authors: ManuscriptAuthor[]
}

export interface ManuscriptVersion {
  id: string
  manuscript_id: string
  version_number: number
  label?: string | null
  change_note?: string | null
  metadata_snapshot: ManuscriptSnapshot
  created_at: string
  created_by: string
}

export async function listManuscripts(query: ManuscriptListQuery = {}): Promise<Page<Manuscript>> {
  const response = await api.get<Page<Manuscript>>('/manuscripts', {
    params: { page: 1, page_size: 20, sort: 'created_at', order: 'desc', ...query },
  })
  return response.data
}

export async function createManuscript(payload: ManuscriptCreate): Promise<Manuscript> {
  const response = await api.post<Manuscript>('/manuscripts', payload)
  return response.data
}

export async function getManuscript(manuscriptId: string): Promise<Manuscript> {
  const response = await api.get<Manuscript>(`/manuscripts/${manuscriptId}`)
  return response.data
}

export async function updateManuscript(
  manuscriptId: string,
  payload: ManuscriptUpdate,
): Promise<Manuscript> {
  const response = await api.patch<Manuscript>(`/manuscripts/${manuscriptId}`, payload)
  return response.data
}

export async function deleteManuscript(manuscriptId: string): Promise<void> {
  await api.delete(`/manuscripts/${manuscriptId}`)
}

export async function replaceManuscriptAuthors(
  manuscriptId: string,
  payload: ManuscriptAuthorsUpdate,
): Promise<ManuscriptAuthor[]> {
  const response = await api.put<ManuscriptAuthor[]>(`/manuscripts/${manuscriptId}/authors`, payload)
  return response.data
}

export async function listManuscriptVersions(
  manuscriptId: string,
  query: { page?: number; page_size?: number } = {},
): Promise<Page<ManuscriptVersion>> {
  const response = await api.get<Page<ManuscriptVersion>>(`/manuscripts/${manuscriptId}/versions`, {
    params: { page: 1, page_size: 20, ...query },
  })
  return response.data
}

export async function createManuscriptVersion(
  manuscriptId: string,
  payload: ManuscriptVersionCreate,
): Promise<ManuscriptVersion> {
  const response = await api.post<ManuscriptVersion>(`/manuscripts/${manuscriptId}/versions`, payload)
  return response.data
}

export async function getManuscriptVersion(
  manuscriptId: string,
  versionId: string,
): Promise<ManuscriptVersion> {
  const response = await api.get<ManuscriptVersion>(
    `/manuscripts/${manuscriptId}/versions/${versionId}`,
  )
  return response.data
}
