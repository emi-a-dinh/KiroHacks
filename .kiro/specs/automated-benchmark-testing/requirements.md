# Requirements Document

## Introduction

The AI IDE Token Benchmark currently requires a human operator to manually copy-paste each prompt into Kiro's chat UI, wait for Kiro to respond, and press Enter to advance through every turn of every session — twice (once for baseline, once for treatment). This manual loop is slow, error-prone, and blocks the operator for the entire duration of both runs.

This feature replaces the entire manual benchmark workflow with fully automated execution. An **Automation Driver** launches Kiro as a subprocess with the correct environment variables (proxy settings), sends each prompt from the Session_Script to Kiro programmatically, waits for Kiro's response to complete, captures the response, and advances to the next turn — all without human intervention. The existing proxy interception, session script generation, and reporting pipeline remain unchanged; only the orchestration layer between the Benchmark_Runner and Kiro is automated.

For the baseline run, the Automation Driver disables the token-miser Power by setting `"disabled": true` in `.kiro/settings/mcp.json` and removing or disabling the auto-included steering file. For the treatment run, it re-enables the Power by setting `"disabled": false` and restoring the steering file. This ensures the A/B comparison is controlled programmatically without operator intervention.

The operator launches a single `benchmark run` command and receives the Comparison_Report at the end without further interaction.

## Glossary

- **Benchmark_Runner**: The core component that orchestrates proxy setup, session script generation, run collection, and report production.
- **Automation_Driver**: The new component that programmatically sends prompts to Kiro and collects responses, replacing the manual input() loop in the Orchestrator.
- **Kiro_Process**: A Kiro IDE instance launched as a subprocess by the Automation_Driver with specific environment variables (proxy settings, TLS bypass).
- **Prompt_Sender**: The subcomponent of the Automation_Driver responsible for delivering a single prompt string to Kiro's chat interface programmatically.
- **Response_Watcher**: The subcomponent of the Automation_Driver responsible for detecting when Kiro has finished responding to a prompt, using proxy traffic observation (no new API responses for a configurable idle period).
- **Power_Manager**: The subcomponent of the Automation_Driver responsible for enabling and disabling the token-miser Power between runs by modifying `.kiro/settings/mcp.json` and the auto-included steering file.
- **Idle_Timeout**: The configurable duration of silence (no new proxy JSONL entries) after which the Response_Watcher considers Kiro's response complete. Default: 30 seconds.
- **Turn_Timeout**: The maximum wall-clock time the Automation_Driver waits for a single Turn to complete before marking it as timed out. Default: 300 seconds (5 minutes).
- **Session_Script**: A structured document containing all sessions and their ordered prompts for both runs.
- **Proxy**: The mitmproxy-based HTTPS interceptor that captures API responses and extracts credit usage data.
- **Token_Report**: The structured output produced after a benchmark run, containing per-turn and per-session usage data.
- **Comparison_Report**: The output document comparing Baseline_Run and Treatment_Run usage, showing reduction ratios and assessment.
- **Baseline_Run**: A benchmark run with Kiro and the token-miser Power disabled.
- **Treatment_Run**: A benchmark run with Kiro and the token-miser Power enabled.
- **MCP_Config**: The `.kiro/settings/mcp.json` file that controls which MCP servers (Powers) are active in Kiro.
- **Steering_File**: The `.kiro/steering/token-miser.md` file with `inclusion: auto` that triggers the token-miser Power's behavior when active.
- **MCP_Tool_Prefix**: A short command keyword (e.g., `miser-fix`, `miser-ask`, `miser-plan`) prepended to a prompt to trigger Kiro to invoke the corresponding token-miser MCP tool during the Treatment_Run.
- **Treatment_Prefix_Map**: A mapping from Turn role to MCP_Tool_Prefix that determines which prefix to apply for each turn during the Treatment_Run. Default mapping: `task_description` → `miser-plan`, `clarifying_question` → `miser-ask`, `implementation` → `miser-fix`, `verification` → `miser-ask`.

---

## Requirements

### Requirement 1: Automated Benchmark Execution

**User Story:** As a benchmark operator, I want to run the full benchmark (baseline + treatment) without manual intervention, so that I can start the process and walk away while it completes.

#### Acceptance Criteria

1. THE Benchmark_Runner SHALL execute both the Baseline_Run and the Treatment_Run in a single invocation without requiring any human input.
2. THE Benchmark_Runner SHALL produce Token_Report and Comparison_Report output structures consistent with the existing report schema.
3. WHEN the benchmark completes, THE Benchmark_Runner SHALL print the Comparison_Report summary table to standard output.

---

