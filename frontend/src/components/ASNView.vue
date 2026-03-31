<template>
  <div class="asn-view">
    <h2>ASN 拓扑（交互）</h2>
    <div style="margin-bottom:8px">
      <button @click="loadGraph">刷新拓扑</button>
    </div>
    <div v-if="error" class="error">{{error}}</div>
    <div style="display:flex; gap:12px">
      <svg ref="svgRef" :width="680" :height="500" style="border:1px solid #ddd; background:#fff"></svg>
      <div style="width:240px">
        <div v-if="selected" style="padding:8px; border:1px solid #eee; border-radius:6px; background:#fafafa">
          <h3>AS{{selected.asn}}</h3>
          <div><strong>名称：</strong>{{selected.name || '—'}}</div>
          <div><strong>国家：</strong>{{selected.country || '—'}}</div>
          <div style="margin-top:8px"><strong>邻居：</strong></div>
          <ul>
            <li v-for="n in neighbors" :key="n.asn">AS{{n.asn}} ({{n.relation}})</li>
          </ul>
          <div style="margin-top:8px">
            <button @click="clearSelection">清除高亮</button>
          </div>
          <div style="margin-top:12px; border-top:1px dashed #eee; padding-top:8px">
            <h4>黑洞操作</h4>
            <div style="display:flex; gap:6px; align-items:center">
              <input v-model="community" placeholder="Community (可选)" style="flex:1; padding:6px" />
              <button @click="doBlackhole('add')">下发黑洞</button>
              <button @click="doBlackhole('remove')">撤销黑洞</button>
            </div>
            <div style="margin-top:8px">
              <button @click="loadBlackholeLogs">刷新审计日志</button>
            </div>
            <div style="margin-top:8px; max-height:180px; overflow:auto; background:#fff; padding:6px; border-radius:4px">
              <div v-for="log in bhLogs" :key="log.id" style="font-size:12px; margin-bottom:6px; display:flex; justify-content:space-between">
                <div>
                  <strong>#{{log.id}}</strong> {{log.performed_at}} — {{log.prefix}} ({{log.action}}) — {{log.result ? 'OK' : 'FAIL'}}
                  <div style="color:#666">{{log.detail}}</div>
                </div>
                <div style="display:flex; flex-direction:column; gap:4px">
                  <button @click="revertLog(log.id)">回滚</button>
                </div>
              </div>
            </div>
          </div>
            <div style="margin-top:12px">
              <h4>Telemetry 活动（最近）</h4>
              <div ref="chartRef" style="width:100%; height:120px"></div>
              <div style="margin-top:6px; max-height:140px; overflow:auto; background:#fff; padding:6px; border-radius:4px">
                <div v-for="s in samples" :key="s.id" style="font-size:12px;margin-bottom:6px">
                  <strong>{{s.ts || s.received_at}}</strong> — {{s.payload && (s.payload.msg || s.payload.event || JSON.stringify(s.payload))}}
                </div>
              </div>
            </div>
        </div>
        <div v-else style="padding:8px;color:#666">点击节点查看详情</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as d3 from 'd3'

const svgRef = ref(null)
const error = ref('')
const selected = ref(null)
const neighbors = ref([])
let currentNodes = []
let currentLinks = []
const samples = ref([])
const chartRef = ref(null)
const community = ref('')
const bhLogs = ref([])

async function loadGraph(){
  error.value = ''
  try{
    const r = await fetch('/api/v1/asn/graph')
    const j = await r.json()
    if(!r.ok){ error.value = j.detail || JSON.stringify(j); return }
    currentNodes = j.nodes || []
    currentLinks = j.links || []
    renderGraph(currentNodes, currentLinks)
  }catch(e){ error.value = String(e) }
}

