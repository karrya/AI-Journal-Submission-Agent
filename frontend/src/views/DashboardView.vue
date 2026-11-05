<template>
  <section aria-labelledby="dashboard-title">
    <h1 id="dashboard-title">Dashboard</h1>
    <p>Your submission workspace is ready.</p>
    <nav class="dashboard-links" aria-label="Management pages">
      <router-link to="/authors">Manage authors and institutions</router-link>
      <router-link to="/authorizations">Manage author authorizations</router-link>
      <router-link to="/journals">Manage publishers, platforms, and journals</router-link>
    </nav>
  </section>
</template>
