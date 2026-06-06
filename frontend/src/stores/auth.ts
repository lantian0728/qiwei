import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('access_token') || '')
  const userInfo = ref<any>(JSON.parse(localStorage.getItem('user_info') || 'null'))

  function setAuth(accessToken: string, user: any) {
    token.value = accessToken
    userInfo.value = user
    localStorage.setItem('access_token', accessToken)
    localStorage.setItem('user_info', JSON.stringify(user))
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_info')
  }

  function isLoggedIn() {
    return !!token.value
  }

  return { token, userInfo, setAuth, logout, isLoggedIn }
})
