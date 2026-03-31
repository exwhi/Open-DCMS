<template>
  <div class="admin">
    <h2>Admin 密钥管理</h2>
    <div>
      <label>Admin Key: <input v-model="adminKey" type="password"/></label>
      <button @click="listKeys" :disabled="loading" style="margin-left:8px">刷新列表</button>
    </div>

    <div style="margin-top:8px;">
      <input v-model="tenant" placeholder="tenant name"/>
      <button @click="createKey" :disabled="loading || !tenant">创建租户密钥</button>
    </div>

    <div v-if="createdKey" class="created" style="margin-top:12px;">
      <strong>已创建：</strong> <span>{{createdKey.tenant}}</span>
      <code style="margin-left:8px">{{createdKey.key}}</code>
      <button @click="copyKey(createdKey.key)" style="margin-left:8px">复制</button>
    </div>

    <div v-if="keys && keys.length" style="margin-top:12px;">
      <h3>密钥列表</h3>
      <ul>
        <li v-for="k in keys" :key="k.tenant" style="margin-bottom:6px">
          <strong>{{k.tenant}}:</strong>
          <code style="margin-left:8px">{{k.key}}</code>
          <button @click="copyKey(k.key)" style="margin-left:8px">复制</button>
        </li>
      </ul>
    </div>

    <div v-if="error" style="color:red; margin-top:8px">{{error}}</div>
    <div v-if="message" style="color:green; margin-top:8px">{{message}}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const adminKey = ref('')
const tenant = ref('')
const keys = ref([])
const error = ref('')
const message = ref('')
const loading = ref(false)
const createdKey = ref(null)
const passphrase = ref('')

function bufToBase64(b){
  return btoa(String.fromCharCode(...new Uint8Array(b)))
}
function base64ToBuf(s){
  const bin = atob(s)
  const arr = new Uint8Array(bin.length)
  for(let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i)
  return arr.buffer
}

async function deriveKey(pass, salt){
  const enc = new TextEncoder()
  const baseKey = await crypto.subtle.importKey('raw', enc.encode(pass), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey({name:'PBKDF2', salt, iterations:100000, hash:'SHA-256'}, baseKey, {name:'AES-GCM', length:256}, false, ['encrypt','decrypt'])
}

async function encryptText(plain, pass){
  const enc = new TextEncoder()
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(pass, salt.buffer)
  const ct = await crypto.subtle.encrypt({name:'AES-GCM', iv}, key, enc.encode(plain))
  return {ct: bufToBase64(ct), salt: bufToBase64(salt), iv: bufToBase64(iv)}
}

async function decryptText(ct_b64, pass, salt_b64, iv_b64){
  const dec = new TextDecoder()
  const salt = base64ToBuf(salt_b64)
  const iv = base64ToBuf(iv_b64)
  const key = await deriveKey(pass, salt)
  const pt = await crypto.subtle.decrypt({name:'AES-GCM', iv}, key, base64ToBuf(ct_b64))
  return dec.decode(pt)
}

function saveAdminKey(){
  // store in sessionStorage; if passphrase provided, encrypt
  if(passphrase.value){
    encryptText(adminKey.value, passphrase.value).then(({ct,salt,iv})=>{
      sessionStorage.setItem('open_dcms_admin_key_enc', JSON.stringify({ct,salt,iv}))
      sessionStorage.removeItem('open_dcms_admin_key')
    }).catch(e=>{ error.value = '加密失败: '+String(e) })
  }else{
    sessionStorage.setItem('open_dcms_admin_key', adminKey.value)
    sessionStorage.removeItem('open_dcms_admin_key_enc')
  }
}

async function tryLoadAdminKey(){
  error.value = ''
  // try plaintext
  const p = sessionStorage.getItem('open_dcms_admin_key')
  if(p){ adminKey.value = p; return }
  const enc = sessionStorage.getItem('open_dcms_admin_key_enc')
  if(enc){
    // need passphrase to decrypt
    if(passphrase.value){
      try{
        const obj = JSON.parse(enc)
        const pt = await decryptText(obj.ct, passphrase.value, obj.salt, obj.iv)
        adminKey.value = pt
      }catch(e){ error.value = '解密失败: ' + String(e) }
    }
  }
}

async function createKey(){
  error.value = ''
  message.value = ''
  createdKey.value = null
  if(!adminKey.value){ error.value='需要 Admin Key'; return }
  if(!tenant.value){ error.value='需要 tenant 名称'; return }
  saveAdminKey()
  loading.value = true
  try{
    const r = await fetch('/api/v1/admin/key', {
      method:'POST',
      headers: {'Content-Type':'application/json', 'X-Admin-Key': adminKey.value},
      body: JSON.stringify({tenant: tenant.value})
    })
    const j = await r.json()
    if(!r.ok){ error.value = j.error || JSON.stringify(j); return }
    createdKey.value = j
    message.value = `已创建租户密钥（可复制）`
    listKeys()
  }catch(e){
    error.value = String(e)
  }finally{ loading.value = false }
}

async function listKeys(){
  error.value = ''
  message.value = ''
  saveAdminKey()
  loading.value = true
  try{
    const r = await fetch('/api/v1/admin/keys', {
      headers:{ 'X-Admin-Key': adminKey.value}
    })
    const j = await r.json()
    if(!r.ok){ error.value = j.error || JSON.stringify(j); return }
    keys.value = j.keys || []
  }catch(e){
    error.value = String(e)
  }finally{ loading.value = false }
}

async function copyKey(text){
  try{
    if(navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(text)
    }else{
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    message.value = '已复制到剪贴板'
    setTimeout(()=>{ message.value = '' }, 2500)
  }catch(e){
    error.value = '复制失败: ' + String(e)
  }
}
</script>

<style scoped>
.admin { max-width:700px; margin:12px auto; }
input { margin-right:8px; padding:4px; }
button { padding:6px 10px; }
code { background:#f3f3f3; padding:4px 6px; border-radius:4px }
.created { background:#f9fff0; padding:8px; border:1px solid #e0f0c0; border-radius:6px }
</style>

