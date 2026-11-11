import { ElMessage } from 'element-plus'

export function showSaveSuccess(): void {
  ElMessage.success({ message: '保存成功', duration: 1000 })
}
