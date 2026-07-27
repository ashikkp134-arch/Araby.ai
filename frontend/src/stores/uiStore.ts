import { create } from 'zustand';

interface UiState {
  chatOpen: boolean;
  previewOpen: boolean;
  setChatOpen: (open: boolean) => void;
  setPreviewOpen: (open: boolean) => void;
  toggleChat: () => void;
  togglePreview: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  chatOpen: true,
  previewOpen: false,
  setChatOpen: (open) => set({ chatOpen: open }),
  setPreviewOpen: (open) => set({ previewOpen: open }),
  toggleChat: () => set((state) => ({ chatOpen: !state.chatOpen })),
  togglePreview: () => set((state) => ({ previewOpen: !state.previewOpen })),
}));
