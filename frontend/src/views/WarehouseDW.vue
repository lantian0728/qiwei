<template>
  <div class="wh-dw" v-loading="loading">
    <div class="hd">
      <h3>仓库预约 / DW 数据 <small>每周从公众号「美国物流周况」更新一次</small></h3>
    </div>

    <el-card shadow="never" style="margin-bottom:16px">
      <div class="tip">
        把公众号的<b>元宝总结</b>整段复制粘贴到下面，点「AI 解析」，系统自动提取各仓预约推迟天数。
        之后货到港就能按目的仓算出预计 DW。
      </div>
      <el-input v-model="text" type="textarea" :rows="6" placeholder="粘贴元宝总结全文（含各仓批约推迟/不批约/关单等）…" />
      <div class="ops">
        <el-input v-model="weekLabel" placeholder="周次 如 2026.06.06" style="width:200px" size="default" />
        <el-button type="primary" :loading="parsing" @click="doUpdate">
          <el-icon><MagicStick /></el-icon> AI 解析并更新
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <b>当前各仓预约情况（{{ list.length }} 个仓）</b>
        <span v-if="list.length" style="color:#909399;font-size:12px;margin-left:8px">数据周次：{{ list[0].week_label }}</span>
      </template>
      <el-table :data="list" max-height="520" size="default"
                :default-sort="{ prop: 'delay_days', order: 'descending' }">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="warehouse" label="仓代码" width="130" />
        <el-table-column prop="delay_days" label="预约推迟" width="130" sortable>
          <template #default="{ row }">
            <span v-if="row.delay_days >= 99" style="color:#F56C6C;font-weight:600">{{ row.status }}</span>
            <span v-else :style="{ color: row.delay_days >= 14 ? '#E6A23C' : '#67C23A', fontWeight: 600 }">
              推迟 {{ row.delay_days }} 天
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.delay_days >= 99 ? 'danger' : row.delay_days >= 14 ? 'warning' : 'success'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!list.length" class="empty">还没数据 —— 粘贴公众号总结，点「AI 解析」一次即可</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { trackingApi } from '@/api'
import { startTask } from '@/utils/loading'

const loading = ref(false)
const parsing = ref(false)
const text = ref('')
const weekLabel = ref('')
const list = ref<any[]>([])

const load = async () => {
  loading.value = true
  try {
    list.value = (await trackingApi.warehouseList()) as any
  } finally {
    loading.value = false
  }
}

const doUpdate = async () => {
  if (!text.value.trim()) {
    ElMessage.warning('先粘贴公众号总结文本')
    return
  }
  parsing.value = true
  const t = startTask('🤖 AI 正在解析各仓预约')
  try {
    const r: any = await trackingApi.warehouseUpdate(text.value, weekLabel.value)
    if (r.error) {
      ElMessage.error(r.error)
    } else {
      ElMessage.success(`已解析并更新 ${r.saved} 个仓`)
      text.value = ''
      await load()
    }
  } finally {
    parsing.value = false
    t.close()
  }
}

onMounted(load)
</script>

<style scoped>
.wh-dw .hd { margin-bottom: 16px; }
.hd h3 { margin: 0; font-size: 16px; }
.hd small { color: #909399; font-weight: 400; font-size: 13px; margin-left: 8px; }
.tip { color: #606266; font-size: 13px; margin-bottom: 10px; line-height: 1.7; }
.ops { margin-top: 12px; display: flex; gap: 10px; }
.empty { text-align: center; color: #c0c4cc; padding: 24px 0; }
</style>
