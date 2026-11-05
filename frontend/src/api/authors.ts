import { api } from './client'

export const PERMISSION_CODES = [
  'manuscript:read',
  'manuscript:create',
  'manuscript:update',
  'manuscript:file:manage',
  'author:profile:read',
  'author:email:read',
  'author:phone:read',
  'author:address:read',
  'author:profile:update',
] as const

export type PermissionCode = typeof PERMISSION_CODES[number]
export type SortOrder = 'asc' | 'desc'

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface AuthorListQuery {
  page?: number
  page_size?: number
  name?: string
  orcid?: string
  status?: 'active' | 'inactive'
  sort?: 'display_name' | 'created_at' | 'updated_at'
  order?: SortOrder
}

export interface InstitutionListQuery {
  page?: number
  page_size?: number
  name?: string
  country_code?: string
  city?: string
  sort?: 'name' | 'created_at' | 'updated_at'
  order?: SortOrder
}

export interface AlternateName {
  language?: string | null
  given_name?: string | null
  middle_name?: string | null
  family_name?: string | null
  display_name?: string | null
}

interface AuthorFields {
  given_name?: string | null
  middle_name?: string | null
  family_name?: string | null
  orcid?: string | null
  phone_country_code?: string | null
  phone_number?: string | null
  notes?: string | null
}

export interface AuthorCreate extends AuthorFields {
  display_name: string
  alternate_names?: AlternateName[]
  status?: 'active' | 'inactive'
  confirm_identity_change: true
}

export interface AuthorUpdate extends AuthorFields {
  display_name?: string
  alternate_names?: AlternateName[]
  status?: 'active' | 'inactive'
  confirm_identity_change: true
}

export interface AuthorResponse {
  id: string
  given_name?: string | null
  middle_name?: string | null
  family_name?: string | null
  display_name: string
  alternate_names: AlternateName[]
  orcid?: string | null
  phone_country_code?: string | null
  phone_number?: string | null
  status: 'active' | 'inactive'
  notes?: string | null
  created_at: string
  updated_at: string
}

export interface EmailCreate {
  email: string
  purpose?: 'communication' | 'registration' | 'backup'
  is_primary?: boolean
  confirm_email_binding: true
}

export interface EmailUpdate {
  email?: string
  purpose?: 'communication' | 'registration' | 'backup'
  is_primary?: boolean
  confirm_email_binding?: true
  verification_status?: 'unverified' | 'verified'
  authorization_status?: 'unconfirmed' | 'authorized' | 'revoked'
}

export interface EmailResponse {
  id: string
  author_id: string
  email: string
  normalized_email: string
  purpose: 'communication' | 'registration' | 'backup'
  is_primary: boolean
  verification_status: 'unverified' | 'verified'
  authorization_status: 'unconfirmed' | 'authorized' | 'revoked'
  created_at: string
  updated_at: string
}

export interface InstitutionCreate {
  name: string
  institution_type?: string | null
  website_url?: string | null
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  region?: string | null
  postal_code?: string | null
  country_code?: string | null
}

export interface InstitutionUpdate {
  name?: string
  institution_type?: string | null
  website_url?: string | null
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  region?: string | null
  postal_code?: string | null
  country_code?: string | null
}

export interface InstitutionSummaryResponse {
  id: string
  name: string
  institution_type?: string | null
  website_url?: string | null
  country_code?: string | null
  city?: string | null
}

export interface InstitutionResponse extends InstitutionSummaryResponse {
  address_line1?: string | null
  address_line2?: string | null
  region?: string | null
  postal_code?: string | null
  created_at: string
  updated_at: string
}

export interface AuthorInstitutionLinkCreate {
  institution_id: string
  department?: string | null
  position_title?: string | null
  valid_from?: string | null
  valid_to?: string | null
  is_current?: boolean
  display_order?: number
}

export interface AuthorInstitutionLinkUpdate {
  institution_id?: string
  department?: string | null
  position_title?: string | null
  valid_from?: string | null
  valid_to?: string | null
  is_current?: boolean
  display_order?: number
}

export interface AuthorInstitutionLinkResponse {
  id: string
  author_id: string
  institution_id: string
  institution_name: string
  department?: string | null
  position_title?: string | null
  valid_from?: string | null
  valid_to?: string | null
  is_current: boolean
  display_order: number
  address_line1?: string | null
  address_line2?: string | null
  city?: string | null
  region?: string | null
  postal_code?: string | null
  country_code?: string | null
  created_at: string
  updated_at: string
}

export type AuthorizationValidityStatus =
  | 'not_yet_active'
  | 'active'
  | 'expired'
  | 'revoked'
  | 'inactive_subject'

export interface AuthorizationCreate {
  author_id: string
  user_id: string
  permissions: PermissionCode[]
  valid_from: string
  valid_to: string
  evidence_ref?: string | null
  notes?: string | null
}

export interface AuthorizationUpdate {
  permissions?: PermissionCode[]
  valid_from?: string
  valid_to?: string
  evidence_ref?: string | null
  notes?: string | null
}

export interface AuthorizationRevokeRequest {
  reason?: string | null
}

export interface AuthorizationResponse {
  id: string
  author_id: string
  user_id: string
  permissions: PermissionCode[]
  valid_from: string
  valid_to: string
  evidence_ref: string | null
  notes: string | null
  revoked_at: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
  validity_status: AuthorizationValidityStatus
}

export interface AuthorizationListQuery {
  page?: number
  page_size?: number
  author_id?: string
  user_id?: string
  permission?: PermissionCode
  validity_status?: AuthorizationValidityStatus
  sort?: 'created_at' | 'updated_at' | 'valid_from' | 'valid_to'
  order?: SortOrder
}

