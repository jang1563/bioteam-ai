import { create } from "zustand";
import type {
  AgentListItem,
  WorkflowStatus,
  SSEEvent,
} from "@/types/api";

interface AppState {
  // Agents
  agents: AgentListItem[];
  setAgents: (agents: AgentListItem[]) => void;

  // Workflows
  workflows: WorkflowStatus[];
  setWorkflows: (workflows: WorkflowStatus[]) => void;
  updateWorkflow: (id: string, partial: Partial<WorkflowStatus>) => void;

  // SSE activity feed
  events: SSEEvent[];
  addEvent: (event: SSEEvent) => void;
  clearEvents: () => void;

  // UI state
  selectedAgentId: string | null;
  setSelectedAgentId: (id: string | null) => void;
  selectedWorkflowId: string | null;
  setSelectedWorkflowId: (id: string | null) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Agents
  agents: [],
  setAgents: (agents) => set({ agents }),

  // Workflows
  workflows: [],
  setWorkflows: (workflows) => set({ workflows }),
  updateWorkflow: (id, partial) =>
    set((state) => ({
      workflows: state.workflows.map((w) =>
        w.id === id ? { ...w, ...partial } : w,
      ),
    })),

  // SSE events — keep last 100
  events: [],
  addEvent: (event) =>
    set((state) => ({
      events: [event, ...state.events].slice(0, 100),
    })),
  clearEvents: () => set({ events: [] }),

  // UI
  selectedAgentId: null,
  setSelectedAgentId: (id) => set({ selectedAgentId: id }),
  selectedWorkflowId: null,
  setSelectedWorkflowId: (id) => set({ selectedWorkflowId: id }),
  sidebarCollapsed: false,
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
}));
