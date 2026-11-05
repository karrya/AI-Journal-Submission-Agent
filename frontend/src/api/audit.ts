import { api } from './client'
import type { Page, SortOrder } from './authors'

export type AuditCategory = 'authentication' | 'authorization' | 'business' | 'sensitive_access'

export interface AuditLog {
  id: string
  actor_user_id: string | null
  actor_type: 'user' | 'system' | 'anonymous'
  category: AuditCategory
  action: string
  target_type: string | null
  target_id: string | null
  author_id: string | null
  request_id: string
  result: 'success' | 'failure'
  before_summary?: Record<string, unknown> | null
  after_summary?: Record<string, unknown> | null
  error_code?: string | null
  error_message?: string | null
  created_at: string
}

export interface AuditListQuery {
  page?: number
  page_size?: number
  actor_user_id?: string
  author_id?: string
  category?: AuditCategory
  action?: string
  target_type?: string
  target_id?: string
  result?: 'success' | 'failure'
  request_id?: string
  created_from?: string
  created_to?: string
  sort?: 'created_at'
  order?: SortOrder
}

export async function listAuditLogs(query: AuditListQuery = {}): Promise<Page<AuditLog>> {
  const response = await api.get<Page<AuditLog>>('/audit-logs', {
    params: { page: 1, page_size: 20, sort: 'created_at', order: 'desc', ...query },
  })
  return response.data
}

export async function getAuditLog(logId: string): Promise<AuditLog> {
  const response = await api.get<AuditLog>(`/audit-logs/${logId}`)
  return response.data
}
