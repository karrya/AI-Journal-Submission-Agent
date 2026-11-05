import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { AxiosError } from 'axios'
import { api, getCsrfToken, registerAuthStateClear, setCsrfToken } from '../api/client'

export interface User {
  id: string
  username: string
  display_name: string
  roles: string[]
  status: 'active' | 'disabled'
  must_change_password: boolean
  last_login_at: string | null
}

interface LoginResponse {
  user: User
  csrf_token: string
  idle_expires_at: string
  absolute_expires_at: string
}

interface CsrfResponse {
  csrf_token: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const hasCheckedSession = ref(false)
  const isAuthenticated = computed(() => user.value !== null)
  const csrfToken = computed(getCsrfToken)
  let restorePromise: Promise<User | null> | null = null

  function setSession(sessionUser: User, token: string): void {
    user.value = sessionUser
    setCsrfToken(token)
    hasCheckedSession.value = true
  }

  function clearSession(): void {
    user.value = null
    setCsrfToken(null)
    hasCheckedSession.value = true
  }

  async function login(username: string, password: string): Promise<User> {
    const response = await api.post<LoginResponse>('/auth/login', { username, password })
    setSession(response.data.user, response.data.csrf_token)
    return response.data.user
  }

  async function restoreSession(): Promise<User | null> {
    if (hasCheckedSession.value) return user.value
    if (restorePromise) return restorePromise

    restorePromise = (async () => {
      try {
        const response = await api.get<User>('/auth/me')
        user.value = response.data
        if (!getCsrfToken()) {
          const csrfResponse = await api.get<CsrfResponse>('/auth/csrf')
          setCsrfToken(csrfResponse.data.csrf_token)
        }
        hasCheckedSession.value = true
        return user.value
      } catch (error) {
        if (error instanceof AxiosError && error.response?.status === 401) {
          clearSession()
        }
        throw error
      } finally {
        restorePromise = null
      }
    })()

    return restorePromise
  }

  async function logout(): Promise<void> {
    try {
      await api.post('/auth/logout')
    } finally {
      clearSession()
    }
  }

  async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    clearSession()
  }

  return {
    user,
    csrfToken,
    isAuthenticated,
    hasCheckedSession,
    setSession,
    clearSession,
    login,
    restoreSession,
    logout,
    changePassword,
  }
})

registerAuthStateClear(() => useAuthStore().clearSession())
