import type { RecentResearchRun } from "../types/research";

const STORAGE_KEY = "evident.research-history.v1";
const MAX_HISTORY_ITEMS = 8;

export function loadResearchHistory(): RecentResearchRun[] {
  const serialized = localStorage.getItem(STORAGE_KEY);

  if (!serialized) {
    return [];
  }

  try {
    const history = JSON.parse(serialized) as RecentResearchRun[];
    return Array.isArray(history) ? history.slice(0, MAX_HISTORY_ITEMS) : [];
  } catch {
    return [];
  }
}

export function saveResearchHistory(history: RecentResearchRun[]): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(history.slice(0, MAX_HISTORY_ITEMS)),
  );
}
