import { create } from 'zustand';
import type { EditorTab } from '@/types';

interface EditorState {
  tabs: EditorTab[];
  activeTabId: string | null;
  openTab: (tab: EditorTab) => void;
  closeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  updateContent: (tabId: string, content: string) => void;
  markSaved: (tabId: string, content: string) => void;
  syncTab: (tabId: string, next: EditorTab) => void;
  replaceTabMeta: (tabId: string, patch: Partial<EditorTab>) => void;
  reset: () => void;
}

export const useEditorStore = create<EditorState>((set, get) => ({
  tabs: [],
  activeTabId: null,

  openTab: (tab) => {
    const existing = get().tabs.find((item) => item.id === tab.id);
    if (existing) {
      // Adopt the freshly loaded content unless the user has unsaved edits.
      set((state) => ({
        tabs: state.tabs.map((item) =>
          item.id === tab.id && !item.dirty ? { ...item, ...tab } : item,
        ),
        activeTabId: existing.id,
      }));
      return;
    }
    set((state) => ({
      tabs: [...state.tabs, tab],
      activeTabId: tab.id,
    }));
  },

  closeTab: (tabId) => {
    set((state) => {
      const tabs = state.tabs.filter((tab) => tab.id !== tabId);
      const activeTabId =
        state.activeTabId === tabId ? tabs[tabs.length - 1]?.id ?? null : state.activeTabId;
      return { tabs, activeTabId };
    });
  },

  setActiveTab: (tabId) => set({ activeTabId: tabId }),

  updateContent: (tabId, content) => {
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === tabId ? { ...tab, content, dirty: true } : tab,
      ),
    }));
  },

  markSaved: (tabId, content) => {
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === tabId ? { ...tab, content, dirty: false } : tab,
      ),
    }));
  },

  syncTab: (tabId, next) => {
    set((state) => ({
      tabs: state.tabs.map((tab) => (tab.id === tabId ? next : tab)),
      activeTabId: state.activeTabId === tabId ? next.id : state.activeTabId,
    }));
  },

  replaceTabMeta: (tabId, patch) => {
    set((state) => ({
      tabs: state.tabs.map((tab) => (tab.id === tabId ? { ...tab, ...patch } : tab)),
    }));
  },

  reset: () => set({ tabs: [], activeTabId: null }),
}));