### Requirement 2: Power Management

**User Story:** As a benchmark operator, I want the tool to automatically disable the token-miser Power for the baseline run and enable it for the treatment run, so that the A/B comparison is controlled without manual Power toggling.

#### Acceptance Criteria

1. WHEN starting the Baseline_Run, THE Power_Manager SHALL disable the token-miser Power by setting `"disabled": true` in the MCP_Config file.
2. WHEN starting the Baseline_Run, THE Power_Manager SHALL disable the token-miser Steering_File so that Kiro does not receive the auto-included agent instructions.
3. WHEN starting the Treatment_Run, THE Power_Manager SHALL enable the token-miser Power by setting `"disabled": false` in the MCP_Config file.
4. WHEN starting the Treatment_Run, THE Power_Manager SHALL restore the token-miser Steering_File to its original state so that Kiro receives the auto-included agent instructions.
5. WHEN the benchmark completes (whether successfully or due to error), THE Power_Manager SHALL restore the MCP_Config and Steering_File to their original pre-benchmark state.
6. THE Power_Manager SHALL create a backup of the MCP_Config and Steering_File before making any modifications, and use the backup for restoration.

---

### Requirement 3: Kiro Process Management

**User Story:** As a benchmark operator, I want the tool to launch and manage Kiro IDE instances automatically, so that I don't have to manually start Kiro with the right environment variables.

#### Acceptance Criteria

1. WHEN starting a run, THE Automation_Driver SHALL launch a Kiro_Process as a subprocess with the environment variables `HTTPS_PROXY`, `HTTP_PROXY`, and `NODE_TLS_REJECT_UNAUTHORIZED=0` set to route traffic through the Proxy.
2. THE Automation_Driver SHALL pass the Target_Repository path as the workspace argument to the Kiro_Process so that Kiro opens the correct project.
3. WHEN transitioning from the Baseline_Run to the Treatment_Run, THE Automation_Driver SHALL stop the current Kiro_Process, reconfigure the Power via the Power_Manager, and start a new Kiro_Process.
4. WHEN the benchmark completes (both runs finished), THE Automation_Driver SHALL terminate the Kiro_Process gracefully.
5. IF the Kiro_Process exits unexpectedly during a run, THEN THE Automation_Driver SHALL log the exit code and error output, and halt the benchmark with a descriptive error message.
6. IF the Kiro_Process fails to start within the configured startup timeout, THEN THE Automation_Driver SHALL emit a descriptive error message and halt the benchmark.

---

### Requirement 4: Prompt Delivery

**User Story:** As a benchmark operator, I want each prompt from the session script sent to Kiro programmatically, so that the benchmark runs without copy-paste errors or human timing variability.

#### Acceptance Criteria

1. FOR EACH Turn in the Session_Script, THE Prompt_Sender SHALL deliver the Turn's prompt text to the active Kiro conversation.
2. THE Prompt_Sender SHALL deliver prompts in the order defined by the Session_Script: sessions in session_id order, turns within each session in turn_number order.
3. THE Prompt_Sender SHALL wait for the Response_Watcher to confirm the previous Turn is complete before delivering the next prompt.
4. WHILE executing the Baseline_Run, THE Prompt_Sender SHALL deliver the prompt text verbatim from the Session_Script without modification.
5. WHILE executing the Treatment_Run, THE Prompt_Sender SHALL prefix each prompt with the appropriate MCP_Tool_Prefix as defined by the Treatment_Prefix_Map before delivering it to Kiro.

---

### Requirement 5: Response Detection

**User Story:** As a benchmark operator, I want the tool to detect when Kiro has finished responding to each prompt, so that it can advance to the next turn at the right time.

#### Acceptance Criteria

1. THE Response_Watcher SHALL monitor the Proxy's JSONL output file for new entries after each prompt is sent.
2. WHEN no new JSONL entries appear for the duration of the Idle_Timeout after at least one entry has been received for the current Turn, THE Response_Watcher SHALL consider the Turn complete.
3. IF no JSONL entries appear within the Turn_Timeout after a prompt is sent, THEN THE Response_Watcher SHALL mark the Turn as timed out and log a warning including the session ID and turn number.
4. WHEN a Turn times out, THE Automation_Driver SHALL continue to the next Turn rather than halting the entire benchmark.
5. THE Response_Watcher SHALL use the Proxy's `read_new_entries` method to track only entries that arrived after the prompt was sent, avoiding double-counting entries from previous turns.

---

### Requirement 6: Session Boundary Management

**User Story:** As a benchmark operator, I want the tool to start a new Kiro conversation between sessions automatically, so that each session has a clean context like the manual process.

