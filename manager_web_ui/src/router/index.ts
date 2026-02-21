import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/:port(\\d+)',
      name: 'session',
      component: () => import('@/views/SessionView.vue'),
      props: true,
    },
  ],
})

export default router
