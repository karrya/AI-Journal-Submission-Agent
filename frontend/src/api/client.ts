import axios, { AxiosHeaders, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import { ref } from 'vue'

export interface ApiErrorBody {
  code?: string
  message?: string
  request_id?: string
  details?: unknown
}

interface CsrfResponse {
  csrf_token: string
}

type RetryableRequestConfig = InternalAxiosRequestConfig & {
  securityRetried?: boolean
}

const csrfToken = ref<string | null>(null)

export function getCsrfToken(): string | null {
  return csrfToken.value
}

export function setCsrfToken(token: string | null): void {
  csrfToken.value = token
}

export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
})

let clearAuthState: () => void = () => setCsrfToken(null)
let navigateToLogin: () => Promise<void> = () => Promise.resolve()
let navigateToChangePassword: () => Promise<void> = () => Promise.resolve()

export function registerAuthStateClear(handler: () => void): void {
  clearAuthState = handler
}

export function registerAuthNavigationHandlers(handlers: {
  login: () => Promise<void>
  changePassword: () => Promise<void>
}): void {
  navigateToLogin = handlers.login
  navigateToChangePassword = handlers.changePassword
}

function isMutation(config: AxiosRequestConfig | InternalAxiosRequestConfig): boolean {
  const method = config.method?.toLowerCase() ?? 'get'
  return !['get', 'head', 'options'].includes(method)
}

api.interceptors.request.use((config) => {
  if (isMutation(config) && csrfToken.value) {
    config.headers = AxiosHeaders.from(config.headers)
    config.headers.set('X-CSRF-Token', csrfToken.value)
  }
  return config
})

api.interceptors.response.use(undefined, async (error) => {
  const config = error.config as RetryableRequestConfig | undefined
  const code = (error.response?.data as ApiErrorBody | undefined)?.code

  if (error.response?.status === 401) {
    clearAuthState()
    await navigateToLogin()
    return Promise.reject(error)
  }

  if (code === 'PASSWORD_CHANGE_REQUIRED') {
    await navigateToChangePassword()
    return Promise.reject(error)
  }

  if (
    code === 'SECURITY_CHECK_FAILED' &&
    config &&
    isMutation(config) &&
    !config.securityRetried
  ) {
    config.securityRetried = true
    const response = await api.get<CsrfResponse>('/auth/csrf')
    setCsrfToken(response.data.csrf_token)
    return api.request(config)
  }

  return Promise.reject(error)
})

export function getSafeRequestId(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null
  const body = error.response?.data as ApiErrorBody | undefined
  const header = error.response?.headers?.['x-request-id']
  const candidate = body?.request_id ?? (typeof header === 'string' ? header : null)
  if (!candidate) return null
  const requestId = candidate.trim()
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId)
    ? requestId
    : null
}