#### Acceptance Criteria

1. WHEN all Turns in a Session are complete and another Session follows, THE Automation_Driver SHALL start a new conversation in Kiro before beginning the next Session.
2. THE Automation_Driver SHALL wait for the new conversation to be ready before sending the first prompt of the next Session.
3. WHEN transitioning between the Baseline_Run and the Treatment_Run, THE Automation_Driver SHALL start a fresh Kiro_Process with the appropriate Power configuration as managed by the Power_Manager.

---

### Requirement 7: Configuration for Automation

**User Story:** As a benchmark operator, I want to configure automation-specific parameters (timeouts, Kiro path) in the config file, so that I can tune the automation for different environments.

#### Acceptance Criteria

1. THE Config_File SHALL support an `automation` section with the following optional parameters: `kiro_path` (path to the Kiro executable, default: `kiro`), `idle_timeout` (seconds of silence before considering a turn complete, default: 30), `turn_timeout` (maximum seconds per turn, default: 300), and `startup_timeout` (seconds to wait for Kiro to start, default: 60).
2. WHERE an automation parameter is omitted from the Config_File, THE Benchmark_Runner SHALL apply the documented default value.
3. THE Benchmark_Runner SHALL log the resolved automation configuration at the start of a run.
4. IF the `kiro_path` executable is not found on PATH, THEN THE Benchmark_Runner SHALL emit a descriptive error message and halt before starting the proxy.

---

### Requirement 8: Progress Reporting

**User Story:** As a benchmark operator, I want to see progress updates during an automated run, so that I know the benchmark is advancing and can estimate time remaining.

#### Acceptance Criteria

1. WHEN a Turn completes during a run, THE Benchmark_Runner SHALL print a progress line showing the run type, session number, turn number, and credit usage captured for that turn.
2. WHEN a Session completes during a run, THE Benchmark_Runner SHALL print a summary line showing the session's aggregate credit usage.
3. WHEN a run (Baseline or Treatment) completes, THE Benchmark_Runner SHALL print the total credit usage for that run.
4. IF a Turn times out, THEN THE Benchmark_Runner SHALL print a warning line identifying the timed-out session and turn.

---

### Requirement 9: Error Recovery

**User Story:** As a benchmark operator, I want the automation to handle transient failures gracefully, so that a single flaky turn doesn't invalidate the entire benchmark.

#### Acceptance Criteria

1. IF a Turn times out, THEN THE Automation_Driver SHALL record zero credit usage for that Turn and continue to the next Turn.
2. IF the Kiro_Process becomes unresponsive (no JSONL entries for three consecutive Turns), THEN THE Automation_Driver SHALL restart the Kiro_Process and resume from the current Session.
3. WHEN the Automation_Driver restarts a Kiro_Process mid-run, THE Automation_Driver SHALL log the restart event including the session ID and turn number where the restart occurred.
4. THE Automation_Driver SHALL attempt at most 2 Kiro_Process restarts per run before halting with a descriptive error.
5. WHEN the benchmark halts due to errors, THE Benchmark_Runner SHALL write any partial Token_Report data collected so far to disk before exiting.
6. WHEN the benchmark halts due to errors, THE Power_Manager SHALL restore the MCP_Config and Steering_File to their original pre-benchmark state before exiting.

---

### Requirement 10: Treatment Prompt Prefixing

**User Story:** As a benchmark operator, I want treatment run prompts to be prefixed with token-miser MCP tool commands, so that Kiro actually invokes the token-miser context-lens tools during the treatment run and the benchmark measures real MCP tool usage.

#### Acceptance Criteria

1. WHILE executing the Treatment_Run, THE Prompt_Sender SHALL prepend the MCP_Tool_Prefix from the Treatment_Prefix_Map to the prompt text, separated by a space, before delivering it to Kiro.
2. WHILE executing the Baseline_Run, THE Prompt_Sender SHALL deliver prompts verbatim without any prefix.
3. THE Treatment_Prefix_Map SHALL map Turn roles to MCP_Tool_Prefix values as follows: `task_description` → `miser-plan`, `clarifying_question` → `miser-ask`, `implementation` → `miser-fix`, `verification` → `miser-ask`.
4. WHERE a custom Treatment_Prefix_Map is provided in the Config_File, THE Prompt_Sender SHALL use the custom mapping instead of the default.
5. THE Prompt_Sender SHALL accept the run type (baseline or treatment) and the Turn role as inputs when determining whether and how to prefix a prompt.
6. FOR EACH Turn in the Treatment_Run, THE Prompt_Sender SHALL log the MCP_Tool_Prefix applied to that Turn's prompt.
