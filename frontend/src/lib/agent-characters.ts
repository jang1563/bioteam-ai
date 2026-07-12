/**
 * Agent character metadata — maps each agent_id to a visual identity.
 *
 * Each agent gets:
 *   icon    — Lucide icon that reflects the agent's specialty
 *   color   — tier-based color group (8 groups)
 *   tagline — one-line description of what the agent does
 */

import type { LucideIcon } from "lucide-react";
import {
  Atom,
  BarChart2,
  BookOpen,
  Brain,
  CheckCircle2,
  ClipboardList,
  Compass,
  Dna,
  FileSearch,
  GitMerge,
  Layers,
  Microscope,
  Network,
  PenLine,
  RefreshCw,
  Rss,
  Ruler,
  BadgeDollarSign,
  ScanText,
  Server,
  Shield,
  TestTube2,
  Zap,
} from "lucide-react";

// ── Color scheme ──────────────────────────────────────────────────────────────

export type AgentColor =
  | "indigo"
  | "teal"
  | "blue"
  | "violet"
  | "orange"
  | "amber"
  | "rose"
  | "purple";

export const AGENT_COLOR_CLASSES: Record<
  AgentColor,
  { bg: string; text: string; ring: string; dot: string }
> = {
  indigo: {
    bg: "bg-indigo-500/20",
    text: "text-indigo-400",
    ring: "ring-indigo-500/40",
    dot: "bg-indigo-400",
  },
  teal: {
    bg: "bg-teal-500/20",
    text: "text-teal-400",
    ring: "ring-teal-500/40",
    dot: "bg-teal-400",
  },
  blue: {
    bg: "bg-blue-500/20",
    text: "text-blue-400",
    ring: "ring-blue-500/40",
    dot: "bg-blue-400",
  },
  violet: {
    bg: "bg-violet-500/20",
    text: "text-violet-400",
    ring: "ring-violet-500/40",
    dot: "bg-violet-400",
  },
  orange: {
    bg: "bg-orange-500/20",
    text: "text-orange-400",
    ring: "ring-orange-500/40",
    dot: "bg-orange-400",
  },
  amber: {
    bg: "bg-amber-500/20",
    text: "text-amber-400",
    ring: "ring-amber-500/40",
    dot: "bg-amber-400",
  },
  rose: {
    bg: "bg-rose-500/20",
    text: "text-rose-400",
    ring: "ring-rose-500/40",
    dot: "bg-rose-400",
  },
  purple: {
    bg: "bg-purple-500/20",
    text: "text-purple-400",
    ring: "ring-purple-500/40",
    dot: "bg-purple-400",
  },
};

// ── Character definition ──────────────────────────────────────────────────────

export interface AgentCharacter {
  icon: LucideIcon;
  color: AgentColor;
  tagline: string;
}

// ── Tier group definitions (for roster page layout) ───────────────────────────

export interface AgentTierGroup {
  label: string;
  agentIds: string[];
}

export const AGENT_TIER_GROUPS: AgentTierGroup[] = [
  {
    label: "Strategic Command",
    agentIds: ["research_director", "knowledge_manager", "project_manager"],
  },
  {
    label: "Domain — Wet / Dry Lab",
    agentIds: ["t01_genomics", "t02_transcriptomics", "t03_proteomics"],
  },
  {
    label: "Domain — Computation",
    agentIds: ["t04_biostatistics", "t05_ml_dl", "t06_systems_bio", "t07_structural_bio"],
  },
  {
    label: "Domain — Translation",
    agentIds: ["t08_scicomm", "t09_grants", "t10_data_eng"],
  },
  {
    label: "Cross-Cutting",
    agentIds: ["experimental_designer", "integrative_biologist"],
  },
  {
    label: "Specialized Engines",
    agentIds: ["ambiguity_engine", "data_integrity_auditor", "digest_agent"],
  },
  {
    label: "QA Tier",
    agentIds: ["qa_statistical_rigor", "qa_biological_plausibility", "qa_reproducibility"],
  },
  {
    label: "Paper Review",
    agentIds: ["claim_extractor", "methodology_reviewer"],
  },
];

