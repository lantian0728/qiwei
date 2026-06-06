<template>
  <div class="admin-page">
    <el-tabs v-model="activeTab" type="border-card">
      <!-- 企业微信API配置 -->
      <el-tab-pane label="企业微信API配置" name="wxwork">
        <div class="tab-content">
          <el-alert
            title="配置说明：请在企业微信管理后台创建自建应用，获取CorpID、AgentID和Secret后填入下方"
            type="info" show-icon :closable="false" style="margin-bottom:20px" />

          <el-form :model="corpForm" label-width="160px" style="max-width:600px">
            <el-form-item label="企业ID (CorpID)" required>
              <el-input v-model="corpForm.corp_id" placeholder="ww开头的企业ID" />
            </el-form-item>
            <el-form-item label="企业名称">
              <el-input v-model="corpForm.corp_name" placeholder="企业名称（显示用）" />
            </el-form-item>
            <el-form-item label="应用ID (AgentID)" required>
              <el-input v-model="corpForm.agent_id" placeholder="自建应用的AgentID" />
            </el-form-item>
            <el-form-item label="应用Secret" required>
              <el-input v-model="corpForm.corp_secret" type="password" show-password
                        placeholder="自建应用的Secret（加密存储）" />
            </el-form-item>
            <el-form-item label="Webhook通知URL（可选）">
              <el-input v-model="corpForm.webhook_url" placeholder="预警通知Webhook地址" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveCorpConfig" :loading="saving">保存配置</el-button>
              <el-button @click="testConnection" :loading="testing" style="margin-left:8px">测试连接</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 系统参数 -->
      <el-tab-pane label="系统参数" name="system">
        <div class="tab-content">
          <el-form :model="sysForm" label-width="200px" style="max-width:600px">
            <el-divider content-position="left">活跃度分级阈值</el-divider>
            <el-form-item label="高活跃评分阈值">
              <el-input-number v-model="sysForm.high_active_threshold" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="正常活跃评分阈值">
              <el-input-number v-model="sysForm.normal_active_threshold" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="低活跃评分阈值">
              <el-input-number v-model="sysForm.low_active_threshold" :min="0" :max="100" />
            </el-form-item>

            <el-divider content-position="left">预警配置</el-divider>
            <el-form-item label="沉默群超时天数">
              <el-input-number v-model="sysForm.silent_days" :min="1" :max="30" />
            </el-form-item>
            <el-form-item label="启用预警通知">
              <el-switch v-model="sysForm.alert_enabled" />
            </el-form-item>

            <el-divider content-position="left">数据同步配置</el-divider>
            <el-form-item label="自动同步间隔（分钟）">
              <el-input-number v-model="sysForm.sync_interval" :min="10" :max="1440" />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="saveSysConfig" :loading="savingSys">保存系统参数</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 用户权限 -->
      <el-tab-pane label="用户权限" name="users">
        <div class="tab-content">
          <el-table :data="users" v-loading="usersLoading">
            <el-table-column prop="userid" label="企业微信ID" width="150" />
            <el-table-column prop="username" label="姓名" width="120" />
            <el-table-column prop="real_name" label="真实姓名" width="120" />
            <el-table-column prop="department" label="部门" width="120" />
            <el-table-column label="角色" width="140">
              <template #default="{ row }">
                <el-select v-model="row.role" size="small" @change="updateRole(row)">
                  <el-option label="超级管理员" :value="1" />
                  <el-option label="管理员" :value="2" />
                  <el-option label="运营" :value="3" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="最后登录" width="160">
              <template #default="{ row }">
                {{ row.last_login_at ? dayjs(row.last_login_at).format('YYYY-MM-DD HH:mm') : '-' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 同步日志 -->
      <el-tab-pane label="同步日志" name="logs">
        <div class="tab-content">
          <el-table :data="syncLogs" v-loading="logsLoading" size="small">
            <el-table-column prop="sync_type" label="同步类型" width="120" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.status === 2 ? 'success' : row.status === 3 ? 'danger' : 'warning'" size="small">
                  {{ row.status_name }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_count" label="总数" width="80" align="center" />
            <el-table-column prop="success_count" label="成功" width="80" align="center" />
            <el-table-column prop="fail_count" label="失败" width="80" align="center" />
            <el-table-column prop="error_msg" label="错误信息" show-overflow-tooltip />
            <el-table-column label="开始时间" width="160">
              <template #default="{ row }">
                {{ row.started_at ? dayjs(row.started_at).format('MM-DD HH:mm:ss') : '-' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api'

const activeTab = ref('wxwork')
const saving = ref(false)
const testing = ref(false)
const savingSys = ref(false)
const usersLoading = ref(false)
const logsLoading = ref(false)

const corpForm = ref({
  corp_id: '', corp_name: '', agent_id: '', corp_secret: '', webhook_url: '',
})

const sysForm = ref<any>({
  high_active_threshold: 70, normal_active_threshold: 40, low_active_threshold: 15,
  silent_days: 7, alert_enabled: true, sync_interval: 30,
})

const users = ref<any[]>([])
const syncLogs = ref<any[]>([])

const loadCorpConfig = async () => {
  try {
    const res: any = await adminApi.getCorpConfig()
    if (res.configured) Object.assign(corpForm.value, res)
  } catch {}
}

const saveCorpConfig = async () => {
  saving.value = true
  try {
    await adminApi.saveCorpConfig(corpForm.value)
    ElMessage.success('企业微信配置保存成功')
  } finally {
    saving.value = false
  }
}

const testConnection = async () => {
  testing.value = true
  try {
    const res: any = await adminApi.testConnection()
    res.success ? ElMessage.success(res.message) : ElMessage.error(res.message)
  } finally {
    testing.value = false
  }
}

const loadSysConfig = async () => {
  try {
    const res: any = await adminApi.getSystemConfig()
    Object.keys(res || {}).forEach((k) => {
      if (k in sysForm.value) {
        const v = res[k]
        sysForm.value[k] = v === 'true' ? true : v === 'false' ? false : isNaN(Number(v)) ? v : Number(v)
      }
    })
  } catch {}
}

const saveSysConfig = async () => {
  savingSys.value = true
  try {
    await adminApi.saveSystemConfig({ ...sysForm.value })
    ElMessage.success('系统参数保存成功')
  } finally {
    savingSys.value = false
  }
}

const loadUsers = async () => {
  usersLoading.value = true
  try {
    users.value = (await adminApi.getUsers()) as any
  } finally {
    usersLoading.value = false
  }
}

const updateRole = async (user: any) => {
  await adminApi.updateUserRole({ userid: user.userid, role: user.role })
  ElMessage.success('角色已更新')
}

const loadLogs = async () => {
  logsLoading.value = true
  try {
    const res: any = await adminApi.getSyncLogs({ page: 1, page_size: 20 })
    syncLogs.value = res.items || []
  } finally {
    logsLoading.value = false
  }
}

onMounted(async () => {
  await loadCorpConfig()
  await loadSysConfig()
  await loadUsers()
  await loadLogs()
})
</script>

<style scoped>
.tab-content { padding: 16px 0; }
</style>
