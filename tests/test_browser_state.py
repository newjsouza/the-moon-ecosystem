import time
import pytest
from core.browser_state import ElementRef, PageSnapshot, BrowserAction, BrowserSession


def test_element_ref_creation():
    """Testa criação de ElementRef com campos obrigatórios e defaults."""
    element = ElementRef(
        ref_id="btn_123",
        tag="button",
        text="Clique aqui",
        href="https://example.com",
        attrs={"class": "primary-btn", "id": "submit-btn"}
    )
    
    assert element.ref_id == "btn_123"
    assert element.tag == "button"
    assert element.text == "Clique aqui"
    assert element.href == "https://example.com"
    assert element.attrs == {"class": "primary-btn", "id": "submit-btn"}


def test_page_snapshot_creation():
    """Testa criação de PageSnapshot com url, title, timestamp, elements."""
    elements = [
        ElementRef(
            ref_id="link_1",
            tag="a",
            text="Home",
            href="/home"
        ),
        ElementRef(
            ref_id="btn_1",
            tag="button",
            text="Submit",
            attrs={"type": "submit"}
        )
    ]
    
    snapshot = PageSnapshot(
        url="https://example.com",
        title="Example Site",
        timestamp=time.time(),
        elements=elements,
        raw_text="Welcome to example site"
    )
    
    assert snapshot.url == "https://example.com"
    assert snapshot.title == "Example Site"
    assert len(snapshot.elements) == 2
    assert snapshot.raw_text == "Welcome to example site"


def test_browser_action_creation():
    """Testa criação de BrowserAction com action_type, target_ref, value."""
    action = BrowserAction(
        action_type="click",
        target_ref="btn_123",
        value="submit",
        timestamp=time.time()
    )
    
    assert action.action_type == "click"
    assert action.target_ref == "btn_123"
    assert action.value == "submit"
    assert isinstance(action.timestamp, float)


def test_browser_session_add_action():
    """Testa adicionar e recuperar ação na sessão."""
    session = BrowserSession(
        session_id="test_session",
        actions=[],
        snapshots=[]
    )
    
    action = BrowserAction(
        action_type="navigate",
        target_ref=None,
        value="https://example.com",
        timestamp=time.time()
    )
    
    session.add_action(action)
    
    assert len(session.actions) == 1
    assert session.actions[0].action_type == "navigate"
    assert session.actions[0].value == "https://example.com"


def test_browser_session_add_snapshot():
    """Testa adicionar e recuperar snapshot na sessão."""
    session = BrowserSession(
        session_id="test_session",
        actions=[],
        snapshots=[]
    )
    
    snapshot = PageSnapshot(
        url="https://example.com",
        title="Example",
        timestamp=time.time(),
        elements=[],
        raw_text=""
    )
    
    session.add_snapshot(snapshot)
    
    assert len(session.snapshots) == 1
    assert session.snapshots[0].url == "https://example.com"
    assert session.snapshots[0].title == "Example"


def test_browser_session_last_snapshot():
    """Testa retorno do último snapshot."""
    session = BrowserSession(
        session_id="test_session",
        actions=[],
        snapshots=[]
    )
    
    # Test with no snapshots
    assert session.last_snapshot() is None
    
    # Add first snapshot
    snapshot1 = PageSnapshot(
        url="https://example1.com",
        title="Example 1",
        timestamp=time.time() - 10,
        elements=[],
        raw_text=""
    )
    
    # Add second snapshot
    snapshot2 = PageSnapshot(
        url="https://example2.com",
        title="Example 2",
        timestamp=time.time(),
        elements=[],
        raw_text=""
    )
    
    session.add_snapshot(snapshot1)
    session.add_snapshot(snapshot2)
    
    last = session.last_snapshot()
    assert last.url == "https://example2.com"
    assert last.title == "Example 2"


