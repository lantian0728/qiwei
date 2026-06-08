import { ElLoading } from 'element-plus'

// 轮播的可爱进度文案，让等待不无聊
const CUTE_TIPS = [
  '🤖 AI 开足马力分析中…',
  '📊 正在翻群聊记录…',
  '✨ 整理重点，马上好…',
  '🚀 再等一下下…',
  '🍵 喝口茶的功夫就好…',
]

/**
 * 启动一个全屏任务进度遮罩，文案会轮播。
 * 用法：const t = startTask('智谱正在识别'); try { ... } finally { t.close() }
 */
export function startTask(title = '处理中') {
  const inst = ElLoading.service({
    lock: true,
    text: `${title}…`,
    background: 'rgba(255, 255, 255, 0.88)',
  })
  let i = 0
  const timer = window.setInterval(() => {
    inst.setText(`${title}  ${CUTE_TIPS[i % CUTE_TIPS.length]}`)
    i += 1
  }, 1500)
  return {
    close() {
      window.clearInterval(timer)
      inst.close()
    },
  }
}
