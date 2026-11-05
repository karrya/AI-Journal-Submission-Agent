import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElAlert,
  ElButton,
  ElContainer,
  ElForm,
  ElFormItem,
  ElHeader,
  ElInput,
  ElMain,
} from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
for (const component of [ElAlert, ElButton, ElContainer, ElForm, ElFormItem, ElHeader, ElInput, ElMain]) {
  app.use(component)
}
app.mount('#app')
