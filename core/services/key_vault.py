import os
import json
import asyncio
import sqlite3
import httpx
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv, set_key

@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_from_env()
    # Migrate old keys.json if exists
    json_path = os.path.join(PROJECT_ROOT, "config/keys.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                old_keys = json.load(f)
                # Ensure all fields are present for SQLite insertion
                for key in old_keys:
                    key.setdefault("docsUrl", "")
                    key.setdefault("baseUrl", "")
                    key.setdefault("rateLimit", "")
                    key.setdefault("notes", "")
                save_keys(old_keys)
            os.remove(json_path) # Move to DB and cleanup
            print("✅ migrated keys.json to SQLite")
        except Exception as e:
            print(f"Error migrating keys.json: {e}")
    yield

app = FastAPI(title="KeyVault - The Moon Bridge", lifespan=lifespan)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurações
PROJECT_ROOT = "/home/johnathan/Área de trabalho/The Moon"
KEY_VAULT_UI_PATH = os.path.join(PROJECT_ROOT, "Teste de APPs/KeyVault")
DB_PATH = os.path.join(PROJECT_ROOT, "config/keyvault.db")
OS_AREA_DESKTOP = "/home/johnathan/Área de trabalho"
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

class APIKey(BaseModel):
    id: Optional[str] = None
    name: str
    provider: str
    key: str
    category: str
    description: Optional[str] = ""
    docsUrl: Optional[str] = ""
    baseUrl: Optional[str] = ""
    type: str = "free"
    rateLimit: Optional[str] = ""
    notes: Optional[str] = ""

class Category(BaseModel):
    id: str
    name: str
    icon: str
    count: int = 0

class DiscoveryRequest(BaseModel):
    query: Optional[str] = None

DEFAULT_CATEGORIES = [
    {"id": "Geral", "name": "Geral", "icon": "LayoutGrid"},
    {"id": "Infraestrutura", "name": "Infraestrutura", "icon": "Cpu"},
    {"id": "Desenvolvimento", "name": "Desenvolvimento", "icon": "Terminal"},
    {"id": "Segurança", "name": "Segurança", "icon": "Shield"},
    {"id": "Social", "name": "Social", "icon": "Hash"},
    {"id": "Cloud", "name": "Cloud", "icon": "Cloud"},
    {"id": "AI", "name": "AI", "icon": "Brain"},
    {"id": "Database", "name": "Database", "icon": "Database"},
]

def init_db():
    """Initialize SQLite database if it doesn't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id TEXT PRIMARY KEY,
            name TEXT,
            provider TEXT,
            key TEXT,
            category TEXT,
            description TEXT,
            type TEXT,
            docsUrl TEXT,
            baseUrl TEXT,
            rateLimit TEXT,
            notes TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def load_keys() -> List[Dict]:
    """Load keys from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM keys')
    rows = cursor.fetchall()
    keys = [dict(row) for row in rows]
    conn.close()
    return keys

def save_keys(keys: List[Dict]):
    """Save keys to SQLite (Upsert)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for key_data in keys:
        cursor.execute('''
            INSERT OR REPLACE INTO keys (id, name, provider, key, category, description, type, docsUrl, baseUrl, rateLimit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (key_data.get('id'), key_data.get('name'), key_data.get('provider'), key_data.get('key'), 
              key_data.get('category'), key_data.get('description'), key_data.get('type'),
              key_data.get('docsUrl'), key_data.get('baseUrl'), key_data.get('rateLimit'), key_data.get('notes')))
    conn.commit()
    conn.close()

def sync_from_env():
    """Import keys from all .env files found in the project recursively."""
    keys = load_keys()
    existing_keys = {k['key'] for k in keys}
    
    # Categorization mapping
    category_map = {
        "GROQ": "AI",
        "GITHUB": "Desenvolvimento",
        "TELEGRAM": "Social",
        "GMAIL": "Social",
        "OPENCODE": "Infraestrutura",
        "CLAUDE": "AI",
        "ANTHROPIC": "AI",
        "OPENAI": "AI",
        "GOOGLE": "Cloud",
        "AWS": "Cloud",
        "DATABASE": "Database",
        "DB": "Database",
        "FOOTBALL": "Geral",
        "SUPABASE": "Infraestrutura",
        "POSTGRES": "Database",
        "REDIS": "Database"
    }

    # Find all .env files recursively
    env_files = []
    for root, _, files in os.walk(PROJECT_ROOT):
        # Skip node_modules and .venv
        if "node_modules" in root or ".venv" in root:
            continue
        for file in files:
            if file == ".env" or file.startswith(".env."):
                env_files.append(os.path.join(root, file))

    for env_path in env_files:
        load_dotenv(env_path, override=True)
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    var_name, var_value = line.split('=', 1)
                    var_name = var_name.strip()
                    var_value = var_value.strip().strip('"').strip("'")
                    
                    if not var_value or var_value == "your-supabase-anon-key" or var_value in existing_keys:
                        continue

                    # Determine category
                    category = "Geral"
                    for pattern, cat in category_map.items():
                        if pattern in var_name:
                            category = cat
                            break
                    
                    new_key = {
                        "id": str(len(keys) + 1),
                        "name": var_name.replace('_', ' ').title(),
                        "provider": var_name.split('_')[0].capitalize(),
                        "key": var_value,
                        "category": category,
                        "description": f"Importado de: {os.path.relpath(env_path, PROJECT_ROOT)}",
                        "type": "free",
                        "docsUrl": "",
                        "baseUrl": "",
                        "rateLimit": "",
                        "notes": ""
                    }
                    keys.append(new_key)
                    existing_keys.add(var_value)
    
    save_keys(keys)

@app.get("/api/keys")
async def get_keys():
    return load_keys()

@app.post("/api/keys")
async def create_key(key: APIKey):
    keys = load_keys()
    key_dict = key.dict()
    if not key_dict["id"]:
        key_dict["id"] = str(len(keys) + 1)
    keys.append(key_dict)
    save_keys(keys)
    return key_dict

@app.put("/api/keys/{key_id}")
async def update_key(key_id: str, updated_key: APIKey):
    keys = load_keys()
    for i, k in enumerate(keys):
        if k.get("id") == key_id:
            keys[i] = updated_key.dict()
            keys[i]["id"] = key_id
            save_keys(keys)
            return keys[i]
    raise HTTPException(status_code=404, detail="Key not found")

@app.delete("/api/keys/{key_id}")
async def delete_key(key_id: str):
    keys = load_keys()
    keys = [k for k in keys if k.get("id") != key_id]
    save_keys(keys)
    return {"status": "deleted"}

@app.get("/api/categories")
async def get_categories():
    keys = load_keys()
    categories = []
    for cat in DEFAULT_CATEGORIES:
        count = sum(1 for k in keys if k.get("category") == cat["id"])
        categories.append({**cat, "count": count})
    return categories

@app.get("/api/github/search")
async def search_github(q: str):
    import httpx
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/search/repositories?q={q}+topic:api",
            headers=headers
        )
        if response.status_code != 200:
            return {"items": []}
        
        data = response.json()
        items = []
        for item in data.get("items", [])[:10]:
            items.append({
                "id": str(item["id"]),
                "name": item["name"],
                "full_name": item["full_name"],
                "description": item["description"],
                "html_url": item["html_url"],
                "stargazers_count": item["stargazers_count"],
                "language": item["language"],
                "topics": item.get("topics", [])
            })
        return {"items": items}

@app.post("/api/keys/discover")
async def discover_keys(request: DiscoveryRequest):
    """Search for public API keys or free-tier providers."""
    import httpx
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    query = request.query
    q = query or "public+api+keys"
    
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    async with httpx.AsyncClient() as client:
        # Search GitHub for potential providers - broader query
        response = await client.get(
            f"https://api.github.com/search/repositories?q={q}+api",
            headers=headers
        )
        if response.status_code == 200:
            data = response.json()
            items = []
            for item in data.get("items", [])[:5]:
                items.append({
                    "id": str(item["id"]),
                    "name": item["name"],
                    "description": item["description"],
                    "provider": item["owner"]["login"],
                    "category": "Geral",
                    "type": "free",
                    "docsUrl": item["html_url"]
                })
            return {"status": "success", "discovered": items}
    return {"status": "error", "message": f"GitHub Search Failed: {response.text if 'response' in locals() else 'Connection Error'}"}

@app.post("/api/keys/verify/{key_id}")
async def verify_key(key_id: str):
    keys = load_keys()
    target = next((k for k in keys if k.get("id") == key_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Key not found")
    
    import httpx
    provider = target.get("provider", "").lower()
    key = target.get("key", "")
    
    try:
        async with httpx.AsyncClient() as client:
            if "groq" in provider:
                res = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if res.status_code == 200:
                    return {"status": "valid", "message": "Groq Key is working!"}
            elif "github" in provider:
                res = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {key}"}
                )
                if res.status_code == 200:
                    return {"status": "valid", "message": "GitHub Token is working!"}
            
            # Fallback for unknown providers
            return {"status": "unknown", "message": f"Verification not implemented for {provider}"}
    except Exception as e:
        return {"status": "invalid", "message": str(e)}

# Serve static files from KeyVault UI
if os.path.exists(KEY_VAULT_UI_PATH):
    app.mount("/", StaticFiles(directory=KEY_VAULT_UI_PATH, html=True), name="static")

def run_service(port=8080):
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    run_service()
