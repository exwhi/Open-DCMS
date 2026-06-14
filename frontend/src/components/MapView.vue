<template>
  <div class="map-container">
    <div id="map" style="height:600px"></div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'

async function fetchLocations(){
  try{
    const r = await fetch('/api/v1/asn/locations')
    if(!r.ok) return []
    const j = await r.json()
    return j.items || []
  }catch(e){
    return []
  }
}

onMounted(async ()=>{
  const map = L.map('map', { worldCopyJump: true }).setView([20,0], 2)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map)

  const items = await fetchLocations()
  const markers = L.markerClusterGroup()
  const maxWeight = Math.max(0, ...items.map(i => Number(i.weight || 0)))
  for(const it of items){
    const lat = Number(it.lat)
    const lon = Number(it.lon)
    const label = `AS${it.asn} ${it.name || ''} (${it.country || ''})` + (it.weight ? ` — weight:${it.weight}` : '')
    if(lat && lon){
      // color by weight
      const w = Number(it.weight || 0)
      let color = '#3388ff'
      if(maxWeight > 0){
        const t = Math.min(1, w / maxWeight)
        // interpolate blue -> red
        const r = Math.round(255 * t)
        const g = Math.round(80 * (1 - t))
        const b = Math.round(200 * (1 - t))
        color = `rgb(${r},${g},${b})`
      }
      const icon = L.divIcon({
        html: `<div style="background:${color};width:12px;height:12px;border-radius:6px;border:2px solid white"></div>`,
        className: 'asn-marker',
        iconSize: [16,16]
      })
      const m = L.marker([lat, lon], { icon })
      m.bindPopup(label)
      markers.addLayer(m)
    }
  }
  map.addLayer(markers)
})
</script>

<style scoped>
.map-container { width:100% }
#map { width:100%; height:600px }
</style>
