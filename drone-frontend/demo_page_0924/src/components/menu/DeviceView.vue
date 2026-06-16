<!-- src/components/menu/DeviceView.vue -->
<script setup>
</script>

<template>
  <div class="menu-module-dark">
    <router-view v-slot="{ Component }">
      <keep-alive include="DeviceAirport,DeviceDrone">
        <component :is="Component" />
      </keep-alive>
    </router-view>
  </div>
</template>
<style scoped>
</style>
