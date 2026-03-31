<template>
  <div class="query">
    <h2>Telemetry 查询</h2>
    <div class="controls">
      <input v-model="tenant" placeholder="tenant (default)" />
      <input v-model="source" placeholder="source (optional)" />
      <input v-model="payloadKey" placeholder="payload_key (optional)" />
      <input v-model="since" placeholder="since (ISO8601)" />
      <input v-model="until" placeholder="until (ISO8601)" />
      <input v-model.number="limit" type="number" min="1" max="500" />
      <button @click="runQuery" :disabled="loading">查询</button>
    </div>
    <div style="margin-bottom:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap">
      <div>
        <label style="margin-right:6px">导出列:</label>
        <label><input type="checkbox" v-model="cols.id" /> id</label>
        <label style="margin-left:6px"><input type="checkbox" v-model="cols.source" /> source</label>
        <label style="margin-left:6px"><input type="checkbox" v-model="cols.timestamp" /> timestamp</label>
        <label style="margin-left:6px"><input type="checkbox" v-model="cols.payload" /> payload</label>
      </div>
      <div>
        <label><input type="checkbox" v-model="exportAll" /> 导出全部（遍历翻页）</label>
      </div>
    </div>

    <div v-if="loading">加载中…</div>
    <div v-if="error" class="error">{{error}}</div>

    <div v-if="items && items.length" class="results">
      <h3>结果（{{total}}）</h3>
      <ul>
        <li v-for="it in items" :key="it.id">
          <strong>{{it.id}}</strong> [{{it.source}}] {{it.timestamp}} — {{it.payload}}
        </li>
      </ul>
      <div style="margin-top:8px; display:flex; gap:8px; align-items:center">
        <div>
          <button v-if="nextCursor" @click="loadMore" :disabled="loading">加载更多</button>
        </div>
        <div>
          <button @click="exportCSV" :disabled="!items.length">导出 CSV</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const tenant = ref('')
const source = ref('')
const payloadKey = ref('')
const since = ref('')
const until = ref('')
const limit = ref(20)
const items = ref([])
const total = ref(0)
const nextCursor = ref(null)
const loading = ref(false)
const error = ref('')
const cols = ref({ id: true, source: true, timestamp: true, payload: true })
const exportAll = ref(false)

function itemsToCsv(rows, selectedCols){
  const available = ['id','source','timestamp','payload']
  const chosen = available.filter(c => selectedCols[c])
  const esc = v => '"' + String(v === undefined || v === null ? '' : v).replace(/"/g,'""') + '"'
  const lines = [chosen.join(',')]
  for(const r of rows){
    const map = {
      id: r.id,
      source: r.source,
      timestamp: r.timestamp || r.received_at || r.ts || '',
      payload: typeof r.payload === 'string' ? r.payload : JSON.stringify(r.payload)
    }
    lines.push(chosen.map(k => esc(map[k])).join(','))
  }
  return lines.join('\n')
}

function download(filename, text){
  const b = new Blob([text], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(b)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function exportCSV(){
  if(exportAll.value){
    exportAllPages()
    return
  }
  if(!items.value || !items.value.length) return
  const csv = itemsToCsv(items.value, cols.value)
  const name = `query-${tenant.value || 'all'}-${new Date().toISOString()}.csv`
  download(name, csv)
}

async function exportAllPages(){
  loading.value = true; error.value = ''
  const collected = []
  try{
    let cursor = null
    while(true){
      const qs = buildQueryParams(cursor)
      // force a reasonable page size to accelerate export
      const url = '/api/v1/query?' + qs + (qs.includes('limit=') ? '' : '&limit=500')
      const r = await fetch(url)
      const j = await r.json()
      if(!r.ok){ throw new Error(j.detail || JSON.stringify(j)) }
      const page = j.items || []
      collected.push(...page)
      cursor = j.next_cursor || null
      if(!cursor) break
    }
    if(!collected.length){ error.value = '没有可导出的数据'; loading.value=false; return }
    const csv = itemsToCsv(collected, cols.value)
    const name = `query-all-${tenant.value || 'all'}-${new Date().toISOString()}.csv`
    download(name, csv)
  }catch(e){ error.value = String(e) }
  loading.value = false
}

function buildQueryParams(cursor=null){
  const params = new URLSearchParams()
  if(tenant.value) params.set('tenant', tenant.value)
  if(source.value) params.set('source', source.value)
  if(payloadKey.value) params.set('payload_key', payloadKey.value)
  if(since.value) params.set('since', since.value)
  if(until.value) params.set('until', until.value)
  if(limit.value) params.set('limit', String(limit.value))
  if(cursor) params.set('cursor', cursor)
  return params.toString()
}

async function runQuery(){
  loading.value = true; error.value = ''
  items.value = []; total.value = 0; nextCursor.value = null
  try{
    const qs = buildQueryParams()
    const r = await fetch('/api/v1/query?' + qs)
    const j = await r.json()
    if(!r.ok){ error.value = j.detail || JSON.stringify(j); loading.value=false; return }
    items.value = j.items || []
    total.value = j.total || 0
    nextCursor.value = j.next_cursor || null
  }catch(e){ error.value = String(e) }
  loading.value = false
}

async function loadMore(){
  if(!nextCursor.value) return
  loading.value = true; error.value = ''
  try{
    const qs = buildQueryParams(nextCursor.value)
    const r = await fetch('/api/v1/query?' + qs)
    const j = await r.json()
    if(!r.ok){ error.value = j.detail || JSON.stringify(j); loading.value=false; return }
    items.value = items.value.concat(j.items || [])
    nextCursor.value = j.next_cursor || null
  }catch(e){ error.value = String(e) }
  loading.value = false
}
</script>

<style scoped>
.controls { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px }
input { padding:6px }
.error { color:red }
.results ul { list-style:none; padding:0 }
</style>
