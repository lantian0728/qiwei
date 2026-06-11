<template>
  <div class="callback-page">
    <el-icon class="is-loading" size="40"><Loading /></el-icon>
    <p>{{ msg }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api'

const router = useRouter()
const authStore = useAuthStore()
const msg = ref('正在登录…')

onMounted(async () => {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const corpId = params.get('appid') || undefined
  if (!code) {
    msg.value = '未获取到授权码，返回登录页…'
    setTimeout(() => router.replace('/login'), 1500)
    return
  }
  try {
    const res: any = await authApi.loginWxWork(code, corpId)
    authStore.setAuth(res.access_token, res.user_info)
    ElMessage.success('登录成功')
    // 二维码是 iframe 嵌入的，回调可能跑在 iframe 内 → 用顶层窗口整页跳转
    if (window.top && window.top !== window.self) {
      window.top.location.href = '/dashboard'
    } else {
      router.replace('/dashboard')
    }
  } catch (e: any) {
    msg.value = e?.response?.data?.detail || '登录失败，返回登录页…'
    setTimeout(() => router.replace('/login'), 2000)
  }
})
</script>

<style scoped>
.callback-page {
  min-height: 100vh; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 16px;
  background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
}
.callback-page p { color: #fff; font-size: 14px; }
</style>
