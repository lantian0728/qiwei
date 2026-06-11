<template>
  <div class="login-page">
    <div class="login-bg">
      <div class="bg-circle bg-circle-1"></div>
      <div class="bg-circle bg-circle-2"></div>
      <div class="bg-circle bg-circle-3"></div>
    </div>

    <div class="login-container">
      <div class="login-header">
        <div class="logo-icon">
          <el-icon size="40" color="#fff"><ChatDotRound /></el-icon>
        </div>
        <h1 class="system-title">企微群会话分析系统</h1>
        <p class="system-subtitle">企业微信群数据监测 · 活跃度分析 · 智能运营管理</p>
      </div>

      <div class="login-card">
        <el-tabs v-model="activeTab" class="login-tabs">
          <el-tab-pane label="企业微信扫码" name="scan">
            <div class="wxwork-login">
              <div id="ww_qr" style="display:flex;justify-content:center;min-height:240px"></div>
              <p class="wxwork-desc">打开企业微信 App 扫一扫登录</p>
            </div>
          </el-tab-pane>
          <el-tab-pane label="账号登录" name="password">
            <div class="pwd-login">
              <el-form :model="pwdForm">
                <el-form-item>
                  <el-input v-model="pwdForm.username" placeholder="账号" size="large">
                    <template #prefix><el-icon><User /></el-icon></template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="pwdForm.password" type="password" show-password placeholder="密码"
                            size="large" @keyup.enter="handlePwdLogin">
                    <template #prefix><el-icon><Lock /></el-icon></template>
                  </el-input>
                </el-form-item>
              </el-form>
              <el-button type="primary" size="large" style="width:100%;margin-top:8px"
                         :loading="loading" @click="handlePwdLogin">登 录</el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane label="企业微信授权登录" name="wxwork">
            <div class="wxwork-login">
              <div class="wxwork-icon">
                <el-icon size="60" color="#07C160"><ChatDotRound /></el-icon>
              </div>
              <p class="wxwork-desc">使用企业微信账号扫码或点击授权登录</p>
              <el-form :model="wxForm" label-width="0" style="margin-top:20px">
                <el-form-item>
                  <el-input v-model="wxForm.corpId" placeholder="企业ID（CorpID）" size="large">
                    <template #prefix><el-icon><OfficeBuilding /></el-icon></template>
                  </el-input>
                </el-form-item>
                <el-form-item>
                  <el-input v-model="wxForm.code" placeholder="OAuth2 Code（从企业微信回调获取）" size="large">
                    <template #prefix><el-icon><Key /></el-icon></template>
                  </el-input>
                </el-form-item>
              </el-form>
              <el-button type="primary" size="large" style="width:100%;margin-top:8px"
                         :loading="loading" @click="handleWxLogin">
                企业微信授权登录
              </el-button>
              <div class="login-divider"><span>或</span></div>
              <el-button size="large" style="width:100%" @click="getOAuthUrl">
                获取企业微信授权链接
              </el-button>
            </div>
          </el-tab-pane>

        </el-tabs>
      </div>

      <p class="login-footer">仅只读监测 · 不发送消息 · 数据安全合规</p>
    </div>
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
const activeTab = ref('scan')
const loading = ref(false)
const wxForm = ref({ corpId: '', code: '' })
const pwdForm = ref({ username: '', password: '' })

const handlePwdLogin = async () => {
  if (!pwdForm.value.username || !pwdForm.value.password) {
    ElMessage.warning('请输入账号和密码'); return
  }
  loading.value = true
  try {
    const res: any = await authApi.loginPassword(pwdForm.value.username, pwdForm.value.password)
    authStore.setAuth(res.access_token, res.user_info)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '账号或密码错误')
  } finally {
    loading.value = false
  }
}

