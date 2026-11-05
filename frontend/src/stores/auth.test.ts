import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { api, setCsrfToken } from '../api/client'
import { useAuthStore, type User } from './auth'

const activeUser: User = {
  id: 'u1',
  username: 'admin',
  display_name: 'Admin',
  roles: ['system_admin'],
  status: 'active',
  must_change_password: false,
  last_login_at: null,
}

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

describe('auth store', () => {
  let adapter: ReturnType<typeof vi.fn<AxiosAdapter>>

  beforeEach(() => {
    setActivePinia(createPinia())
    adapter = vi.fn<AxiosAdapter>()
    api.defaults.adapter = adapter
    setCsrfToken(null)
    localStorage.clear()
  })

  it('keeps CSRF only in memory', () => {
    const store = useAuthStore()
    store.setSession(activeUser, 'csrf')

    expect(store.csrfToken).toBe('csrf')
    expect(localStorage.getItem('asa_session')).toBeNull()
    expect(localStorage.getItem('csrf_token')).toBeNull()
  })

  it('logs in with backend field names and stores the returned session', async () => {
    adapter.mockImplementationOnce(async (config) => success(config, {
      user: activeUser,
      csrf_token: 'login-csrf',
      idle_expires_at: '2026-11-05T10:00:00Z',
      absolute_expires_at: '2026-11-05T18:00:00Z',
    }))
    const store = useAuthStore()

    const user = await store.login('admin', 'secret')

    expect(user).toEqual(activeUser)
    expect(store.user).toEqual(activeUser)
    expect(store.isAuthenticated).toBe(true)
    expect(store.csrfToken).toBe('login-csrf')
    expect(adapter.mock.calls[0][0].url).toBe('/auth/login')
    expect(JSON.parse(String(adapter.mock.calls[0][0].data))).toEqual({ username: 'admin', password: 'secret' })
  })

  it('restores the user and CSRF once before protected routing', async () => {
    adapter
      .mockImplementationOnce(async (config) => success(config, activeUser))
      .mockImplementationOnce(async (config) => success(config, { csrf_token: 'restored-csrf' }))
    const store = useAuthStore()

    await store.restoreSession()
    await store.restoreSession()

    expect(store.user).toEqual(activeUser)
    expect(store.csrfToken).toBe('restored-csrf')
    expect(adapter).toHaveBeenCalledTimes(2)
    expect(adapter.mock.calls[0][0].url).toBe('/auth/me')
    expect(adapter.mock.calls[1][0].url).toBe('/auth/csrf')
  })

  it('clears session state when restoration is unauthorized', async () => {
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, 401, { code: 'UNAUTHORIZED' })
    })
    const store = useAuthStore()
    store.user = activeUser
    setCsrfToken('stale')

    await expect(store.restoreSession()).rejects.toMatchObject({ response: { status: 401 } })
    expect(store.user).toBeNull()
    expect(store.csrfToken).toBeNull()
  })

  it('clears session state after logout even when the request fails', async () => {
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, 500, { code: 'INTERNAL_SERVER_ERROR' })
    })
    const store = useAuthStore()
    store.setSession(activeUser, 'csrf')

    await expect(store.logout()).rejects.toMatchObject({ response: { status: 500 } })
    expect(store.user).toBeNull()
    expect(store.csrfToken).toBeNull()
  })

  it('changes password with backend fields and clears the revoked session', async () => {
    adapter.mockImplementationOnce(async (config) => success(config, null, 204))
    const store = useAuthStore()
    store.setSession({ ...activeUser, must_change_password: true }, 'csrf')

    await store.changePassword('old-password', 'new-long-password')

    expect(adapter.mock.calls[0][0].url).toBe('/auth/change-password')
    expect(JSON.parse(String(adapter.mock.calls[0][0].data))).toEqual({
      current_password: 'old-password',
      new_password: 'new-long-password',
    })
    expect(store.user).toBeNull()
    expect(store.csrfToken).toBeNull()
  })

  it('preserves the session when password change fails', async () => {
    adapter.mockImplementationOnce(async (config) => {
      throw failure(config, 400, { code: 'WEAK_PASSWORD' })
    })
    const store = useAuthStore()
    store.setSession({ ...activeUser, must_change_password: true }, 'csrf')

    await expect(store.changePassword('old-password', 'weak')).rejects.toBeDefined()
    expect(store.user?.username).toBe('admin')
    expect(store.csrfToken).toBe('csrf')
  })
})
