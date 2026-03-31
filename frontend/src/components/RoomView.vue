<template>
  <div class="room">
    <h2>机柜视图 — Cabinet 1</h2>

    <div class="controls">
      <label>后端地址：
        <input v-model="server" placeholder="http://localhost:8001" />
      </label>
      <label style="margin-left:12px">租户：
        <input v-model="tenant" placeholder="demo" />
      </label>
      <button @click="fetchLatest" style="margin-left:12px">拉取最新状态</button>
    </div>

    <div class="cabinet">
      <div v-for="u in slots" :key="u.number" class="u-slot" :class="u.status">
        <div class="u-label">U{{u.number}}</div>
      </div>
    </div>

    <div class="legend">
      <span class="box occupied"></span> 已占用
      <span class="box free" style="margin-left:12px"></span> 空闲
    </div>

    <div v-if="lastPayload" class="payload">
      <h3>最近采集数据（预览）</h3>
      <pre>{{ lastPayload }}</pre>
    </div>

    <div v-if="previewItems && previewItems.length" class="preview" style="margin-top:12px">
      <h3>Telemetry 预览（最近）</h3>
      <ul>
        <li v-for="p in previewItems" :key="p.id">
          <strong>{{p.id}}</strong> [{{p.source}}] {{p.timestamp || p.received_at || p.ts}} — {{p.payload}}
        </li>
      </ul>
      <div style="margin-top:8px">
        <button @click="exportPreviewCsv">导出 预览 CSV</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const server = ref('http://localhost:8001')
const tenant = ref('demo')
const slots = ref([])
const lastPayload = ref(null)
const previewItems = ref([])
const previewNextCursor = ref(null)

function makeEmptySlots(){
  const arr = []
  for (let i = 42; i >= 1; i--) arr.push({ number: i, status: 'free' })
  return arr
}

function applyPayloadToSlots(payload){
  // Expect payload to contain mapping like { rack_units: [{u: 1, status: 'occupied'}, ...] }
  const s = makeEmptySlots()
  if (payload && payload.rack_units && Array.isArray(payload.rack_units)){
    for (const r of payload.rack_units){
      const idx = s.findIndex(x => x.number === r.u)
      if (idx !== -1){
        s[idx].status = r.status === 'occupied' ? 'occupied' : 'free'
      }
    }
  } else if (payload && payload.payload && payload.payload.env){
    // fallback: just mark some random slots based on hash of timestamp
    const t = payload.timestamp || Date.now()
    for (let i=0;i<8;i++){
      const n = (Math.abs(Math.floor(t/1000)) + i*7) % 42
      s[n].status = 'occupied'
    }
  } else {
    // default random demo
    for (let i = 0; i < 10; i++){
      const idx = Math.floor(Math.random()*42)
      s[idx].status = 'occupied'
    }
  }
  slots.value = s
}

async function fetchLatest(){
  try{
    const url = `${server.value.replace(/\/$/, '')}/api/v1/latest?tenant=${encodeURIComponent(tenant.value)}`
    const r = await axios.get(url, { timeout: 5000 })
    lastPayload.value = r.data
    applyPayloadToSlots(r.data)
    // fetch a small telemetry preview
    fetchPreview()
  }catch(e){
    // fallback: try /api/v1/ingest latest by calling /api/v1/latest isn't available
    lastPayload.value = { error: '无法从后端拉取最新数据，使用演示数据' }
    applyPayloadToSlots(null)
  }
}

async function fetchPreview(){
  try{
    const q = `${server.value.replace(/\/$/, '')}/api/v1/query?tenant=${encodeURIComponent(tenant.value)}&limit=5`
    const r = await axios.get(q, { timeout: 5000 })
    if(r && r.data && Array.isArray(r.data.items)){
      previewItems.value = r.data.items
      previewNextCursor.value = r.data.next_cursor || null
    } else {
      previewItems.value = []
      previewNextCursor.value = null
    }
  }catch(e){ previewItems.value = []; previewNextCursor.value = null }
}

function itemsToCsv(rows){
  const cols = ['id','source','timestamp','payload']
  const esc = v => '"' + String(v === undefined || v === null ? '' : v).replace(/"/g,'""') + '"'
  const lines = [cols.join(',')]
  for(const r of rows){
    const payload = typeof r.payload === 'string' ? r.payload : JSON.stringify(r.payload)
    lines.push([r.id, r.source, r.timestamp || r.received_at || r.ts, payload].map(esc).join(','))
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

function exportPreviewCsv(){
  if(!previewItems.value || !previewItems.value.length) return
  const csv = itemsToCsv(previewItems.value)
  const name = `preview-${tenant.value || 'all'}-${new Date().toISOString()}.csv`
  download(name, csv)
}

// init demo
applyPayloadToSlots(null)
</script>

<style scoped>
.controls { margin-bottom:12px }
.controls input { padding:6px; width:240px }
.cabinet { display: grid; grid-template-columns: 1fr; gap: 4px; background:#222; padding:8px; border-radius:6px }
.u-slot { height:20px; display:flex; align-items:center; padding:0 8px; color:#fff; border-radius:3px }
.u-slot .u-label { font-size:12px }
.u-slot.occupied { background: linear-gradient(90deg,#b02a37,#7a0f15) }
.u-slot.free { background: linear-gradient(90deg,#2a8b4a,#0f6a3a) }
.legend { margin-top:8px; font-size:14px }
.box { display:inline-block; width:14px; height:14px; vertical-align:middle; margin-right:6px; border-radius:3px }
.box.occupied { background:#b02a37 }
.box.free { background:#2a8b4a }
.payload { margin-top:12px; background:#fff; padding:8px; border-radius:6px }
pre { white-space:pre-wrap }
</style>
