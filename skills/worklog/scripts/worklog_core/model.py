"""Normalized data model shared by all adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Session:
    tool: str                      # "claude", "codex", "kiro", "opencode"
    session_id: str
    cwd: Optional[str] = None      # working directory the session ran in
    title: Optional[str] = None
    branch: Optional[str] = None
    prompts: List[str] = field(default_factory=list)           # real user requests, in order
    files: List[str] = field(default_factory=list)             # files edited/created/deleted
    commands: List[str] = field(default_factory=list)          # shell commands run
    events: List[datetime] = field(default_factory=list)       # activity timestamps (aware)
    last_reply: Optional[str] = None                           # last assistant message in range
    parent_id: Optional[str] = None                            # set for subagent/workflow threads
    agent: Optional[str] = None                                # subagent role/name, if any
    subtasks: List[str] = field(default_factory=list)          # merged child agent/workflow names
    subagents: int = 0

    def add_file(self, path: Optional[str]) -> None:
        if path and path not in self.files:
            self.files.append(path)

    def add_prompt(self, text: Optional[str]) -> None:
        if text and (not self.prompts or self.prompts[-1] != text):
            self.prompts.append(text)

    def add_subtask(self, name: Optional[str]) -> None:
        if name and name not in self.subtasks:
            self.subtasks.append(name)

    def add_command(self, cmd: Optional[str]) -> None:
        if cmd:
            cmd = " ".join(cmd.split())
            if cmd and cmd not in self.commands:
                self.commands.append(cmd)

    @property
    def start(self) -> Optional[datetime]:
        return min(self.events) if self.events else None

    @property
    def end(self) -> Optional[datetime]:
        return max(self.events) if self.events else None

    def has_work(self) -> bool:
        return bool(self.prompts or self.files)