def test_browser_session_replay_log():
    """Testa log com ações e snapshots ordenados por timestamp."""
    session = BrowserSession(
        session_id="test_session",
        actions=[],
        snapshots=[]
    )
    
    # Create events with different timestamps
    ts1 = time.time() - 10
    ts2 = time.time() - 5
    ts3 = time.time()
    
    # Add action at ts1
    session.add_action(BrowserAction(
        action_type="navigate",
        target_ref=None,
        value="https://example.com",
        timestamp=ts1
    ))
    
    # Add snapshot at ts2
    session.add_snapshot(PageSnapshot(
        url="https://example.com",
        title="Example",
        timestamp=ts2,
        elements=[],
        raw_text="Some content"
    ))
    
    # Add action at ts3
    session.add_action(BrowserAction(
        action_type="click",
        target_ref="btn_1",
        value=None,
        timestamp=ts3
    ))
    
    log = session.replay_log()
    
    # Should have 3 entries sorted by timestamp
    assert len(log) == 3
    assert log[0]["timestamp"] <= log[1]["timestamp"] <= log[2]["timestamp"]
    
    # Check types in order
    assert log[0]["type"] == "action"
    assert log[1]["type"] == "snapshot"
    assert log[2]["type"] == "action"
    
    # Check content
    assert log[0]["data"]["action_type"] == "navigate"
    assert log[1]["data"]["url"] == "https://example.com"
    assert log[2]["data"]["action_type"] == "click"


def test_browser_session_to_dict():
    """Testa serialização da sessão."""
    session = BrowserSession(
        session_id="test_session",
        actions=[
            BrowserAction(
                action_type="click",
                target_ref="btn_1",
                value=None,
                timestamp=1234567890.0
            )
        ],
        snapshots=[
            PageSnapshot(
                url="https://example.com",
                title="Example",
                timestamp=1234567891.0,
                elements=[
                    ElementRef(
                        ref_id="el_1",
                        tag="div",
                        text="Content",
                        attrs={"class": "content"}
                    )
                ],
                raw_text="Raw content"
            )
        ]
    )
    
    data = session.to_dict()
    
    assert data["session_id"] == "test_session"
    assert len(data["actions"]) == 1
    assert len(data["snapshots"]) == 1
    assert data["actions"][0]["action_type"] == "click"
    assert data["snapshots"][0]["url"] == "https://example.com"
    assert data["snapshots"][0]["elements"][0]["ref_id"] == "el_1"


def test_browser_session_from_dict():
    """Testa desserialização da sessão (round-trip)."""
    original_data = {
        "session_id": "test_session",
        "actions": [
            {
                "action_type": "fill",
                "target_ref": "input_1",
                "value": "test_value",
                "timestamp": 1234567890.0
            }
        ],
        "snapshots": [
            {
                "url": "https://example.com",
                "title": "Example",
                "timestamp": 1234567891.0,
                "elements": [
                    {
                        "ref_id": "el_1",
                        "tag": "input",
                        "text": "",
                        "href": None,
                        "attrs": {"name": "username"}
                    }
                ],
                "raw_text": "Login page"
            }
        ]
    }
    
    session = BrowserSession.from_dict(original_data)
    
    assert session.session_id == "test_session"
    assert len(session.actions) == 1
    assert len(session.snapshots) == 1
    assert session.actions[0].action_type == "fill"
    assert session.actions[0].target_ref == "input_1"
    assert session.snapshots[0].url == "https://example.com"
    assert session.snapshots[0].elements[0].ref_id == "el_1"
    assert session.snapshots[0].elements[0].tag == "input"


def test_browser_pilot_start_session():
    """Testa _start_session() cria BrowserSession."""
    from agents.browser_pilot import BrowserPilot
    
    pilot = BrowserPilot()
    session = pilot._start_session("custom_id")
    
    assert session.session_id == "custom_id"
    assert isinstance(session, BrowserSession)
    assert pilot._browser_session is session


def test_browser_pilot_record_action():
    """Testa _record_action() adiciona à sessão."""
    from agents.browser_pilot import BrowserPilot
    
    pilot = BrowserPilot()
    pilot._start_session("test_rec")
    
    pilot._record_action("click", "btn_1", "submit")
    
    replay_log = pilot.get_replay_log()
    assert len(replay_log) == 1
    assert replay_log[0]["type"] == "action"
    assert replay_log[0]["data"]["action_type"] == "click"
    assert replay_log[0]["data"]["target_ref"] == "btn_1"
    assert replay_log[0]["data"]["value"] == "submit"


def test_browser_pilot_get_replay_log():
    """Testa get_replay_log() retorna lista."""
    from agents.browser_pilot import BrowserPilot
    
    pilot = BrowserPilot()
    pilot._start_session("test_replay")
    
    # Initially empty
    assert pilot.get_replay_log() == []
    
    # Add some actions
    pilot._record_action("navigate", None, "https://example.com")
    pilot._record_action("click", "btn_1", None)
    
    log = pilot.get_replay_log()
    assert len(log) == 2
    assert all(entry["type"] == "action" for entry in log)