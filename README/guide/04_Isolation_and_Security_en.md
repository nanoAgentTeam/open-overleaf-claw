# Project Isolation and Security

## Role-Based Permission Isolation

The system distinguishes Agent permissions through roles:

- **Assistant (Main Agent)**: Has full read/write access to core
- **Worker (SubAgent)**: Can only read core; writes are redirected to its own overlay directory
- **GitAgent**: Dedicated Git operation permissions, only activated in `/git` mode

## Path Security

- All file operations undergo path validation; `..` and absolute paths are rejected to prevent sandbox escape
- Bash command working directories are locked to core and cannot access external files

## Write Protection

- SubAgent writes do not directly affect core; they must go through the merge process
- Truncated write operations are rejected to prevent file corruption
- Every write is tracked and batch auto-committed at the end of each turn

## How Project Files Are Modified

### Direct Modification (Main Agent)

The main Agent writes directly to the core directory. Every write is tracked and automatically git committed at the end of each turn.

### Indirect Modification (SubAgent)

SubAgents write to their own overlay directories (isolated). After completion, changes are merged to core or `_subagent_results/` through the merge mechanism.

### Context Safety

- The Agent loop has deadlock detection: if the same tool call repeats more than 3 times, it triggers Meta-Diagnosis (an independent LLM analyzes the deadlock cause and intervenes)
- Context overflow has three-level protection: proactive compression at the 70% threshold, forced summarization at the safety limit, and recovery retry after failure
