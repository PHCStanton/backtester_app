# Generic Coding Agent Memory System

This guide provides a generic framework for setting up a memory system for coding agents. Based on concepts from Cline's Memory Bank and prompting techniques, this system can be adapted for use with any AI coding assistant.

## Overview

The Generic Coding Agent Memory System helps maintain context across sessions, enforces consistent practices, and improves the effectiveness of your AI coding assistant. It consists of two main components:

1. **Agent Instructions**: Global guidelines that define your coding assistant's baseline behavior
2. **Project Memory System**: Project-specific documentation that maintains context and guides development

## Project-Specific Notes (QuFLX v2)

- Keep `.agent-memory/activeContext.md` aligned with the latest validated state (tests passing, key contracts stable).
- Record contract-level decisions (HTTP status semantics, response shapes like `candles`) in `systemPatterns.md` to prevent regressions.
- When documenting verification commands, prefer listing separate commands (PowerShell does not reliably support `&&`).

## Folder Structure Setup

Create the following folder structure in your project:

```
your-project/
├── .agent-memory/           # Project-specific memory files
│   ├── productContext.md    # Project purpose and goals
│   ├── activeContext.md     # Current work and next steps
│   ├── systemPatterns.md    # Architecture and patterns
│   ├── techContext.md       # Technologies and setup
│   └── progress.md          # Development progress
├── .agentrules              # Project-specific rules (like .clinerules)
└── agent-docs/              # Documentation about using this system
    ├── MEMORY_GUIDE.md      # This file
    └── PROMPTING_GUIDE.md   # Effective prompting techniques
```

## Setup Instructions

### Step 1: Create the Folder Structure

Create the folders and files as shown in the structure above:

```bash
mkdir -p .agent-memory
mkdir -p agent-docs
touch .agent-memory/productContext.md
touch .agent-memory/activeContext.md
touch .agent-memory/systemPatterns.md
touch .agent-memory/techContext.md
touch .agent-memory/progress.md
touch .agentrules
touch agent-docs/MEMORY_GUIDE.md
touch agent-docs/PROMPTING_GUIDE.md
```

### Step 2: Configure Your Coding Agent

Add the following instructions to your coding agent's custom instructions/settings:

```markdown
# Generic Coding Agent Memory System

You are an expert software engineer with a unique constraint: your memory periodically resets completely. This isn't a bug - it's what makes you maintain perfect documentation. After each reset, you rely ENTIRELY on your Memory System to understand the project and continue work. Without proper documentation, you cannot function effectively.

## Memory System Files

CRITICAL: If `.agent-memory/` or any of these files don't exist, CREATE THEM IMMEDIATELY by:

1. Reading all provided documentation
2. Asking user for ANY missing information
3. Creating files with verified information only
4. Never proceeding without complete context

Required files:

### .agent-memory/productContext.md
- Why this project exists
- What problems it solves
- How it should work

### .agent-memory/activeContext.md
- What you're working on now
- Recent changes
- Next steps (This is your source of truth)

### .agent-memory/systemPatterns.md
- How the system is built
- Key technical decisions
- Architecture patterns

### .agent-memory/techContext.md
- Technologies used
- Development setup
- Technical constraints

### .agent-memory/progress.md
- What works
- What's left to build
- Progress status

## Core Workflows

### Starting Tasks
1. Check for Memory System files
2. If ANY files missing, stop and create them
3. Read ALL files before proceeding
4. Verify you have complete context
5. Begin development. DO NOT update .agent-memory after initializing your memory system at the start of a task.

### During Development
1. For normal development:
   - Follow Memory System patterns
   - Update docs after significant changes

2. Say `[MEMORY SYSTEM: ACTIVE]` at the beginning of every tool use.

### Memory System Updates
When user says "update memory system":
1. This means imminent memory reset
2. Document EVERYTHING about current state
3. Make next steps crystal clear
4. Complete current task

Remember: After every memory reset, you begin completely fresh. Your only link to previous work is the Memory System. Maintain it as if your functionality depends on it - because it does.
```

### Step 3: Create the .agentrules File

Create a `.agentrules` file in your project root with project-specific guidelines:

```markdown
# Project Guidelines

## Documentation Requirements
- Update relevant documentation when modifying features
- Keep README.md in sync with new capabilities
- Maintain changelog entries

## Architecture
- Follow established patterns in .agent-memory/systemPatterns.md
- Document significant architectural decisions

## Code Style & Patterns
- Follow the coding standards outlined in .agent-memory/techContext.md
- Maintain consistency with existing codebase

## Testing Standards
- Follow testing requirements in .agent-memory/techContext.md
- Ensure adequate test coverage for new features
```

### Step 4: Initialize the Memory System

