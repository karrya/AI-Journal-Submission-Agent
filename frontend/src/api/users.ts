import { api } from './client'
import type { Page, SortOrder } from './authors'

export type RoleCode = 'system_admin' | 'submission_operator' | 'reviewer' | 'author' | 'auditor'
export type UserStatus = 'active' | 'disabled'

export interface ManagedUser {
  id: string
  username: string
  display_name: string
  roles: RoleCode[]
  status: UserStatus
  must_change_password: boolean
  last_login_at: string | null
  created_at: string
  updated_at: string
}

export interface UserListQuery {
  page?: number
  page_size?: number
  name?: string
  status?: UserStatus
  sort?: 'username' | 'display_name' | 'created_at' | 'updated_at' | 'last_login_at'
  order?: SortOrder
}

export interface UserCreate {
  username: string
  display_name: string
  password: string
  password_confirmation: string
  roles: RoleCode[]
}

export interface UserUpdate {
  display_name?: string
  roles?: RoleCode[]
  status?: UserStatus
}

export interface UserPasswordReset {
  new_password: string
  password_confirmation: string
}

export async function listUsers(query: UserListQuery = {}): Promise<Page<ManagedUser>> {
  const response = await api.get<Page<ManagedUser>>('/users', {
    params: { page: 1, page_size: 20, sort: 'created_at', order: 'desc', ...query },
  })
  return response.data
}

export async function createUser(payload: UserCreate): Promise<ManagedUser> {
  const response = await api.post<ManagedUser>('/users', payload)
  return response.data
}

export async function getUser(userId: string): Promise<ManagedUser> {
  const response = await api.get<ManagedUser>(`/users/${userId}`)
  return response.data
}

export async function updateUser(userId: string, payload: UserUpdate): Promise<ManagedUser> {
  const response = await api.patch<ManagedUser>(`/users/${userId}`, payload)
  return response.data
}

export async function resetUserPassword(userId: string, payload: UserPasswordReset): Promise<void> {
  await api.post(`/users/${userId}/reset-password`, payload)
}
