from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ElementRef:
    """Representa uma referência estável a um elemento da página."""
    ref_id: str
    tag: str
    text: str
    href: str = None
    attrs: dict = field(default_factory=dict)


@dataclass
class PageSnapshot:
    """Representa um snapshot estruturado da página."""
    url: str
    title: str
    timestamp: float
    elements: list[ElementRef]
    raw_text: str = ""


@dataclass
class BrowserAction:
    """Representa uma ação executada no navegador."""
    action_type: str  # "navigate" | "click" | "fill" | "submit" | "wait" | "scroll"
    target_ref: str = None
    value: str = None
    timestamp: float = 0.0


@dataclass
class BrowserSession:
    """Representa uma sessão de navegação com histórico de ações e snapshots."""
    session_id: str
    actions: list[BrowserAction]
    snapshots: list[PageSnapshot]
    
    def add_action(self, action: BrowserAction) -> None:
        """Adiciona uma ação à sessão."""
        self.actions.append(action)
    
    def add_snapshot(self, snapshot: PageSnapshot) -> None:
        """Adiciona um snapshot à sessão."""
        self.snapshots.append(snapshot)
    
    def last_snapshot(self) -> PageSnapshot | None:
        """Retorna o último snapshot ou None se não houver nenhum."""
        if not self.snapshots:
            return None
        return self.snapshots[-1]
    
    def replay_log(self) -> list[dict]:
        """Retorna um log auditável de todas as ações e snapshots ordenados por timestamp."""
        # Combina ações e snapshots e ordena por timestamp
        combined = []
        for action in self.actions:
            combined.append({
                "type": "action",
                "timestamp": action.timestamp,
                "data": {
                    "action_type": action.action_type,
                    "target_ref": action.target_ref,
                    "value": action.value
                }
            })
        for snapshot in self.snapshots:
            combined.append({
                "type": "snapshot",
                "timestamp": snapshot.timestamp,
                "data": {
                    "url": snapshot.url,
                    "title": snapshot.title,
                    "element_count": len(snapshot.elements),
                    "raw_text_length": len(snapshot.raw_text)
                }
            })
        
        # Ordena por timestamp
        combined.sort(key=lambda x: x["timestamp"])
        return combined
    
    def to_dict(self) -> dict:
        """Serializa a sessão para dicionário."""
        return {
            "session_id": self.session_id,
            "actions": [
                {
                    "action_type": a.action_type,
                    "target_ref": a.target_ref,
                    "value": a.value,
                    "timestamp": a.timestamp
                } for a in self.actions
            ],
            "snapshots": [
                {
                    "url": s.url,
                    "title": s.title,
                    "timestamp": s.timestamp,
                    "elements": [
                        {
                            "ref_id": e.ref_id,
                            "tag": e.tag,
                            "text": e.text,
                            "href": e.href,
                            "attrs": e.attrs
                        } for e in s.elements
                    ],
                    "raw_text": s.raw_text
                } for s in self.snapshots
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> BrowserSession:
        """Cria uma BrowserSession a partir de um dicionário."""
        from dataclasses import fields
        
        # Recreate actions
        actions = [
            BrowserAction(
                action_type=a["action_type"],
                target_ref=a["target_ref"],
                value=a["value"],
                timestamp=a["timestamp"]
            ) for a in data["actions"]
        ]
        
        # Recreate snapshots
        snapshots = []
        for snap_data in data["snapshots"]:
            elements = [
                ElementRef(
                    ref_id=e["ref_id"],
                    tag=e["tag"],
                    text=e["text"],
                    href=e["href"],
                    attrs=e["attrs"]
                ) for e in snap_data["elements"]
            ]
            snapshot = PageSnapshot(
                url=snap_data["url"],
                title=snap_data["title"],
                timestamp=snap_data["timestamp"],
                elements=elements,
                raw_text=snap_data["raw_text"]
            )
            snapshots.append(snapshot)
        
        session = cls(
            session_id=data["session_id"],
            actions=actions,
            snapshots=snapshots
        )
        
        return session