import request from './request'

// ========== 认证 ==========
export const authApi = {
  loginWxWork: (code: string, corp_id?: string) =>
    request.post('/auth/login/wxwork', { code, corp_id }),
  loginDemo: () => request.post('/auth/login/demo'),
  getMe: () => request.get('/auth/me'),
  getOAuthUrl: (redirect_uri: string, corp_id?: string) =>
    request.get('/auth/wxwork/oauth_url', { params: { redirect_uri, corp_id } }),
}

// ========== 群管理 ==========
export const groupApi = {
  list: (params: any) => request.get('/groups', { params }),
  overview: () => request.get('/groups/overview'),
  levelSummary: () => request.get('/groups/level-summary'),
  byLevel: (level: number, params: any) => request.get(`/groups/by-level/${level}`, { params }),
  detail: (chatId: string) => request.get(`/groups/${chatId}`),
  members: (chatId: string, params: any) => request.get(`/groups/${chatId}/members`, { params }),
  stats: (chatId: string, params: any) => request.get(`/groups/${chatId}/stats`, { params }),
  sentiment: (chatId: string, days = 7) => request.get(`/groups/${chatId}/sentiment`, { params: { days } }),
  messages: (chatId: string, limit = 120) => request.get(`/groups/${chatId}/messages`, { params: { limit } }),
  digest: (chatId: string, day?: string) => request.get(`/groups/${chatId}/digest`, { params: { day } }),
  update: (chatId: string, data: any) => request.patch(`/groups/${chatId}`, data),
  sync: () => request.post('/groups/sync'),
  classifyRun: (only_unknown = false) =>
    request.post('/groups/classify/run', {}, { params: { only_unknown }, timeout: 180000 }),
  classifySummary: () => request.get('/groups/classify/summary'),
  setClientKind: (chatId: string, kind: string) => request.post(`/groups/${chatId}/client-kind`, { kind }),
}

// ========== 后台配置 ==========
export const adminApi = {
  getCorpConfig: () => request.get('/admin/corp-config'),
  saveCorpConfig: (data: any) => request.post('/admin/corp-config', data),
  testConnection: () => request.post('/admin/test-connection'),
  getSystemConfig: () => request.get('/admin/system-config'),
  saveSystemConfig: (configs: any) => request.post('/admin/system-config', configs),
  getUsers: () => request.get('/admin/users'),
  updateUserRole: (data: any) => request.post('/admin/users/role', data),
  getSyncLogs: (params: any) => request.get('/admin/sync-logs', { params }),
}

// ========== 客服效能 ==========
export const staffApi = {
  overview: (params: any = {}) => request.get('/staff/overview', { params }),
  ranking: (params: any = {}) => request.get('/staff/ranking', { params }),
  timeouts: (params: any = {}) => request.get('/staff/timeouts', { params }),
  getStaffNames: () => request.get('/staff/staff-names'),
  setStaffNames: (names: string[]) => request.post('/staff/staff-names', { names }),
}

// ========== 驾驶舱 ==========
export const dashboardApi = {
  todayActions: () => request.get('/dashboard/today-actions'),
}

// ========== AI 群日报 ==========
export const aiApi = {
  run: (params: any = {}) => request.post('/ai/daily-report/run', null, { params }),
  summaries: (params: any = {}) => request.get('/ai/summaries', { params }),
  brief: (params: any = {}) => request.get('/ai/brief', { params }),
}

// ========== 客户流失预警 ==========
export const churnApi = {
  list: () => request.get('/churn/list'),
  scan: () => request.post('/churn/scan'),
}

// ========== 查件 + 客户匹配(新智慧NextSLS) ==========
export const trackingApi = {
  status: () => request.get('/tracking/status'),
  byNumber: (number: string) => request.get('/tracking/by-number', { params: { number } }),
  byGroup: (chat_id: string, limit = 10) => request.get('/tracking/by-group', { params: { chat_id, limit } }),
  matchRun: () => request.post('/tracking/match/run', {}, { timeout: 180000 }),
  matchList: () => request.get('/tracking/match/list'),
  matchSet: (data: any) => request.post('/tracking/match/set', data),
}

// ========== 预警 ==========
export const alertApi = {
  list: (params: any) => request.get('/alerts', { params }),
  markRead: (data: any) => request.post('/alerts/read', data),
}
