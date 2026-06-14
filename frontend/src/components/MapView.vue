<template>
  <div class="map-container">
    <div id="map" style="height:600px"></div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

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
  for(const it of items){
    const lat = Number(it.lat)
    const lon = Number(it.lon)
    const label = `AS${it.asn} ${it.name || ''} (${it.country || ''})`
    if(lat && lon){
      const m = L.marker([lat, lon]).addTo(map)
      m.bindPopup(label)
    }
  }
})
</script>

<style scoped>
.map-container { width:100% }
#map { width:100%; height:600px }
</style>
