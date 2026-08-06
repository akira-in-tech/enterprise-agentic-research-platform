import { VueQueryPlugin } from "@tanstack/vue-query";
import { config } from "@vue/test-utils";
import { afterEach } from "vitest";

// Installed fresh for every mount() call (VueQueryPlugin creates its own
// QueryClient at install time when none is supplied), so query state never
// leaks between tests.
config.global.plugins.push([
  VueQueryPlugin,
  { queryClientConfig: { defaultOptions: { queries: { retry: false } } } },
]);

afterEach(() => {
  document.body.innerHTML = "";
  localStorage.clear();
});