// ── Agent character map (all 22 agents) ───────────────────────────────────────

export const AGENT_CHARACTERS: Record<string, AgentCharacter> = {
  // Strategic Command (indigo)
  research_director: {
    icon: Compass,
    color: "indigo",
    tagline: "Orchestrates your research strategy",
  },
  knowledge_manager: {
    icon: BookOpen,
    color: "indigo",
    tagline: "Retrieves and stores scientific knowledge",
  },
  project_manager: {
    icon: ClipboardList,
    color: "indigo",
    tagline: "Tracks tasks and timelines",
  },

  // Domain — Wet / Dry Lab (teal)
  t01_genomics: {
    icon: Dna,
    color: "teal",
    tagline: "Decodes genome and epigenome data",
  },
  t02_transcriptomics: {
    icon: Microscope,
    color: "teal",
    tagline: "Analyzes gene expression patterns",
  },
  t03_proteomics: {
    icon: Atom,
    color: "teal",
    tagline: "Profiles proteins and metabolites",
  },

  // Domain — Computation (blue)
  t04_biostatistics: {
    icon: BarChart2,
    color: "blue",
    tagline: "Ensures statistical rigor",
  },
  t05_ml_dl: {
    icon: Brain,
    color: "blue",
    tagline: "Designs ML and deep learning models",
  },
  t06_systems_bio: {
    icon: Network,
    color: "blue",
    tagline: "Maps pathways and biological networks",
  },
  t07_structural_bio: {
    icon: Layers,
    color: "blue",
    tagline: "Predicts protein structure and docking",
  },

  // Domain — Translation (violet)
  t08_scicomm: {
    icon: PenLine,
    color: "violet",
    tagline: "Crafts your scientific narrative",
  },
  t09_grants: {
    icon: BadgeDollarSign,
    color: "violet",
    tagline: "Builds winning grant proposals",
  },
  t10_data_eng: {
    icon: Server,
    color: "violet",
    tagline: "Designs scalable data pipelines",
  },

  // Cross-Cutting (orange)
  experimental_designer: {
    icon: TestTube2,
    color: "orange",
    tagline: "Plans robust experiments",
  },
  integrative_biologist: {
    icon: GitMerge,
    color: "orange",
    tagline: "Synthesizes cross-omics insights",
  },

  // Specialized Engines (amber)
  ambiguity_engine: {
    icon: Zap,
    color: "amber",
    tagline: "Detects contradictions in evidence",
  },
  data_integrity_auditor: {
    icon: Shield,
    color: "amber",
    tagline: "Audits data integrity and retractions",
  },
  digest_agent: {
    icon: Rss,
    color: "amber",
    tagline: "Summarizes today's research digest",
  },

  // QA Tier (rose)
  qa_statistical_rigor: {
    icon: Ruler,
    color: "rose",
    tagline: "Validates statistical methods",
  },
  qa_biological_plausibility: {
    icon: CheckCircle2,
    color: "rose",
    tagline: "Checks biological consistency",
  },
  qa_reproducibility: {
    icon: RefreshCw,
    color: "rose",
    tagline: "Assesses reproducibility compliance",
  },

  // Paper Review (purple)
  claim_extractor: {
    icon: FileSearch,
    color: "purple",
    tagline: "Extracts structured claims from papers",
  },
  methodology_reviewer: {
    icon: ScanText,
    color: "purple",
    tagline: "Deep-reviews experimental methodology",
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const FALLBACK_CHARACTER: AgentCharacter = {
  icon: Brain,
  color: "blue",
  tagline: "Specialized research agent",
};

export function getAgentCharacter(agentId: string): AgentCharacter {
  return AGENT_CHARACTERS[agentId] ?? FALLBACK_CHARACTER;
}
