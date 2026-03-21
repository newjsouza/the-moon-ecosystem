"""
Index existing Learning Room meeting logs into RAG collections.
Run once to populate RAG with existing room knowledge.
"""
import asyncio
import logging
from pathlib import Path
from core.rag import RAGEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOMS_BASE = Path("learning/workspaces/rooms")

async def index_all_rooms():
    rag = RAGEngine()
    results = []

    for room_dir in ROOMS_BASE.iterdir():
        if not room_dir.is_dir():
            continue

        room_name = room_dir.name
        log_file = room_dir / "meeting_log.md"

        if not log_file.exists():
            logger.warning(f"No meeting_log.md in room: {room_name}")
            continue

        content = log_file.read_text(encoding="utf-8")
        if not content.strip():
            logger.warning(f"Empty meeting log in room: {room_name}")
            continue

        metadata = {
            "title": f"Meeting Log — {room_name}",
            "topic": room_name,
            "source": f"room:{room_name}",
            "log_path": str(log_file),
        }

        result = await rag.ingest_room(room_name, content, metadata)
        if result.success:
            logger.info(f"Room '{room_name}': {result.data['chunks_ingested']} chunks indexed ✅")
        else:
            logger.error(f"Room '{room_name}': indexing failed — {result.error}")
        results.append((room_name, result.success))

    return results

if __name__ == "__main__":
    results = asyncio.run(index_all_rooms())
    print("\n=== Learning Rooms Indexing Summary ===")
    for room, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {room}")