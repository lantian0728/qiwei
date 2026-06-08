<template>
  <div class="tracking">
    <el-alert v-if="!nextslsOk" type="warning" :closable="false" show-icon style="margin-bottom:16px"
      title="未配置新智慧 NEXTSLS_TOKEN，查件不可用。请在 backend/.env 填入密钥后重启。" />

    <el-tabs v-model="tab">
      <!-- 按单号查 -->
      <el-tab-pane label="按单号查轨迹" name="number">
        <div class="panel">
          <div class="search-bar">
            <el-input v-model="number" placeholder="输入系统运单号 或 客户单号(client_reference)" size="large"
                      @keyup.enter="doTrackNumber" clearable style="max-width:480px">
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-button type="primary" size="large" :loading="loadingN" @click="doTrackNumber">查询</el-button>
          </div>

          <div v-if="result" class="result">
            <div v-if="!result.found" class="empty">{{ result.message || '未查到' }}</div>
            <template v-else>
              <div class="ship-head">
                <span class="sid">{{ result.shipment_id }}</span>
                <el-tag :type="statusType(result.status)" effect="dark">{{ result.status_name }}</el-tag>
                <span v-if="result.carrier_code" class="carrier">{{ result.carrier_code }} {{ result.tracking_number }}</span>
              </div>
              <el-timeline style="margin-top:18px">
                <el-timeline-item v-for="(t, i) in result.traces" :key="i"
                  :timestamp="t.time" placement="top" :type="i === 0 ? 'primary' : ''" :hollow="i !== 0">
                  <div class="trace-info">{{ t.info }}</div>
                  <div v-if="t.location" class="trace-loc">{{ t.location }}</div>
                  <div v-if="t.remark" class="trace-remark">{{ t.remark }}</div>
                </el-timeline-item>
              </el-timeline>
              <div v-if="!result.traces.length" class="empty">暂无路由信息</div>
            </template>
          </div>
        </div>
      </el-tab-pane>

      <!-- 群查件 -->
      <el-tab-pane label="按群查件 + 客户匹配" name="group">
        <div class="panel">
          <div class="panel-head">
            <span>群 ↔ 客户 映射 <el-tag size="small" type="info">智谱识别群名</el-tag></span>
            <el-button type="primary" size="small" :loading="matching" @click="runMatch">
              <el-icon><MagicStick /></el-icon> 自动匹配
            </el-button>
          </div>
          <el-table :data="mappings" size="default" max-height="360">
            <el-table-column prop="group_name" label="群名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="candidate" label="识别客户名" width="120" />
            <el-table-column label="匹配客户" width="160">
              <template #default="{ row }">
                <span v-if="row.customer_name">{{ row.customer_name }}
                  <span class="unum">({{ row.user_number }})</span>
                </span>
                <span v-else class="muted">未匹配</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag size="small" :type="row.match_status==='confirmed'?'success':row.match_status==='auto'?'warning':'info'">
                  {{ statusLabel(row.match_status) }}{{ row.confidence ? ' '+row.confidence : '' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openShipments(row)">查运单</el-button>
                <el-button link type="primary" size="small" @click="editMapping(row)">关联</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 客户运单 -->
        <div class="panel" v-if="groupResult" style="margin-top:16px">
          <div class="panel-head">
            <span>{{ groupResult.customer_name || '客户' }} 近期运单</span>
          </div>
          <div v-if="!groupResult.matched" class="empty">{{ groupResult.message }}</div>
          <el-table v-else :data="groupResult.shipments" size="small">
            <el-table-column prop="shipment_id" label="运单号" width="130" />
            <el-table-column prop="client_reference" label="客户单号" width="140" show-overflow-tooltip />
            <el-table-column prop="service_name" label="服务" min-width="160" show-overflow-tooltip />
            <el-table-column prop="main_name" label="品名" min-width="120" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="statusType(row.status)">{{ row.status_name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="" width="80">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="trackFromList(row.shipment_id)">轨迹</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 手动关联弹窗 -->
    <el-dialog v-model="editVisible" title="关联客户" width="420">
      <el-form label-width="90px">
        <el-form-item label="群名"><span>{{ editing.group_name }}</span></el-form-item>
        <el-form-item label="客户编号"><el-input v-model="editForm.user_number" placeholder="NextSLS user_number" /></el-form-item>
        <el-form-item label="客户名"><el-input v-model="editForm.customer_name" placeholder="客户名" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible=false">取消</el-button>
        <el-button type="primary" @click="saveMapping">确认关联</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { trackingApi } from '@/api'
import { startTask } from '@/utils/loading'

const tab = ref('number')
const nextslsOk = ref(true)

const number = ref('')
const result = ref<any>(null)
const loadingN = ref(false)

const mappings = ref<any[]>([])
const matching = ref(false)
const groupResult = ref<any>(null)

const editVisible = ref(false)
const editing = ref<any>({})
const editForm = ref({ user_number: '', customer_name: '' })

const statusType = (s: string) => (({
  delivered: 'success', in_transit: 'warning', returned: 'danger',
  cancelled: 'info', picked: 'warning', ready: 'info',
} as any)[s] || 'info')
const statusLabel = (s: string) => (({ confirmed: '已确认', auto: '自动', none: '未匹配' } as any)[s] || s)

const doTrackNumber = async () => {
  if (!number.value.trim()) return
  loadingN.value = true
  try { result.value = await trackingApi.byNumber(number.value.trim()) }
  finally { loadingN.value = false }
}

const trackFromList = async (sid: string) => {
  tab.value = 'number'; number.value = sid; await doTrackNumber()
}

const loadMappings = async () => { mappings.value = (await trackingApi.matchList()) as any }

const runMatch = async () => {
  matching.value = true
  const task = startTask('🔍 正在匹配群↔客户')
  try {
    const r: any = await trackingApi.matchRun()
    ElMessage.success(`匹配完成：${r.matched}/${r.total_groups} 个群关联到客户（客户库 ${r.directory_size} 人${r.ai_used ? `，智谱精修 ${r.ai_used} 个` : ''}）`)
    await loadMappings()
  } catch (e: any) {
    ElMessage.error('匹配失败：' + (e?.response?.data?.detail || e?.message || '请稍后重试'))
  } finally { matching.value = false; task.close() }
}

const openShipments = async (row: any) => {
  groupResult.value = await trackingApi.byGroup(row.chat_id)
}

const editMapping = (row: any) => {
  editing.value = row
  editForm.value = { user_number: row.user_number || '', customer_name: row.customer_name || '' }
  editVisible.value = true
}
const saveMapping = async () => {
  await trackingApi.matchSet({ chat_id: editing.value.chat_id, ...editForm.value })
  ElMessage.success('已关联')
  editVisible.value = false
  await loadMappings()
}

onMounted(async () => {
  try { const s: any = await trackingApi.status(); nextslsOk.value = !!s.nextsls_available } catch {}
  await loadMappings()
})
</script>

<style scoped>
.panel { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.panel-head { display: flex; align-items: center; justify-content: space-between; font-size: 15px; font-weight: 600; margin-bottom: 14px; }
.panel-head span { display: flex; align-items: center; gap: 8px; }
.search-bar { display: flex; gap: 12px; }
.result { margin-top: 22px; }
.ship-head { display: flex; align-items: center; gap: 12px; }
.ship-head .sid { font-size: 18px; font-weight: 700; }
.carrier { color: #909399; font-size: 13px; }
.trace-info { font-weight: 600; color: #303133; }
.trace-loc { color: #606266; font-size: 13px; margin-top: 2px; }
.trace-remark { color: #909399; font-size: 12px; }
.empty { text-align: center; color: #c0c4cc; padding: 24px 0; }
.unum { color: #c0c4cc; font-size: 12px; }
.muted { color: #c0c4cc; }
</style>
