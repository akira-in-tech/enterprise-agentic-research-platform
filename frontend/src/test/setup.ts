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

// jsdom has no layout engine, so it never implements scroll methods.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom does not implement the Blob URL registry used by file downloads.
if (!URL.createObjectURL) {
  URL.createObjectURL = () => "blob:mock-url";
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => {};
}

afterEach(() => {
  document.body.innerHTML = "";
  localStorage.clear();
});