async function doBlackhole(action){
  if(!selected.value) return
  const adminKey = sessionStorage.getItem('open_dcms_admin_key') || ''
  try{
    const body = { prefix: selected.value.asn ? `${selected.value.asn}` : selected.value.asn }
    // prefix expects CIDR; UI shows ASN — use prefix from selection if available
    // if selected has 'prefix' field, prefer it; otherwise show prompt
    const p = selected.value.prefix || selected.value.asn
    body.prefix = p
    body.action = action
    body.adapter = 'exabgp'
    if(community.value) body.community = community.value
    const r = await fetch('/api/v1/blackhole', { method:'POST', headers: {'Content-Type':'application/json', 'X-Admin-Key': adminKey}, body: JSON.stringify(body) })
    const j = await r.json()
    if(!r.ok){ alert('操作失败: '+JSON.stringify(j)); return }
    alert('操作成功: '+JSON.stringify(j))
    loadBlackholeLogs()
  }catch(e){ alert('请求失败: '+String(e)) }
}

async function loadBlackholeLogs(){
  const adminKey = sessionStorage.getItem('open_dcms_admin_key') || ''
  try{
    const r = await fetch('/api/v1/blackhole/logs?limit=50', { headers: {'X-Admin-Key': adminKey} })
    const j = await r.json()
    if(!r.ok){ console.error(j); return }
    bhLogs.value = j.logs || []
  }catch(e){ console.error(e) }
}

async function revertLog(id){
  const adminKey = sessionStorage.getItem('open_dcms_admin_key') || ''
  try{
    const r = await fetch('/api/v1/blackhole/revert', { method:'POST', headers:{'Content-Type':'application/json','X-Admin-Key': adminKey}, body: JSON.stringify({id}) })
    const j = await r.json()
    if(!r.ok){ alert('回滚失败: '+JSON.stringify(j)); return }
    alert('回滚结果: '+JSON.stringify(j))
    loadBlackholeLogs()
  }catch(e){ alert('请求失败: '+String(e)) }
}

function clearSelection(){
  selected.value = null
  neighbors.value = []
  const svg = d3.select(svgRef.value)
  svg.selectAll('circle').attr('r', 10).attr('fill', '#1f77b4')
  svg.selectAll('line').attr('stroke', '#999').attr('stroke-width', 1.5)
}

function computePath(start, goal){
  // BFS on adjacency
  const adj = {}
  for(const n of currentNodes) adj[n.asn] = []
  for(const l of currentLinks){
    adj[l.from] = adj[l.from] || []
    adj[l.to] = adj[l.to] || []
    adj[l.from].push(l.to)
    adj[l.to].push(l.from)
  }
  const q = [start]
  const prev = {}
  const seen = new Set([start])
  while(q.length){
    const u = q.shift()
    if(u === goal) break
    for(const v of (adj[u]||[])){
      if(!seen.has(v)){
        seen.add(v); prev[v]=u; q.push(v)
      }
    }
  }
  if(!prev[goal] && start !== goal) return null
  const path = [goal]
  let cur = goal
  while(cur !== start){ cur = prev[cur]; path.unshift(cur) }
  return path
}

function highlightPath(path){
  const svg = d3.select(svgRef.value)
  svg.selectAll('circle').attr('r', d => path.includes(d.asn) ? 14 : 10).attr('fill', d => path.includes(d.asn) ? '#d62728' : '#1f77b4')
  svg.selectAll('line').attr('stroke', l => {
    // link object has from,to
    const key = (l.from + '-' + l.to)
    // check if this link is between consecutive nodes in path
    for(let i=0;i<path.length-1;i++){
      const a = path[i], b = path[i+1]
      if((l.from===a && l.to===b) || (l.from===b && l.to===a)) return '#d62728'
    }
    return '#999'
  }).attr('stroke-width', l => {
    for(let i=0;i<path.length-1;i++){
      const a = path[i], b = path[i+1]
      if((l.from===a && l.to===b) || (l.from===b && l.to===a)) return 3
    }
    return 1.5
  })
}

