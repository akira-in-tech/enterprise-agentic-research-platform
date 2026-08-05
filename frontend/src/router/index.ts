import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
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

export default router;