export function rolePermissions(roles: string[]): PermissionCode[] {
  if (roles.includes('system_admin') || roles.includes('submission_operator')) {
    return [...PERMISSION_CODES]
  }
  if (roles.includes('reviewer') || roles.includes('author')) {
    return [
      'manuscript:read',
      'author:profile:read',
      'author:email:read',
      'author:phone:read',
      'author:address:read',
    ]
  }
  return []
}

export async function listAuthors(query: AuthorListQuery = {}): Promise<Page<AuthorResponse>> {
  const response = await api.get<Page<AuthorResponse>>('/authors', {
    params: { page: 1, page_size: 20, sort: 'display_name', order: 'asc', ...query },
  })
  return response.data
}

export async function createAuthor(payload: AuthorCreate): Promise<AuthorResponse> {
  const response = await api.post<AuthorResponse>('/authors', payload)
  return response.data
}

export async function deleteAuthor(authorId: string): Promise<void> {
  await api.delete(`/authors/${authorId}`)
}

export async function updateAuthor(
  authorId: string,
  payload: AuthorUpdate,
): Promise<AuthorResponse> {
  const response = await api.patch<AuthorResponse>(`/authors/${authorId}`, payload)
  return response.data
}

export async function getAuthor(authorId: string): Promise<AuthorResponse> {
  const response = await api.get<AuthorResponse>(`/authors/${authorId}`)
  return response.data
}

export async function listEmails(authorId: string): Promise<Page<EmailResponse>> {
  const response = await api.get<Page<EmailResponse>>(`/authors/${authorId}/emails`, {
    params: { page: 1, page_size: 100, sort: 'created_at', order: 'asc' },
  })
  return response.data
}

export async function createEmail(
  authorId: string,
  payload: EmailCreate,
): Promise<EmailResponse> {
  const response = await api.post<EmailResponse>(`/authors/${authorId}/emails`, payload)
  return response.data
}

export async function updateEmail(
  authorId: string,
  emailId: string,
  payload: EmailUpdate,
): Promise<EmailResponse> {
  const response = await api.patch<EmailResponse>(`/authors/${authorId}/emails/${emailId}`, payload)
  return response.data
}

export async function deleteEmail(authorId: string, emailId: string): Promise<void> {
  await api.delete(`/authors/${authorId}/emails/${emailId}`, {
    data: { confirm_email_binding: true },
  })
}

export async function listAuthorInstitutions(
  authorId: string,
): Promise<Page<AuthorInstitutionLinkResponse>> {
  const response = await api.get<Page<AuthorInstitutionLinkResponse>>(
    `/authors/${authorId}/institutions`,
    { params: { page: 1, page_size: 100, sort: 'display_order', order: 'asc' } },
  )
  return response.data
}

export async function updateAuthorInstitution(
  authorId: string,
  linkId: string,
  payload: AuthorInstitutionLinkUpdate,
): Promise<AuthorInstitutionLinkResponse> {
  const response = await api.patch<AuthorInstitutionLinkResponse>(
    `/authors/${authorId}/institutions/${linkId}`,
    payload,
  )
  return response.data
}

export async function deleteAuthorInstitution(authorId: string, linkId: string): Promise<void> {
  await api.delete(`/authors/${authorId}/institutions/${linkId}`)
}

export async function listInstitutions(
  query: InstitutionListQuery = {},
): Promise<Page<InstitutionSummaryResponse>> {
  const response = await api.get<Page<InstitutionSummaryResponse>>('/institutions', {
    params: { page: 1, page_size: 100, sort: 'name', order: 'asc', ...query },
  })
  return response.data
}

export async function createInstitution(
  payload: InstitutionCreate,
): Promise<InstitutionResponse> {
  const response = await api.post<InstitutionResponse>('/institutions', payload)
  return response.data
}

export async function updateInstitution(
  institutionId: string,
  payload: InstitutionUpdate,
): Promise<InstitutionResponse> {
  const response = await api.patch<InstitutionResponse>(`/institutions/${institutionId}`, payload)
  return response.data
}

export async function deleteInstitution(institutionId: string): Promise<void> {
  await api.delete(`/institutions/${institutionId}`)
}

export async function createAuthorInstitution(
  authorId: string,
  payload: AuthorInstitutionLinkCreate,
): Promise<AuthorInstitutionLinkResponse> {
  const response = await api.post<AuthorInstitutionLinkResponse>(
    `/authors/${authorId}/institutions`,
    payload,
  )
  return response.data
}

export async function listAuthorizations(
  query: AuthorizationListQuery = {},
): Promise<Page<AuthorizationResponse>> {
  const response = await api.get<Page<AuthorizationResponse>>('/author-authorizations', {
    params: { page: 1, page_size: 20, sort: 'created_at', order: 'desc', ...query },
  })
  return response.data
}

export async function createAuthorization(
  payload: AuthorizationCreate,
): Promise<AuthorizationResponse> {
  const response = await api.post<AuthorizationResponse>('/author-authorizations', payload)
  return response.data
}

export async function updateAuthorization(
  authorizationId: string,
  payload: AuthorizationUpdate,
): Promise<AuthorizationResponse> {
  const response = await api.patch<AuthorizationResponse>(
    `/author-authorizations/${authorizationId}`,
    payload,
  )
  return response.data
}

export async function revokeAuthorization(
  authorizationId: string,
  payload: AuthorizationRevokeRequest,
): Promise<AuthorizationResponse> {
  const response = await api.post<AuthorizationResponse>(
    `/author-authorizations/${authorizationId}/revoke`,
    payload,
  )
  return response.data
}
