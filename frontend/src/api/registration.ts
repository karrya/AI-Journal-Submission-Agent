import { api } from './client'
import type { Page } from './authors'
import type { JournalOption } from './identification'

export type RegistrationSupportStatus = 'SUPPORTED' | 'TESTING' | 'DISABLED'

export interface RegistrationPublisher {
  id: string
  publisher_id: string
  publisher_code: string
  display_name: string
  support_status: RegistrationSupportStatus
  support_level: 'V0_1' | 'V0_2'
  official_domains: string[] | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface RegistrationTask {
  id: string
  author_id: string
  publisher_id: string
  journal_id: string
  platform_code: string
  task_status: string
  current_step: string | null
  retryable: boolean
  created_at: string
}

export interface RegistrationTaskCreate {
  author_id: string
  publisher_id: string
  journal_id: string
  authorization_id: string
  platform_code: string
  idempotency_key: string
}

export interface RegistrationTaskQuery {
  page?: number
  page_size?: number
  author_id?: string
  publisher_id?: string
  journal_id?: string
  task_status?: string
  created_from?: string
  created_to?: string
}

export async function getRegistrationPublishers(): Promise<RegistrationPublisher[]> {
  const response = await api.get<{ items: RegistrationPublisher[] }>('/registration/publishers')
  return response.data.items
}

export async function getRegistrationJournals(publisherId: string): Promise<JournalOption[]> {
  const response = await api.get<{ items: JournalOption[] }>(
    `/registration/publishers/${encodeURIComponent(publisherId)}/journals`,
  )
  return response.data.items
}

export async function getRegistrationTasks(
  query: RegistrationTaskQuery = {},
): Promise<Page<RegistrationTask>> {
  const response = await api.get<Page<RegistrationTask>>('/registration/tasks', {
    params: { page: 1, page_size: 20, ...query },
  })
  return response.data
}

export interface RegistrationHandoff {
  task_id: string
  reason: string
  manual_url: string
  browser_handoff_id: string
  current_step: string
  resumable: boolean
}

export async function getRegistrationHandoff(taskId: string): Promise<RegistrationHandoff> {
  const response = await api.get<RegistrationHandoff>(
    `/registration/tasks/${encodeURIComponent(taskId)}/handoff`,
  )
  return response.data
}

export async function resumeRegistrationTask(taskId: string): Promise<RegistrationTask> {
  const response = await api.post<RegistrationTask>(
    `/registration/tasks/${encodeURIComponent(taskId)}/resume`,
  )
  return response.data
}

export async function createRegistrationTask(payload: RegistrationTaskCreate): Promise<RegistrationTask> {
  const response = await api.post<RegistrationTask>('/registration/tasks', payload)
  return response.data
}

export async function cancelRegistrationTask(taskId: string): Promise<RegistrationTask> {
  const response = await api.post<RegistrationTask>(
    `/registration/tasks/${encodeURIComponent(taskId)}/cancel`,
  )
  return response.data
}

export async function retryRegistrationTask(taskId: string): Promise<RegistrationTask> {
  const response = await api.post<RegistrationTask>(
    `/registration/tasks/${encodeURIComponent(taskId)}/retry`,
  )
  return response.data
}