function handleNodeClick(d, event){
  // if Shift key pressed and there is already a selected AS, compute path
  if(event.shiftKey && selected.value){
    const path = computePath(selected.value.asn, d.asn)
    if(path){ highlightPath(path) }
    return
  }
  // normal click: select node and highlight neighbors
  selected.value = d
  // compute neighbor list from currentLinks
  const neigh = []
  for(const l of currentLinks){
    if(l.from === d.asn) neigh.push({asn: l.to, relation: l.relation})
    if(l.to === d.asn) neigh.push({asn: l.from, relation: l.relation})
  }
  neighbors.value = neigh
  const svg = d3.select(svgRef.value)
  svg.selectAll('circle').attr('r', n => n.asn===d.asn ? 16 : 10).attr('fill', n => n.asn===d.asn ? '#2ca02c' : '#1f77b4')
  svg.selectAll('line').attr('stroke', l => (l.from===d.asn || l.to===d.asn) ? '#ff7f0e' : '#999').attr('stroke-width', l => (l.from===d.asn || l.to===d.asn) ? 2.5 : 1.5)
  // fetch telemetry time series for this ASN
  fetchTelemetryForAsn(d.asn)
}

function renderGraph(nodes, links){
  const svg = d3.select(svgRef.value)
  svg.selectAll('*').remove()
  const width = +svg.attr('width')
  const height = +svg.attr('height')

  // convert links to d3 format with from/to
  const d3links = links.map(l => ({from: l.from, to: l.to, relation: l.relation}))
  const nodeMap = new Map(nodes.map(n => [n.asn, n]))
  const d3nodes = nodes.map(n => ({asn: n.asn, name: n.name, country: n.country}))

  const sim = d3.forceSimulation(d3nodes)
    .force('link', d3.forceLink(d3links).id(d => d.asn).distance(80).strength(0.8))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width/2, height/2))

  const link = svg.append('g')
    .attr('stroke', '#999')
    .selectAll('line')
    .data(d3links)
    .enter().append('line')
    .attr('stroke-width', 1.5)

  const node = svg.append('g')
    .attr('stroke', '#fff')
    .attr('stroke-width', 1.5)
    .selectAll('circle')
    .data(d3nodes)
    .enter().append('circle')
    .attr('r', 10)
    .attr('fill', '#1f77b4')
    .on('click', function(event, d){ handleNodeClick(d, event) })
    .call(d3.drag()
      .on('start', (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
      .on('end', (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null }))

  const labels = svg.append('g')
    .selectAll('text')
    .data(d3nodes)
    .enter().append('text')
    .text(d => 'AS' + d.asn)
    .attr('font-size', 10)
    .attr('dx', 12)
    .attr('dy', 4)

  sim.on('tick', () => {
    link
      .attr('x1', d => (nodeMap.get(d.from).x = (d.source.x)))
      .attr('y1', d => (nodeMap.get(d.from).y = (d.source.y)))
      .attr('x2', d => (nodeMap.get(d.to).x = (d.target.x)))
      .attr('y2', d => (nodeMap.get(d.to).y = (d.target.y)))

    node
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)

    labels
      .attr('x', d => d.x)
      .attr('y', d => d.y)
  })
}

onMounted(() => loadGraph())

async function fetchTelemetryForAsn(asn){
  samples.value = []
  try{
    const r = await fetch(`/api/v1/asn/telemetry?asn=${asn}&minutes=60`)
    const j = await r.json()
    if(!r.ok){ return }
    const series = j.series || {times:[], counts:[]}
    samples.value = j.samples || []
    await nextTick()
    renderChart(series.times || [], series.counts || [])
  }catch(e){ }
}

function renderChart(times, counts){
  const el = chartRef.value
  if(!el) return
  d3.select(el).selectAll('*').remove()
  const w = el.clientWidth || 200
  const h = 100
  const svg = d3.select(el).append('svg').attr('width', w).attr('height', h)
  const x = d3.scaleLinear().domain([0, counts.length-1]).range([4, w-4])
  const y = d3.scaleLinear().domain([0, d3.max(counts.concat([1]))]).range([h-4, 4])
  const line = d3.line().x((d,i)=>x(i)).y(d=>y(d)).curve(d3.curveMonotoneX)
  svg.append('path').datum(counts).attr('d', line).attr('fill','none').attr('stroke','#2ca02c').attr('stroke-width',2)
}
</script>

<style scoped>
.error { color: red }
</style>
