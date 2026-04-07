# Agent & Contributor Instructions

This file provides instructions for AI agents and human contributors working in this codebase.

## Project Overview

This fork of Synthea is geared towards the generation of Oncology related synthetic data.

## Concept, Requirements and Design

See [`synthea-nsclc-extension-plan.md`](synthea-nsclc-extension-plan.md) for the extension requirements requirements and design of oncology needs. The plan document must be maintained as it will be the main source of truth for full context.

## Workflow Orchestration

### 1. Plan Mode Fault

- Enter plan mode for ANY non-trivial task defined as a task that takes 3 steps or more or that requires architectural decisions.
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this,"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

# Task Management

1. **Plan First**: Write plan to `tasks/todo{timestamp}.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section`to 'tasks/todo{timestamp}.md`
6. **Capture Lessons**: Update 'tasks/lessons.md' after corrections
7. **Update CHANGELOG.md**: After the successful validation of a task, update the CHANGELOG.md with sufficient details

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Top 1% Software Engineer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
