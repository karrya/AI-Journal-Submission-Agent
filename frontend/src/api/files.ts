import type { AxiosProgressEvent } from 'axios'
import { api } from './client'
import type { Page } from './authors'

export const FILE_TYPES = [
  'main_manuscript',
  'title_page',
  'abstract',
  'figure',
  'table',
  'supplement',
  'cover_letter',
  'reviewer_suggestion',
  'other',
] as const

export type FileType = typeof FILE_TYPES[number]

export interface ManuscriptFile {
  id: string
  file_family_id: string
  manuscript_id: string
  manuscript_version_id: string
  file_type: FileType
  display_name: string
  file_version: number
  original_filename: string
  mime_type: string
  extension: string
  size_bytes: number
  sha256: string
  scan_status: string
  integrity_status: 'normal' | 'missing' | 'hash_mismatch'
  status: 'active' | 'deleted'
  created_at: string
  uploaded_by: string
}

export interface FileUploadInput {
  file: File
  fileType?: FileType
  displayName?: string
  fileFamilyId?: string
  onUploadProgress?: (event: AxiosProgressEvent) => void
}

export async function uploadFile(
  manuscriptId: string,
  versionId: string,
  input: FileUploadInput,
): Promise<ManuscriptFile> {
  const data = new FormData()
  data.append('file', input.file)
  if (input.fileFamilyId) data.append('file_family_id', input.fileFamilyId)
  if (input.fileType) data.append('file_type', input.fileType)
  if (input.displayName) data.append('display_name', input.displayName)

  const response = await api.post<ManuscriptFile>(
    `/manuscripts/${manuscriptId}/versions/${versionId}/files`,
    data,
    { onUploadProgress: input.onUploadProgress },
  )
  return response.data
}

export async function listFiles(
  manuscriptId: string,
  versionId: string,
  query: { page?: number; page_size?: number } = {},
): Promise<Page<ManuscriptFile>> {
  const response = await api.get<Page<ManuscriptFile>>(
    `/manuscripts/${manuscriptId}/versions/${versionId}/files`,
    { params: { page: 1, page_size: 20, ...query } },
  )
  return response.data
}

export async function getFile(fileId: string): Promise<ManuscriptFile> {
  const response = await api.get<ManuscriptFile>(`/files/${fileId}`)
  return response.data
}

export async function deleteFile(fileId: string): Promise<void> {
  await api.delete(`/files/${fileId}`)
}

export async function downloadFile(fileId: string): Promise<Blob> {
  const response = await api.get<Blob>(`/files/${fileId}/download`, { responseType: 'blob' })
  return response.data
}
