import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "../stores/auth";

function isDesignPreview(): boolean {
  return import.meta.env.DEV && new URLSearchParams(window.location.search).has("design-preview");
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("../views/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/register",
      name: "register",
      component: () => import("../views/RegisterView.vue"),
      meta: { public: true },
    },
    {
      path: "/",
      name: "home",
      component: () => import("../views/HomeView.vue"),
    },
    {
      path: "/knowledge",
      name: "knowledge",
      component: () => import("../views/KnowledgeView.vue"),
    },
    {
      path: "/runs/:id",
      name: "research-run",
      component: () => import("../views/ResearchRunView.vue"),
      props: true,
    },
  ],
});

router.beforeEach(async (to) => {
  if (isDesignPreview()) {
    return true;
  }

  const authStore = useAuthStore();
  await authStore.bootstrap();

  const isPublicRoute = to.meta.public === true;

  if (!isPublicRoute && !authStore.isAuthenticated()) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  if (isPublicRoute && authStore.isAuthenticated()) {
    return { name: "home" };
  }

  return true;
});

export default router;
