import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import path from 'path'
import cesium from 'vite-plugin-cesium' 
// import svgLoader from 'vite-svg-loader'

export default defineConfig({
  plugins: [
    vue(),
    cesium(), // 现在这是可用的
    // svgLoader(),//svg图标
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      directoryAsNamespace: true,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  }
})