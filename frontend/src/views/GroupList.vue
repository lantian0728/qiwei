<template>
  <div class="group-list">
    <div class="ov-cards">
      <div class="ov-card"><b>{{ clientStat.total ?? total }}</b><span>监测群</span></div>
      <div class="ov-card"><b class="agent">{{ clientStat.agent ?? 0 }}</b><span>代理群</span></div>
      <div class="ov-card"><b class="direct">{{ clientStat.direct ?? 0 }}</b><span>直客群</span></div>
      <div class="ov-card"><b class="unknown">{{ clientStat.unknown ?? 0 }}</b><span>未判定</span></div>
    </div>
    <el-card shadow="never">
      <!-- 筛选栏 -->
      <div class="filters">
        <el-input v-model="filters.keyword" placeholder="搜索群名" clearable
                  style="width:200px" @keyup.enter="load" @clear="load">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filters.activity_level" placeholder="活跃度" clearable
                   style="width:130px" @change="load">
          <el-option label="高活跃" :value="1" />
          <el-option label="正常" :value="2" />
          <el-option label="低活跃" :value="3" />
          <el-option label="沉默" :value="4" />
        </el-select>
        <el-select v-model="filters.group_type" placeholder="群类型" clearable
                   style="width:130px" @change="load">
          <el-option label="客户群" :value="1" />
          <el-option label="内部群" :value="2" />
          <el-option label="项目群" :value="3" />
          <el-option label="渠道群" :value="4" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button :loading="classifying" @click="runClassify">
          <el-icon><MagicStick /></el-icon> AI 识别代理/直客
        </el-button>
      </div>

      <el-table :data="list" v-loading="loading" style="margin-top:16px" @row-click="goDetail">
        <el-table-column prop="group_name" label="群名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="group_type_name" label="类型" width="80" />
        <el-table-column label="客户类型" width="110">
          <template #default="{ row }">
            <span @click.stop>
              <el-dropdown trigger="click" @command="(k:string)=>setKind(row, k)">
                <el-tag :type="row.client_kind==='agent'?'warning':row.client_kind==='direct'?'success':'info'"
                        size="small" :effect="row.client_kind_conf===100?'dark':'light'" style="cursor:pointer">
                  {{ row.client_kind==='agent'?'代理':row.client_kind==='direct'?'直客':'未判定' }}
                  {{ row.client_kind_conf===100 ? ' ✓' : '' }}
                </el-tag>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="agent">代理</el-dropdown-item>
                    <el-dropdown-item command="direct">直客</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="群主" width="100" show-overflow-tooltip />
        <el-table-column prop="member_count" label="成员" width="70" align="center" />
        <el-table-column label="活跃度" width="100">
          <template #default="{ row }">
            <el-tag :color="row.activity_level_color" effect="dark" style="border:none">
              {{ row.activity_level_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="重点" width="60" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.is_key_group" color="#E6A23C"><StarFilled /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="最后活跃" width="160">
          <template #default="{ row }">
            {{ row.last_msg_time ? dayjs(row.last_msg_time).format('MM-DD HH:mm') : '-' }}
          </template>
        </el-table-column>
      </el-table>

      <div style="display:flex;justify-content:flex-end;margin-top:16px">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
                       :pager-count="7" background
                       layout="total, prev, pager, next, jumper" @current-change="load" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { groupApi } from '@/api'
import { startTask } from '@/utils/loading'

const route = useRoute()
const router = useRouter()
const list = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)

const filters = reactive<any>({
  keyword: '',
  activity_level: route.query.level ? Number(route.query.level) : null,
  group_type: null,
})

const load = async () => {
  loading.value = true
  try {
    const res: any = await groupApi.list({
      page: page.value, page_size: pageSize,
      keyword: filters.keyword || undefined,
      activity_level: filters.activity_level || undefined,
      group_type: filters.group_type || undefined,
    })
    list.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

const goDetail = (row: any) => router.push(`/groups/${row.chat_id}`)

const setKind = async (row: any, kind: string) => {
  try {
    const r: any = await groupApi.setClientKind(row.chat_id, kind)
    row.client_kind = kind
    row.client_kind_conf = 100
    clientStat.value = r
    ElMessage.success('已设为' + (kind === 'agent' ? '代理' : '直客') + '（已锁定，AI 不再改）')
  } catch {
    ElMessage.error('设置失败')
  }
}

const classifying = ref(false)
const clientStat = ref<any>({})
const loadStat = async () => { clientStat.value = await groupApi.classifySummary() }
const runClassify = async () => {
  classifying.value = true
  const task = startTask('🤖 智谱正在识别代理/直客')
  try {
    const r: any = await groupApi.classifyRun()
    ElMessage.success(`分类完成：代理 ${r.agent} / 直客 ${r.direct} / 未判定 ${r.unknown}（AI 判 ${r.ai_used ?? 0} 个）`)
    await loadStat()
    await load()
  } catch (e: any) {
    ElMessage.error('分类失败：' + (e?.response?.data?.detail || e?.message || '稍后重试'))
  } finally {
    classifying.value = false
    task.close()
  }
}

onMounted(() => { load(); loadStat() })
</script>

<style scoped>
.filters { display: flex; gap: 12px; flex-wrap: wrap; }
.ov-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.ov-card { background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.ov-card b { font-size: 28px; font-weight: 700; color: #303133; }
.ov-card b.agent { color: #E6A23C; }
.ov-card b.direct { color: #67C23A; }
.ov-card b.unknown { color: #909399; }
.ov-card span { display: block; font-size: 13px; color: #909399; margin-top: 6px; }
:deep(.el-table__row) { cursor: pointer; }
</style>
