# 04 — Brain and Routing

The brain decides what to do with each utterance and manages VS Code automation.

## Utterance Routing Flow

```mermaid
flowchart TD
    UTT["Utterance received"] --> ECHO{During TTS?}
    ECHO -->|Yes, no wake word| DROP[Discard — echo/noise]
    ECHO -->|Yes, has wake word| INTERRUPT[Stop TTS, continue]
    ECHO -->|No| PERM{Permission dialog<br/>pending?}
    INTERRUPT --> PERM

    PERM -->|Yes| PERM_HANDLE[Handle yes/no response]
    PERM -->|No| PROMPT{Input prompt<br/>pending?}

    PROMPT -->|Yes| PROMPT_HANDLE[Send text to prompt input]
    PROMPT -->|No| WAKE{Wake word present?}

    WAKE -->|No, not in conversation| IGNORE["Ignore — 'say Cyrus, ...'"]
    WAKE -->|No, in conversation| STRIP_NONE[Use text as-is]
    WAKE -->|Yes| STRIP[Strip wake word]

    STRIP --> EMPTY{Text empty<br/>after strip?}
    EMPTY -->|Yes| LISTEN["Play listen chime<br/>Wait 6s for follow-up"]
    EMPTY -->|No| ROUTE[Route text]
    STRIP_NONE --> ROUTE
    LISTEN -->|Got follow-up| ROUTE
    LISTEN -->|Timeout| IGNORE2[No command heard]

    ROUTE --> FAST{"_fast_command()<br/>Regex match?"}
    FAST -->|Match| EXECUTE[Execute Cyrus command]
    FAST -->|No match| ANSWER{"_is_answer_request()?"}
    ANSWER -->|Yes| REPLAY[Speak last response]
    ANSWER -->|No| FORWARD["Forward to Claude Code"]
```

## Fast Commands (Regex)

These are handled locally with zero latency — no LLM or network call needed.

| Pattern | Command Type | Action |
|---------|-------------|--------|
| `pause`, `resume`, `stop listening` | `pause` | Toggle `_user_paused` (split) or send pause to voice (split) |
| `unlock`, `auto`, `follow focus` | `unlock` | Clear `_project_locked`, follow window focus |
| `which project`, `what session` | `which_project` | Speak active project name + lock status |
| `switch to X`, `go to X`, `use X`, `open X` | `switch_project` | Set active project, lock routing |
| `last message`, `repeat`, `replay` | `last_message` | Re-speak last response for active project |
| `rename this to X`, `call this X` | `rename_session` | Update session alias |
| `rename X to Y` | `rename_session` | Update specific session alias |

## Answer Request Detection

The `_ANSWER_RE` regex catches phrases like:
- "recap", "summarize", "summary"
- "what did Claude say", "what was the response"
- "last response", "last reply"
- "repeat that", "repeat what you said"

When matched, the last spoken response is replayed (truncated to 30 words with "See the chat for more.").

## Multi-Session Management

```mermaid
flowchart TD
    subgraph "Session Discovery — every 5 seconds"
        SCAN["Scan gw.getAllWindows()"] --> PARSE["Parse title: 'file.py - my-project - VS Code'"]
        PARSE --> EXTRACT["_extract_project() -> 'my-project'"]
        EXTRACT --> NEW{New project?}
        NEW -->|Yes| CREATE["Create ChatWatcher thread<br/>Create PermissionWatcher thread<br/>Register alias ('my project')"]
        NEW -->|No| SKIP[Skip]
    end

    subgraph "Active Project Tracking — every 0.5s"
        FOCUS["Poll gw.getActiveWindow()"] --> VSCODE{Is it VS Code?}
        VSCODE -->|No| NOOP[Skip]
        VSCODE -->|Yes| LOCKED{Project locked?}
        LOCKED -->|Yes| KEEP[Keep current project]
        LOCKED -->|No| SWITCH["Switch _active_project<br/>Flush pending queue"]
    end
```

### Session Aliases

Project names like `my-web-app` get aliases like `my web app` (dashes/underscores replaced with spaces). The `_resolve_project()` function matches queries against aliases using exact match first, then substring match (longest alias wins).

### Pending Response Queue

```mermaid
sequenceDiagram
    participant CW_B as ChatWatcher (Project B)
    participant Brain as Brain
    participant User as User

    Note over CW_B: Claude responds in Project B
    CW_B->>Brain: New response detected
    Brain->>Brain: Project B is NOT active
    Brain->>Brain: Queue in B's _pending_queue
    Brain->>User: Play chime

    User->>Brain: "Cyrus, switch to Project B"
    Brain->>Brain: Set active = B, lock routing
    Brain->>Brain: flush_pending() -> speak all queued items
    Brain->>User: Speak queued responses in order
```

## ChatWatcher

Each VS Code session gets a dedicated `ChatWatcher` running on a daemon thread.

**How it finds the chat panel:**
1. Find VS Code window by `SubName`
2. Find `Chrome_RenderWidgetHostHWND` pane (depth 12)
3. Collect all `DocumentControl` nodes inside it
4. Prefer unnamed documents (the chat webview), else pick the deepest

**How it extracts responses:**
1. Walk the UIA tree (depth 12) collecting `(depth, controlType, name)` tuples
2. Find `"Message input"` EditControl as end anchor
3. Find last `"Thinking"` ButtonControl before it (start of Claude's response)
4. Fallback: last `"Message actions"` ButtonControl
5. Collect TextControl/ListItemControl text between start and end, deduplicating

**Stability check:** Response must be unchanged for 1.2s (`STABLE_SECS`) before speaking. This prevents reading partial streaming responses.

**New submission detection:** Counts `"Message actions"` buttons. An increase means the user submitted a new message, so `_last_spoken` is cleared to allow speaking the same text again.

## Submit Pipeline

```mermaid
flowchart TD
    TEXT[Text to submit] --> EXT{Companion Extension<br/>available?}

    EXT -->|Yes| SOCK["Send via IPC socket<br/>{text: '...'}"]
    SOCK --> EXT_RESULT{ok: true?}
    EXT_RESULT -->|Yes| DONE[Submit complete]
    EXT_RESULT -->|No| FALLBACK

    EXT -->|No| FALLBACK[UIA Fallback]
    FALLBACK --> COORDS{Cached pixel<br/>coords for project?}
    COORDS -->|No| WAIT["Wait up to 6s for ChatWatcher<br/>to populate coords"]
    WAIT --> SEARCH["_find_chat_input() UIA search"]
    COORDS -->|Yes| ACTIVATE[Activate VS Code window]
    SEARCH --> ACTIVATE
    ACTIVATE --> CLICK["pyautogui.click(cx, cy)"]
    CLICK --> PASTE["pyperclip.copy() + Ctrl+V"]
    PASTE --> REACTIVATE["Re-activate window (focus steal guard)"]
    REACTIVATE --> ENTER["pyautogui.press('enter')"]
    ENTER --> RESTORE[Restore original clipboard]
```

In the **split architecture**, the submit runs on a dedicated thread (`_submit_worker`) with its own `comtypes.CoInitializeEx()` call. Requests are dispatched via `_submit_request_queue` with a threading.Event for synchronization.

## Whisper Prompt Management

As sessions are discovered, the brain builds a prompt string like `"Cyrus, switch to web-app cyrus."` and sends it to the voice service. This helps Whisper correctly recognize short project names.