To initialize the memory system for a new project:

1. Create a project brief with information about your project
2. Ask your coding agent to "initialize memory system"
3. Provide the project brief when requested

## Memory System File Templates

### .agent-memory/productContext.md

```markdown
# Product Context

## Project Purpose
[Why this project exists]

## Problem Statement
[What problems this project solves]

## Intended Users
[Who will use this product]

## Core Functionality
[How the product should work]

## Success Metrics
[How we measure success]
```

### .agent-memory/activeContext.md

```markdown
# Active Context

## Current Work
[What you're working on now]

## Recent Changes
- [Change 1]
- [Change 2]
- [Change 3]

## Next Steps
1. [Next step 1]
2. [Next step 2]
3. [Next step 3]

## blockers
[Any obstacles or questions]
```

### .agent-memory/systemPatterns.md

```markdown
# System Patterns

## Architecture Overview
[High-level system architecture]

## Key Design Patterns
[Important patterns used in the codebase]

## Data Flow
[How data moves through the system]

## Significant Technical Decisions
- [Decision 1 with rationale]
- [Decision 2 with rationale]
```

### .agent-memory/techContext.md

```markdown
# Technical Context

## Technologies Used
- [Technology 1]: [Purpose]
- [Technology 2]: [Purpose]
- [Technology 3]: [Purpose]

## Development Setup
[How to set up the development environment]

## Dependencies
[Key dependencies and their purposes]

## Technical Constraints
[Limitations or constraints to consider]

## Coding Standards
[Language-specific conventions and standards]

## Testing Requirements
[Testing framework and requirements]
```

### .agent-memory/progress.md

```markdown
# Development Progress

## Completed Features
- [Feature 1]: [Status]
- [Feature 2]: [Status]

## In Progress
- [Feature 3]: [Status and next steps]

## Planned Features
- [Feature 4]: [Priority and estimated effort]
- [Feature 5]: [Priority and estimated effort]

## Known Issues
- [Issue 1]: [Severity and potential solution]
- [Issue 2]: [Severity and potential solution]
```

## Best Practices

### For Users

1. **Initialize properly**: Always start new projects by initializing the memory system
2. **Update regularly**: Ask your agent to "update memory system" before ending sessions
3. **Monitor for flags**: Watch for `[MEMORY SYSTEM: ACTIVE]` to confirm the system is working
4. **Provide context**: Give clear, detailed project briefs to help initialize the memory system
5. **Review updates**: Check memory system updates for accuracy before ending sessions

### For Effective Prompting

1. **Be specific**: Clearly state what you want to accomplish
2. **Provide context**: Reference relevant files using @ notation if your agent supports it
3. **Break down complex tasks**: Divide large tasks into manageable steps
4. **Use confidence checks**: Ask your agent to rate its confidence in solutions
5. **Challenge assumptions**: Encourage critical thinking by asking "stupid questions"

## Advanced Techniques

### Constraint Stuffing
To prevent code truncation, include explicit constraints:
- "DO NOT BE LAZY. DO NOT OMIT CODE."
- "Ensure the code is complete"
- "Full code only"

### Memory Checks
Add memory verification prompts:
- "If you understand my prompt fully, respond with 'MEMORY CHECK' before using tools"
- "Before any tool use, confirm you have the complete context"

### Structured Development
Enforce a methodical approach:
```
"Before writing code:
1. Analyze all code files thoroughly
2. Get full context
3. Write implementation plan
4. Then implement code"
```

## Security Considerations

Include security guidelines in your `.agentrules` file:

```markdown
# Security

## Sensitive Files
DO NOT read or modify:
- .env files
- */config/secrets.*
- */*.pem
- Any file containing API keys, tokens, or credentials

## Security Practices
- Never commit sensitive files
- Use environment variables for secrets
- Keep credentials out of logs and output
```

## Adapting for Different Coding Agents

This system can be adapted for various coding agents:

### For GitHub Copilot
- Add the memory system instructions to your workspace settings
- Use comments in code to reference memory files
- Regularly update memory files manually

### For Amazon CodeWhisperer
- Include memory system context in code comments
- Maintain memory files as part of your project documentation
- Reference memory files when starting new tasks

### For Tabnine
- Add memory system guidelines to your Tabnine settings
- Use the memory system to maintain context across sessions
- Update memory files after significant changes

## Conclusion

The Generic Coding Agent Memory System provides a structured approach to maintaining context, enforcing consistency, and improving the effectiveness of AI coding assistants. By implementing this system, you can create a more productive development workflow that leverages the full potential of your coding agent.

Remember that this system is designed to be flexible. Adapt it to your specific needs, project requirements, and the capabilities of your chosen coding agent.
