<script setup>
// Big-improvement splash. Polls /tests/improvements/pending every 15 s when
// the user is logged in. If anything comes back, shows a full-screen modal
// with the old grade in red strikethrough → arrow → the new grade in big
// green. Clicking "Continuă" or hitting Escape acks the improvement so it
// never fires again for the same event.
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { testsApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const event   = ref(null)
let   timer   = null
const POLL_MS = 15000

const isAuthed = computed(() => !!currentUser.value)
const eligibleRole = computed(() => ['student', 'parent'].includes(currentUser.value?.role))

async function poll() {
  if (!isAuthed.value || !eligibleRole.value) return
  if (event.value) return            // already showing one; wait for ack
  try {
    const rows = await testsApi.pendingImprovements()
    if (Array.isArray(rows) && rows.length > 0) {
      event.value = rows[0]
    }
  } catch {
    // network blip is fine, try again on the next tick
  }
}

async function ack() {
  if (!event.value) return
  const id = event.value.id
  // close the modal immediately so it feels snappy
  event.value = null
  try { await testsApi.ackImprovement(id) } catch {}
  // pull again right away — there may be more queued events
  setTimeout(poll, 200)
}

function onKey(e) { if (e.key === 'Escape') ack() }

onMounted(() => {
  poll()
  timer = setInterval(poll, POLL_MS)
  document.addEventListener('keydown', onKey)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  document.removeEventListener('keydown', onKey)
})

watch(currentUser, () => { event.value = null; poll() })

// confetti dots, just for the wow factor; one element per dot, deterministic
const CONFETTI = Array.from({ length: 24 }, (_, i) => ({
  left: (i * 4.1) % 100,
  delay: (i * 0.13) % 1.5,
  color: ['#ffd24a', '#2a9d2a', '#185FA5', '#e85c5c', '#7b3f9f'][i % 5],
}))
</script>

<template>
  <transition name="splash">
    <div v-if="event" class="splash-overlay" @click.self="ack">
      <!-- confetti -->
      <div v-for="(c, i) in CONFETTI" :key="i"
           class="confetti" :style="{ left: c.left + '%', background: c.color, animationDelay: c.delay + 's' }"></div>

      <div class="splash-card">
        <div class="big-emoji">🎉</div>
        <h1>Felicitări! Ai progresat enorm!</h1>
        <p class="subj">la <b>{{ event.subjectName }}</b></p>

        <div class="grades">
          <div class="g g-old">
            <div class="g-label">Nota anterioară</div>
            <div class="g-num old">{{ event.oldGrade }}</div>
          </div>
          <div class="arrow">→</div>
          <div class="g g-new">
            <div class="g-label">Nota nouă</div>
            <div class="g-num new">{{ event.newGrade }}</div>
          </div>
        </div>

        <p class="delta">+{{ event.delta }} puncte progres!</p>
        <p v-if="event.testTitle" class="test-title">la testul „{{ event.testTitle }}”</p>

        <button class="btn-ok" @click="ack">Continuă</button>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.splash-overlay {
  position: fixed; inset: 0;
  background: linear-gradient(135deg, rgba(24,95,165,0.85), rgba(42,157,42,0.85));
  display: flex; align-items: center; justify-content: center;
  z-index: 9999;
  padding: 16px;
  font-family: 'Inter', sans-serif;
}

.splash-card {
  background: white;
  border-radius: 20px;
  padding: clamp(20px, 4vw, 40px) clamp(20px, 4vw, 56px);
  box-shadow: 0 20px 60px rgba(0,0,0,0.35);
  text-align: center;
  max-width: 500px;
  width: 100%;
  animation: pop 0.35s ease-out;
}
@keyframes pop {
  0%   { transform: scale(0.7); opacity: 0; }
  60%  { transform: scale(1.05); }
  100% { transform: scale(1);    opacity: 1; }
}

.big-emoji {
  font-size: clamp(50px, 8vw, 80px);
  animation: bounce 1s infinite alternate;
}
@keyframes bounce {
  from { transform: translateY(0); }
  to   { transform: translateY(-8px); }
}

h1 {
  margin: 8px 0;
  color: #185FA5;
  font-size: clamp(22px, 3.5vw, 30px);
  font-weight: 900;
}
.subj { color: #555; margin: 0 0 24px; font-size: 16px; }

.grades {
  display: flex; align-items: center; justify-content: center; gap: clamp(16px, 4vw, 36px);
  margin: 16px 0 8px;
}
.g { display: flex; flex-direction: column; align-items: center; }
.g-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
.g-num {
  font-size: clamp(56px, 9vw, 88px);
  font-weight: 900;
  line-height: 1;
  margin-top: 4px;
  width: 110px; text-align: center;
  border-radius: 16px;
}
.g-num.old {
  color: #cc0000;
  text-decoration: line-through;
  background: #ffeded;
  opacity: 0.75;
}
.g-num.new {
  color: #155724;
  background: #d4edda;
  animation: glow 1.4s ease-in-out infinite alternate;
}
@keyframes glow {
  from { box-shadow: 0 0 0 0 rgba(42,157,42,0); }
  to   { box-shadow: 0 0 30px 6px rgba(42,157,42,0.35); }
}

.arrow {
  font-size: clamp(36px, 6vw, 60px);
  color: #185FA5;
  font-weight: 900;
  animation: slide 1.2s ease-in-out infinite;
}
@keyframes slide {
  0%, 100% { transform: translateX(0); }
  50%      { transform: translateX(6px); }
}

.delta {
  display: inline-block;
  background: #ffd24a; color: #5a4500;
  padding: 6px 18px; border-radius: 999px;
  font-weight: 700; margin: 20px 0 4px;
  font-size: 16px;
}
.test-title { color: #888; font-size: 13px; margin: 4px 0 24px; font-style: italic; }

.btn-ok {
  background: #185FA5; color: white; border: none;
  padding: 12px 36px; border-radius: 10px; cursor: pointer;
  font-weight: 700; font-size: 16px;
  font-family: 'Inter', sans-serif;
  transition: background 0.1s;
}
.btn-ok:hover { background: #134d87; }

/* confetti dots raining down behind the card */
.confetti {
  position: absolute; top: -20px; width: 10px; height: 14px;
  border-radius: 2px;
  animation: fall 3s linear infinite;
  pointer-events: none;
  z-index: -1;
}
@keyframes fall {
  0%   { transform: translateY(0) rotate(0deg);   opacity: 1; }
  100% { transform: translateY(120vh) rotate(720deg); opacity: 0.4; }
}

/* transition on the overlay itself */
.splash-enter-active, .splash-leave-active { transition: opacity 0.25s ease; }
.splash-enter-from, .splash-leave-to { opacity: 0; }
</style>
