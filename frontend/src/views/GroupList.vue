<template>
  <div class="group-list">
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

      <div class="client-stat">
        <span class="cs agent">代理群 <b>{{ clientStat.agent ?? 0 }}</b></span>
        <span class="cs direct">直客群 <b>{{ clientStat.direct ?? 0 }}</b></span>
        <span class="cs unknown">未判定 <b>{{ clientStat.unknown ?? 0 }}</b></span>
      </div>

      <el-table :data="list" v-loading="loading" style="margin-top:16px" @row-click="goDetail">
        <el-table-column prop="group_name" label="群名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="group_type_name" label="类型" width="80" />
        <el-table-column label="客户类型" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.client_kind==='agent'" type="warning" size="small">代理</el-tag>
            <el-tag v-else-if="row.client_kind==='direct'" type="success" size="small">直客</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">未判定</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="群主" width="100" />
        <el-table-column prop="member_count" label="成员数" width="80" align="center" />
        <el-table-column label="活跃度" width="120">
          <template #default="{ row }">
            <el-tag :color="row.activity_level_color" effect="dark" style="border:none">
              {{ row.activity_level_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="activity_score" label="评分" width="90" align="center">
          <template #default="{ row }">{{ row.activity_score }}</template>
        </el-table-column>
        <el-table-column label="重点" width="70" align="center">
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
.client-stat { display: flex; gap: 24px; margin-top: 14px; padding: 10px 14px; background: #f5f7fa; border-radius: 8px; }
.cs { font-size: 14px; color: #606266; }
.cs b { font-size: 18px; margin-left: 4px; }
.cs.agent b { color: #E6A23C; }
.cs.direct b { color: #67C23A; }
.cs.unknown b { color: #909399; }
:deep(.el-table__row) { cursor: pointer; }
</style>