const handleWxLogin = async () => {
  if (!wxForm.value.code) {
    ElMessage.warning('请输入企业微信OAuth2 Code')
    return
  }
  loading.value = true
  try {
    const res: any = await authApi.loginWxWork(wxForm.value.code, wxForm.value.corpId)
    authStore.setAuth(res.access_token, res.user_info)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}

const handleDemoLogin = async () => {
  loading.value = true
  try {
    const res: any = await authApi.loginDemo()
    authStore.setAuth(res.access_token, res.user_info)
    ElMessage.success('已进入演示模式')
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}

const getOAuthUrl = async () => {
  if (!wxForm.value.corpId) {
    ElMessage.warning('请先输入企业ID')
    return
  }
  try {
    const redirectUri = window.location.origin + '/auth/callback'
    const res: any = await authApi.getOAuthUrl(redirectUri, wxForm.value.corpId)
    window.open(res.oauth_url, '_blank')
  } catch (e) {
    ElMessage.error('获取授权链接失败')
  }
}

function loadWwLogin(): Promise<void> {
  return new Promise((resolve) => {
    if ((window as any).WwLogin) return resolve()
    const s = document.createElement('script')
    s.src = 'https://wwcdn.weixin.qq.com/node/wework/wwopen/js/wwLogin-1.2.7.js'
    s.onload = () => resolve()
    s.onerror = () => resolve()
    document.head.appendChild(s)
  })
}

const renderQr = async () => {
  try {
    const cfg: any = await authApi.scanConfig()
    if (!cfg.enabled) { activeTab.value = 'password'; return }
    await loadWwLogin()
    const W = (window as any).WwLogin
    if (!W) { activeTab.value = 'password'; return }
    const box = document.getElementById('ww_qr')
    if (box) box.innerHTML = ''
    W({
      id: 'ww_qr',
      appid: cfg.corp_id,
      agentid: String(cfg.agent_id),
      redirect_uri: encodeURIComponent(window.location.origin + '/auth/callback'),
      state: 'wxlogin',
      href: '',
      lang: 'zh',
    })
  } catch (e) {
    activeTab.value = 'password'
  }
}

onMounted(() => { renderQr() })
</script>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
  position: relative; overflow: hidden;
}
.login-bg { position: absolute; inset: 0; pointer-events: none; }
.bg-circle { position: absolute; border-radius: 50%; opacity: 0.15; }
.bg-circle-1 { width: 400px; height: 400px; background: #409EFF; top: -100px; left: -100px; animation: float 8s ease-in-out infinite; }
.bg-circle-2 { width: 300px; height: 300px; background: #67C23A; bottom: -50px; right: 100px; animation: float 6s ease-in-out infinite reverse; }
.bg-circle-3 { width: 200px; height: 200px; background: #E6A23C; top: 50%; right: -50px; animation: float 10s ease-in-out infinite; }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-20px); } }
.login-container { width: 480px; position: relative; z-index: 1; }
.login-header { text-align: center; margin-bottom: 32px; }
.logo-icon {
  width: 80px; height: 80px; background: linear-gradient(135deg, #409EFF, #1E6FBB);
  border-radius: 20px; display: flex; align-items: center; justify-content: center;
  margin: 0 auto 16px; box-shadow: 0 8px 24px rgba(64,158,255,0.4);
}
.system-title { font-size: 28px; font-weight: 700; color: #fff; margin-bottom: 8px; }
.system-subtitle { color: rgba(255,255,255,0.7); font-size: 14px; }
.login-card { background: rgba(255,255,255,0.98); border-radius: 16px; padding: 32px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
.wxwork-login, .demo-login { padding: 16px 0; text-align: center; }
.wxwork-icon, .demo-icon { margin-bottom: 16px; }
.wxwork-desc, .demo-desc { color: #606266; font-size: 14px; line-height: 1.6; margin-bottom: 8px; }
.login-divider { display: flex; align-items: center; margin: 16px 0; color: #c0c4cc; font-size: 12px; }
.login-divider::before, .login-divider::after { content: ''; flex: 1; height: 1px; background: #e4e7ed; }
.login-divider span { padding: 0 12px; }
.login-footer { text-align: center; color: rgba(255,255,255,0.5); font-size: 12px; margin-top: 24px; }
</style>
