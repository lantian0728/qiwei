<template>
  <div class="churn" v-loading="loading">
    <div class="stat-row">
      <div class="stat-card"><div class="v">{{ data.total ?? 0 }}</div><div class="l">客户群总数</div></div>
      <div class="stat-card danger"><div class="v">{{ data.high ?? 0 }}</div><div class="l">高流失风险</div></div>
      <div class="stat-card warn"><div class="v">{{ data.medium ?? 0 }}</div><div class="l">中流失风险</div></div>
      <div class="stat-card"><div class="v">{{ safeCount }}</div><div class="l">健康</div></div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <span>客户流失风险榜</span>
        <el-button size="small" type="primary" :loading="scanning" @click="scan">
          <el-icon><Refresh /></el-icon> 重新扫描并生成预警
        </el-button>
      </div>
      <el-table :data="data.items" size="default" @row-click="(r:any)=>$router.push(`/groups/${r.chat_id}`)"
                row-class-name="clickable">
        <el-table-column label="风险" width="90">
          <template #default="{ row }">
            <el-tag :type="riskType(row.churn_risk)" effect="dark" v-if="row.churn_risk!=='none'" size="small">
              {{ riskName(row.churn_risk) }}
            </el-tag>
            <el-tag type="success" effect="plain" v-else size="small">健康</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="客户群" min-width="180">
          <template #default="{ row }">
            <span>{{ row.group_name }}</span>
            <el-tag v-if="row.is_key_group" size="small" type="warning" effect="plain" style="margin-left:6px">重点</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="风险分" width="150">
          <template #default="{ row }">
            <el-progress :percentage="row.churn_score" :stroke-width="10"
              :color="barColor(row.churn_risk)" :format="()=>row.churn_score" />
          </template>
        </el-table-column>
        <el-table-column label="货量变化" width="120">
          <template #default="{ row }">
            <span :class="{ down: row.drop_pct > 0 }">
              {{ row.drop_pct > 0 ? '↓' + row.drop_pct + '%' : (row.drop_pct < 0 ? '↑' + (-row.drop_pct) + '%' : '持平') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="信号" min-width="240">
          <template #default="{ row }">
            <el-tag v-for="r in row.reasons" :key="r" size="small" effect="plain"
                    :type="row.churn_risk==='high'?'danger':row.churn_risk==='medium'?'warning':'info'"
                    style="margin:2px 4px 2px 0">{{ r }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner_name" label="负责客服" width="100" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { churnApi } from '@/api'

const loading = ref(false)
const scanning = ref(false)
const data = ref<any>({ items: [] })

const safeCount = computed(() => (data.value.total ?? 0) - (data.value.high ?? 0) - (data.value.medium ?? 0))
const riskName = (r: string) => ({ high: '高', medium: '中', low: '低' } as any)[r] || ''
const riskType = (r: string) => ({ high: 'danger', medium: 'warning', low: 'info' } as any)[r] || 'info'
const barColor = (r: string) => ({ high: '#F56C6C', medium: '#E6A23C', low: '#409EFF' } as any)[r] || '#67C23A'

const load = async () => {
  loading.value = true
  try { data.value = (await churnApi.list()) as any } finally { loading.value = false }
}
const scan = async () => {
  scanning.value = true
  try {
    const r: any = await churnApi.scan()
    ElMessage.success(`扫描完成，新增 ${r.new_alerts} 条预警`)
    await load()
  } finally { scanning.value = false }
}
onMounted(load)
</script>

<style scoped>
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.stat-card { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.stat-card .v { font-size: 26px; font-weight: 700; }
.stat-card.danger .v { color: #F56C6C; }
.stat-card.warn .v { color: #E6A23C; }
.stat-card .l { font-size: 12px; color: #909399; margin-top: 6px; }
.panel { background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.panel-head { display: flex; align-items: center; justify-content: space-between; font-size: 15px; font-weight: 600; margin-bottom: 14px; }
.down { color: #F56C6C; font-weight: 600; }
:deep(.clickable) { cursor: pointer; }
</style>
