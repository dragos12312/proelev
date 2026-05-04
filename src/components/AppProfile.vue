<script setup>
// little profile avatar that floats in the top right corner
// it sticks just under the header so we watch the header size and move with it
import template from '../assets/template.png'
import { ref, onMounted, onUnmounted } from 'vue'

const top = ref(0)
let observer = null

onMounted(() => {
  const header = document.querySelector('.header')
  if (!header) return

  // recalcs where the avatar should sit under the header
  const update = () => {
    const rect = header.getBoundingClientRect()
    top.value = rect.bottom + window.scrollY
  }

  update()
  // if the header resizes, for example when the window changes size, reposition
  observer = new ResizeObserver(update)
  observer.observe(header)
})

onUnmounted(() => {
  if (observer) observer.disconnect()
})
</script>

<template>
  <div class="profile" :style="{ top: top + 'px' }">
    <img :src="template" alt="Profile" class="profile-pic" />
  </div>
</template>

<style scoped>
.profile {
  position: absolute;
  right: clamp(6px, 2vw, 16px);
  padding: clamp(4px, 1vw, 8px);
  z-index: 9999;
}

.profile-pic {
  display: block;
  width: clamp(28px, 3vw, 48px);
  height: clamp(28px, 3vw, 48px);
  border-radius: 50%;
  cursor: pointer;
  object-fit: cover;
}
</style>