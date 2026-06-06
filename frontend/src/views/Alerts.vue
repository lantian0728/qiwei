<template>
  <div class="alerts">
    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <b>预警管理</b>
          <el-button size="small" type="primary" @click="markAll">全部标记已读</el-button>
        </div>
      </template>

      <el-table :data="list" v-loading="loading">
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <el-tag :type="row.alert_level === 1 ? 'danger' : row.alert_level === 2 ? 'warning' : 'info'" size="small">
              {{ row.alert_level_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="alert_type_name" label="类型" width="110" />
        <el-table-column prop="group_name" label="群" width="200" show-overflow-tooltip />
        <el-table-column prop="content" label="内容" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_read ? 'info' : 'success'" size="small">
              {{ row.is_read ? '已读' : '未读' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ dayjs(row.created_at).format('MM-DD HH:mm') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button v-if="!row.is_read" link type="primary" size="small" @click="markOne(row)">
              标记已读
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="display:flex;justify-content:flex-end;margin-top:16px">
        <el-pagination v-model:current-page="page" :page-size="20" :total="total"
                       layout="total, prev, pager, next" @change="load" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { alertApi } from '@/api'

const list = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)

const load = async () => {
  loading.value = true
  try {
    const res: any = await alertApi.list({ page: page.value, page_size: 20 })
    list.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

const markOne = async (row: any) => {
  await alertApi.markRead({ ids: [row.id] })
  ElMessage.success('已标记')
  load()
}

const markAll = async () => {
  await alertApi.markRead({ all: true })
  ElMessage.success('已全部标记已读')
  load()
}

onMounted(load)
</script>
