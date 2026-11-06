<script setup lang="ts">
defineProps<{ name: string }>()
</script>

<template>
  <svg class="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'dashboard'">
      <rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" />
    </template>
    <template v-else-if="name === 'manuscripts'">
      <path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 12h7M9 16h7" />
    </template>
    <template v-else-if="name === 'authors'">
      <circle cx="9" cy="8" r="3" /><path d="M3.5 20v-2.5A4.5 4.5 0 0 1 8 13h2a4.5 4.5 0 0 1 4.5 4.5V20M16 5.5a3 3 0 0 1 0 5.8M17 14a4.5 4.5 0 0 1 3.5 4.4V20" />
    </template>
    <template v-else-if="name === 'authorizations'">
      <path d="M12 3 4.5 6v5.5c0 4.6 3.2 7.8 7.5 9.5 4.3-1.7 7.5-4.9 7.5-9.5V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" />
    </template>
    <template v-else-if="name === 'journals'">
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5zM20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z" />
    </template>
    <template v-else-if="name === 'audit'">
      <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2M8 2.8 6.5 1.5M16 2.8l1.5-1.3" />
    </template>
    <template v-else-if="name === 'logout'">
      <path d="M10 4H5v16h5M14 8l4 4-4 4M8 12h10" />
    </template>
    <template v-else-if="name === 'files'">
      <path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" /><path d="M4 10h16" />
    </template>
    <template v-else-if="name === 'clock'">
      <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2M8 2.8 6.5 1.5" />
    </template>
    <template v-else>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </template>
  </svg>
</template>
