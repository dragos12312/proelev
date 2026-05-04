// all the routes in the app live here
// homework form is reused for add and edit, the difference is whether the url has an id
import { createRouter, createWebHistory } from 'vue-router'
import LandingView from '../views/LandingView.vue'
import HomeworksView from '../views/HomeworksView.vue'
import HomeworkDetailView from '../views/HomeworkDetailView.vue'
import HomeworkFormView from '../views/HomeworkFormView.vue'
import ResetPasswordView from '../views/ResetPasswordView.vue'
import LoginView from '../views/LoginView.vue'
import MainView from '../views/MainView.vue'
import StatisticsView from '../views/StatisticsView.vue'
import HomeworkStatistics from '../views/HomeworkStatistics.vue'
import AdminPanelView from '../views/AdminPanelView.vue'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'landing',
            component: LandingView
        },
        {
            path: '/homeworks',
            name: 'homeworks',
            component: HomeworksView
        },
        {
            path: '/homeworks/add',
            name: 'homework-add',
            component: HomeworkFormView
        },
        {
            path: '/homeworks/:id',
            name: 'homework-detail',
            component: HomeworkDetailView
        },
        {
            path: '/homeworks/:id/edit',
            name: 'homework-edit',
            component: HomeworkFormView
        },
        {
            path: '/login',
            name: 'login',
            component: LoginView
        },
        {
            path: '/reset-password',
            name: 'reset-password',
            component: ResetPasswordView
        },
        {
            path: '/main',
            name: 'main',
            component: MainView
        },
        {
            path: '/homeworks/:id/statistics',
            name: 'homework-statistics',
            component: StatisticsView
        },
        {
            path: '/homeworks/:id/hwstatistics',
            name: 'HomeworkStatistics',
            component: HomeworkStatistics,
        },
        {
            path: '/admin',
            name: 'admin',
            component: AdminPanelView,
        },
    ]
})

export default router