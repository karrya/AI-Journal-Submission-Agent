import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { api, getSafeRequestId, setCsrfToken } from './client'
import router from '../router'
import { useAuthStore, type User } from '../stores/auth'
import { createPinia, setActivePinia } from 'pinia'

function success(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { data, status, statusText: String(status), headers: {}, config }
}

function failure(config: InternalAxiosRequestConfig, status: number, data: unknown): AxiosError {
  return new AxiosError('Request failed', String(status), config, undefined, {
    data,
    status,
    statusText: String(status),
    headers: {},
    config,
  })
}

describe('typed API client', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    setActivePinia(createPinia())
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
    setCsrfToken(null)
    localStorage.clear()
  })

  afterEach(() => vi.restoreAllMocks())

  it('uses the versioned API and credentialed cookies', () => {
    expect(api.defaults.baseURL).toBe('/api/v1')
    expect(api.defaults.withCredentials).toBe(true)
  })

  it('attaches the in-memory CSRF token only to mutations', async () => {
    setCsrfToken('csrf-secret')
    adapter.mockImplementation(async (config) => success(config, {}))

    await api.get('/auth/me')
    await api.post('/auth/logout')
    await api.put('/authors/1', {})
    await api.patch('/authors/1', {})
    await api.delete('/authors/1')

    expect(new AxiosHeaders(adapter.mock.calls[0][0].headers).has('X-CSRF-Token')).toBe(false)
    for (const call of adapter.mock.calls.slice(1)) {
      expect(new AxiosHeaders(call[0].headers).get('X-CSRF-Token')).toBe('csrf-secret')
    }
    expect(localStorage.getItem('csrf_token')).toBeNull()
    expect(localStorage.getItem('asa_session')).toBeNull()
  })

  it('refreshes CSRF and retries a security-validated mutation once', async () => {
    setCsrfToken('stale')
    adapter
      .mockImplementationOnce(async (config) => {
        throw failure(config, 403, { code: 'SECURITY_CHECK_FAILED', message: 'denied', request_id: 'r1' })
      })
      .mockImplementationOnce(async (config) => success(config, { csrf_token: 'fresh' }))
      .mockImplementationOnce(async (config) => success(config, { id: 'a1' }))

    const response = await api.post('/authors', { display_name: 'Author' })

    expect(response.data).toEqual({ id: 'a1' })
    expect(adapter).toHaveBeenCalledTimes(3)
    expect(adapter.mock.calls[1][0].url).toBe('/auth/csrf')
    expect(adapter.mock.calls[1][0].method).toBe('get')
    expect(adapter.mock.calls[2][0].url).toBe('/authors')
    expect(new AxiosHeaders(adapter.mock.calls[2][0].headers).get('X-CSRF-Token')).toBe('fresh')
  })

  it('does not retry a second security failure', async () => {
    setCsrfToken('stale')
    adapter
      .mockImplementationOnce(async (config) => {
        throw failure(config, 403, { code: 'SECURITY_CHECK_FAILED' })
      })
      .mockImplementationOnce(async (config) => success(config, { csrf_token: 'fresh' }))
      .mockImplementationOnce(async (config) => {
        throw failure(config, 403, { code: 'SECURITY_CHECK_FAILED' })
      })

    await expect(api.post('/authors', {})).rejects.toMatchObject({
      response: { data: { code: 'SECURITY_CHECK_FAILED' } },
    })
    expect(adapter).toHaveBeenCalledTimes(3)
  })

  it('does not retry other authorization failures', async () => {
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, 403, { code: 'PERMISSION_DENIED' })
    })

    await expect(api.post('/authors', {})).rejects.toMatchObject({
      response: { data: { code: 'PERMISSION_DENIED' } },
    })
    expect(adapter).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['numeric', 12345],
    ['object', { value: 'not-a-string' }],
    ['null', null],
  ])('returns null for a %s runtime request_id without throwing', (_label, requestId) => {
    const config = { headers: new AxiosHeaders() } as InternalAxiosRequestConfig
    const error = failure(config, 403, { code: 'PERMISSION_DENIED', request_id: requestId })

    expect(() => getSafeRequestId(error)).not.toThrow()
    expect(getSafeRequestId(error)).toBeNull()
  })

  it('clears authentication and routes to login on 401', async () => {
    const user: User = {
      id: 'u1',
      username: 'admin',
      display_name: 'Admin',
      roles: ['system_admin'],
      status: 'active',
      must_change_password: false,
      last_login_at: null,
    }
    const auth = useAuthStore()
    auth.setSession(user, 'csrf')
    const replace = vi.spyOn(router, 'replace').mockResolvedValue(undefined)
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, 401, { code: 'UNAUTHORIZED' })
    })

    await expect(api.get('/authors')).rejects.toMatchObject({ response: { status: 401 } })

    expect(auth.user).toBeNull()
    expect(auth.csrfToken).toBeNull()
    expect(replace).toHaveBeenCalledWith({ name: 'login' })
  })

  it('routes to change-password without clearing the session when required', async () => {
    const auth = useAuthStore()
    auth.setSession(
      {
        id: 'u1',
        username: 'admin',
        display_name: 'Admin',
        roles: ['system_admin'],
        status: 'active',
        must_change_password: true,
        last_login_at: null,
      },
      'csrf',
    )
    const replace = vi.spyOn(router, 'replace').mockResolvedValue(undefined)
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, 403, { code: 'PASSWORD_CHANGE_REQUIRED' })
    })

    await expect(api.get('/authors')).rejects.toMatchObject({
      response: { data: { code: 'PASSWORD_CHANGE_REQUIRED' } },
    })

    expect(auth.user?.username).toBe('admin')
    expect(auth.csrfToken).toBe('csrf')
    expect(replace).toHaveBeenCalledWith({ name: 'change-password' })
  })
})
