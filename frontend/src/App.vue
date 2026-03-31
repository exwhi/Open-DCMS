<template>
  <div class="container">
    <h1>Open-DCMS — DCIM 最小视图</h1>
    <div style="margin-bottom:12px">
      <button @click="showAdmin = !showAdmin">切换 Admin 密钥管理</button>
      <button @click="showQuery = !showQuery" style="margin-left:8px">切换 Query 界面</button>
      <button @click="showASN = !showASN" style="margin-left:8px">切换 ASN 拓扑</button>
      <button @click="showBH = !showBH" style="margin-left:8px">黑洞审计</button>
    </div>
    <div>
      <AdminKeys v-if="showAdmin" />
      <QueryView v-else-if="showQuery" />
      <BlackholeLogs v-else-if="showBH" />
      <ASNView v-else-if="showASN" />
      <RoomView v-else />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import RoomView from './components/RoomView.vue'
import AdminKeys from './components/AdminKeys.vue'
import QueryView from './components/QueryView.vue'
import ASNView from './components/ASNView.vue'
import BlackholeLogs from './components/BlackholeLogs.vue'

const showAdmin = ref(false)
const showQuery = ref(false)
const showASN = ref(false)
const showBH = ref(false)
</script>

<style>
.container { max-width:900px; margin:20px auto; font-family: Arial, Helvetica, sans-serif }
h1 { margin-bottom: 12px }
</style>
