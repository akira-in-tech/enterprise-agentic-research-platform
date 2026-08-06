import "@fontsource-variable/inter";
import "./styles.css";

import { VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";

const app = createApp(App);

app
  .use(createPinia())
  .use(router)
  .use(VueQueryPlugin, {
    queryClientConfig: { defaultOptions: { queries: { retry: false } } },
  });

void useAuthStore().bootstrap();

app.mount("#app");
