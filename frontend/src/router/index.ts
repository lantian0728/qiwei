import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue') },
  {
    path: '/',
    component: () => import('@/layout/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '经营驾驶舱' } },
      { path: 'staff', name: 'staff', component: () => import('@/views/StaffPerformance.vue'), meta: { title: '客服效能' } },
      { path: 'ai-report', name: 'ai-report', component: () => import('@/views/AIReport.vue'), meta: { title: 'AI群日报' } },
      { path: 'churn', name: 'churn', component: () => import('@/views/ChurnHealth.vue'), meta: { title: '客户健康度' } },
      { path: 'risk', name: 'risk', component: () => import('@/views/RiskRadar.vue'), meta: { title: '投诉雷达' } },
      { path: 'groups', name: 'groups', component: () => import('@/views/GroupList.vue'), meta: { title: '群档案' } },
      { path: 'groups/:chatId', name: 'group-detail', component: () => import('@/views/GroupDetail.vue'), meta: { title: '群详情' } },
      { path: 'alerts', name: 'alerts', component: () => import('@/views/Alerts.vue'), meta: { title: '预警管理' } },
      { path: 'admin', name: 'admin', component: () => import('@/views/Admin.vue'), meta: { title: 'API配置后台' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局登录守卫
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
