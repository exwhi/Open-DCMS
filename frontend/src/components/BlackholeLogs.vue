<template>
  <div class="blackhole-logs">
    <h2>黑洞审计日志</h2>
    <div style="margin-bottom:8px">
      <label>Admin Key: <input v-model="adminKey" type="password"/></label>
      <button @click="refresh" style="margin-left:8px">刷新</button>
    </div>
    <div style="margin-bottom:8px">
      <label>Prefix: <input v-model="filterPrefix" placeholder="可选：203.0.113.0/24"/></label>
      <button @click="refresh" style="margin-left:8px">筛选</button>
    </div>
    <div v-if="error" style="color:red">{{error}}</div>
    <div v-if="logs.length===0" style="color:#666">暂无日志</div>
    <div v-for="log in logs" :key="log.id" style="border:1px solid #eee; padding:8px; margin-bottom:8px; border-radius:6px; background:#fff">
      <div style="display:flex; justify-content:space-between">
        <div>
          <strong>#{{log.id}}</strong>
          <span style="margin-left:8px">{{log.performed_at}}</span>
          <div style="margin-top:6px">前缀：{{log.prefix}} — 操作：{{log.action}} — 结果：{{log.result ? '成功' : '失败'}}</div>
          <div style="color:#666; margin-top:6px">详情：{{log.detail}}</div>
        </div>
        <div style="display:flex; flex-direction:column; gap:6px; align-items:flex-end">
          <button @click="revert(log.id)">回滚</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const adminKey = ref('')
const filterPrefix = ref('')
const logs = ref([])
const error = ref('')

async function refresh(){
  error.value = ''
  try{
    const qs = filterPrefix.value ? `?limit=200&prefix=${encodeURIComponent(filterPrefix.value)}` : '?limit=200'
    const r = await fetch(`/api/v1/blackhole/logs${qs}`, { headers: {'X-Admin-Key': adminKey.value} })
    const j = await r.json()
    if(!r.ok){ error.value = j.error || JSON.stringify(j); return }
    logs.value = j.logs || []
  }catch(e){ error.value = String(e) }
}

async function revert(id){
  try{
    const r = await fetch('/api/v1/blackhole/revert', { method:'POST', headers:{'Content-Type':'application/json','X-Admin-Key': adminKey.value}, body: JSON.stringify({id}) })
    const j = await r.json()
    if(!r.ok){ alert('回滚失败: '+JSON.stringify(j)); return }
    alert('回滚成功: '+JSON.stringify(j))
    refresh()
  }catch(e){ alert('请求失败: '+String(e)) }
}

refresh()
</script>

<style scoped>
.blackhole-logs { max-width:900px; margin:12px auto }
input { padding:6px }
button { padding:6px 10px }
</style>
