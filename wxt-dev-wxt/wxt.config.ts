import { defineConfig } from 'wxt';

// See https://wxt.dev/api/config.html
export default defineConfig({
  modules: ['@wxt-dev/module-react', '@wxt-dev/auto-icons'],
  autoIcons: {
    baseIconPath: 'assets/icon.svg',
  },
  manifest: {
    name: 'Intern.ly',
    description: 'Generate a resume for your internship applications',
    version: '0.1.0',
    permissions: ['clipboardRead', 'clipboardWrite', 'storage'],
    host_permissions: ['http://localhost:8000/*', 'https://*/*'],
  },
});
