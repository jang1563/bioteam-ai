# BioTeam-AI Dashboard

Interactive manuscript defense dashboard for the [BioTeam-AI](https://github.com/jang1563/bioteam-ai) biology research copilot.

## Tech Stack

- **Next.js 16** with App Router
- **React 19** + **TypeScript 5**
- **Tailwind CSS 4** + **shadcn/ui** (Radix UI)
- **Zustand** for state management
- **React Flow** (XYFlow) for workflow visualization
- **Playwright** for E2E testing

## Pages (17)

| Page | Route | Description |
|------|-------|-------------|
| Manuscript Studio | `/` | Story, claim, reviewer-risk, and submission-check launch surface |
| Query | `/query` | Submit research questions, view agent responses |
| Digest | `/digest` | Daily literature digest management |
| Projects | `/projects` | Research project tracking |
| Lab KB | `/lab-kb` | Negative results & knowledge base |
| Submission Checks | `/integrity` | Data integrity and submission-readiness checks |
| Reviewer Risks | `/peer-review` | Benchmark-grounded peer review risk interface |
| Settings | `/settings` | Configuration & API keys |
| Claim Strength | `/rcmxt` | Claim-level evidence scoring dashboard |
| Drug Discovery | `/drug-discovery` | Target ID & compound screening |
| Analytics | `/analytics` | System metrics & cost tracking |
| Evidence | `/evidence` | Evidence browser & claim search |
| Agents | `/agents` | Agent roster with chat interface |
| Teams | `/teams` | Multi-agent team configuration |
| Quality | `/quality` | QA metrics & review quality |
| Benchmarks | `/benchmarks` | W8/W9 benchmark results & trends |
| Login | `/login` | JWT authentication |

## Development

```bash
npm install
npm run dev     # http://localhost:3000
```

Requires the backend running at `http://localhost:8000` (see root README).

## Build

```bash
npm run build   # Production build (webpack)
npm start       # Serve production build
```

## Testing

```bash
npx playwright test              # Run all E2E tests
npx playwright test --ui         # Interactive UI mode
npx playwright show-report       # View last test report
```

12 spec files covering agent roster, chat, navigation, benchmarks, dark mode, accessibility, and streaming.

## Project Structure

```
src/
├── app/              # Next.js App Router pages (17 routes)
├── components/       # Reusable UI components (shadcn/ui + custom)
│   ├── ui/           # shadcn/ui primitives (button, card, sheet, etc.)
│   └── ...           # Domain components (agent-card, chat, workflow-graph)
├── hooks/            # React hooks for data fetching & state
├── lib/              # API client, utilities
└── types/            # TypeScript API types
tests/
└── e2e/              # Playwright E2E tests (12 spec files)
```
