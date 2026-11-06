<script setup lang="ts">
import AppLogo from './AppLogo.vue'
</script>

<template>
  <section class="auth-page">
    <div class="auth-aurora auth-aurora--one" aria-hidden="true" />
    <div class="auth-aurora auth-aurora--two" aria-hidden="true" />
    <div class="auth-brand-panel">
      <div class="auth-brand-lockup">
        <AppLogo :size="58" />
        <span>学术投稿助手</span>
      </div>
      <p class="auth-brand-kicker">ACADEMIC SUBMISSION AGENT</p>
      <h2>让每一份研究，<br><span>抵达更广阔的世界。</span></h2>
      <p class="auth-brand-description">连接稿件、作者与期刊，让复杂的投稿流程变得清晰、有序、值得信赖。</p>
      <div class="auth-feature-list" aria-label="产品能力">
        <span><i aria-hidden="true" />稿件版本，清晰可溯</span>
        <span><i aria-hidden="true" />作者协作，权限分明</span>
        <span><i aria-hidden="true" />期刊信息，集中管理</span>
      </div>
      <p class="auth-brand-footnote">为学术研究而设的投稿工作区</p>
    </div>
    <slot />
  </section>
</template>
