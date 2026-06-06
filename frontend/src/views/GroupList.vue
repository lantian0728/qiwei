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
      </div>

      <el-table :data="list" v-loading="loading" style="margin-top:16px" @row-click="goDetail">
        <el-table-column prop="group_name" label="群名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="group_type_name" label="类型" width="90" />
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
                       layout="total, prev, pager, next" @change="load" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { groupApi } from '@/api'

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

onMounted(load)
</script>

<style scoped>
.filters { display: flex; gap: 12px; flex-wrap: wrap; }
:deep(.el-table__row) { cursor: pointer; }
</style>
