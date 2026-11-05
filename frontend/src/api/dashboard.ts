import { api } from './client'

export interface RecentOperation {
  action: string
  target_id: string | null
  result: 'success' | 'failure'
  created_at: string
}

export interface DashboardSummary {
  author_count: number
  manuscript_count: number
  current_version_file_count: number
  expiring_authorization_count: number
  recent_operations: RecentOperation[]
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const response = await api.get<DashboardSummary>('/dashboard/summary')
  return response.data
}
