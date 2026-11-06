<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{ size?: number }>(), { size: 48 })
const gradientId = `app-logo-gradient-${useId()}`
const sheenId = `app-logo-sheen-${useId()}`
</script>

<template>
  <svg
    class="app-logo"
    data-test="app-logo"
    :width="size"
    :height="size"
    viewBox="0 0 64 64"
    fill="none"
    role="img"
    aria-label="学术投稿助手标志"
  >
    <defs>
      <linearGradient :id="gradientId" x1="8" y1="6" x2="58" y2="60" gradientUnits="userSpaceOnUse">
        <stop stop-color="#2DD4BF" />
        <stop offset="0.48" stop-color="#4F8CFF" />
        <stop offset="1" stop-color="#8B5CF6" />
      </linearGradient>
      <radialGradient :id="sheenId" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(17 12) rotate(51) scale(55)">
        <stop stop-color="white" stop-opacity="0.42" />
        <stop offset="0.55" stop-color="white" stop-opacity="0" />
      </radialGradient>
    </defs>
    <rect x="3" y="3" width="58" height="58" rx="18" :fill="`url(#${gradientId})`" />
    <rect x="3" y="3" width="58" height="58" rx="18" :fill="`url(#${sheenId})`" />
    <rect x="3.75" y="3.75" width="56.5" height="56.5" rx="17.25" stroke="white" stroke-opacity="0.28" stroke-width="1.5" />
    <path d="M19 15.5C19 14.67 19.67 14 20.5 14H38L46 22V47.5C46 48.33 45.33 49 44.5 49H20.5C19.67 49 19 48.33 19 47.5V15.5Z" fill="white" fill-opacity="0.96" />
    <path d="M38 14V20.5C38 21.33 38.67 22 39.5 22H46L38 14Z" fill="#C7F9F0" />
    <path d="M25 37.5L32.5 30L40 37.5M32.5 31V43" stroke="#3276D9" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" />
    <path d="M25 25.5H31.5" stroke="#7A8EB7" stroke-width="2.4" stroke-linecap="round" />
    <circle cx="49" cy="14" r="3" fill="#A7F3D0" />
    <circle cx="49" cy="14" r="5.5" stroke="#A7F3D0" stroke-opacity="0.35" />
  </svg>
</template>
