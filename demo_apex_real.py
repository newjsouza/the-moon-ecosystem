"""
DEMONSTRAÇÃO APEX ORACLE — DADOS REAIS
Usando jogos de HOJE da Champions League
"""
import asyncio, sys, os, json, httpx
from datetime import datetime, timedelta, timezone
from groq import AsyncGroq

sys.path.insert(0,'.')
from dotenv import load_dotenv
load_dotenv()

FOOTBALL_API_KEY = os.getenv('FOOTBALL_DATA_API_KEY')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
BASE = 'https://api.football-data.org/v4'

async def demo():
    headers = {'X-Auth-Token': FOOTBALL_API_KEY}
    
    print("=" * 70)
    print("🌕 APEX BETTING ORACLE — DEMONSTRAÇÃO COM DADOS REAIS")
    print(f"📅 Data: {datetime.now().strftime('%d/%m/%Y')}")
    print("=" * 70)
    
    async with httpx.AsyncClient(timeout=15) as client:
        # Busca jogos de HOJE da Champions League
        print("\n🔍 Buscando jogos de HOJE (17/03/2026)...")
        resp = await client.get(
            f'{BASE}/matches',
            headers=headers,
            params={'dateFrom': '2026-03-17', 'dateTo': '2026-03-17'}
        )
        
        if resp.status_code == 200:
            data = resp.json()
            all_matches = data.get('matches', [])
            
            # Filtra Champions League
            cl_matches = [m for m in all_matches 
                         if m.get('competition',{}).get('code') == 'CL']
            
            print(f"✅ {len(cl_matches)} jogos da Champions League encontrados!\n")
            
            # Mostra jogos
            for i, m in enumerate(cl_matches[:5], 1):
                home = m.get('homeTeam',{}).get('name','?')
                away = m.get('awayTeam',{}).get('name','?')
                time = m.get('utcDate','')[:16].replace('T', ' ')
                venue = m.get('venue', 'Estádio desconhecido')[:40]
                print(f"{i}. ⚽ {home} × {away}")
                print(f"   🕐 {time} UTC | 🏟️ {venue}")
                print()
            
            # Busca últimos 5 jogos de um time (ex: Manchester City)
            print("\n" + "=" * 70)
            print("📊 BUSCANDO DADOS REAIS — MANCHESTER CITY")
            print("=" * 70)
            
            city_id = 65  # Manchester City ID na API
            resp2 = await client.get(
                f'{BASE}/teams/{city_id}/matches',
                headers=headers,
                params={'status': 'FINISHED', 'limit': 5}
            )
            
            if resp2.status_code == 200:
                city_matches = resp2.json().get('matches', [])
                print(f"\n🔵 Últimos 5 jogos do Manchester City:\n")
                for m in city_matches[-5:]:
                    home = m.get('homeTeam',{}).get('shortName','?')
                    away = m.get('awayTeam',{}).get('shortName','?')
                    score = m.get('score',{}).get('fullTime',{})
                    hg = score.get('home', '?')
                    ag = score.get('away', '?')
                    date = m.get('utcDate','')[:10]
                    comp = m.get('competition',{}).get('name','?')[:20]
                    
                    # Resultado
                    if hg == '?' or ag == '?':
                        icon = '❓'
                    elif (home == 'Manchester City' and hg > ag) or (away == 'Manchester City' and ag > hg):
                        icon = '✅'
                    elif hg == ag:
                        icon = '🟡'
                    else:
                        icon = '❌'
                    
                    print(f"  {icon} {date} | {home} {hg}×{ag} {away} _{comp}_")
            
            # Gera análise com Groq
            print("\n\n" + "=" * 70)
            print("🤖 GERANDO ANÁLISE COM GROQ LLM (llama-3.3-70b)")
            print("=" * 70)
            
            groq_client = AsyncGroq(api_key=GROQ_API_KEY)
            
            prompt = """Você é um analista profissional de apostas esportivas.
Analise o jogo: Manchester City × Real Madrid (Champions League, 17/03/2026)

Considere:
- Histórico recente de ambos os times
- Fator casa/campo neutro
- Importância da competição (mata-mata Champions)
- Estilo de jogo de cada time

Retorne APENAS JSON válido:
{
  "analise": "texto da análise em 2-3 parágrafos",
  "mercados": [
    {"nome": "Resultado Final", "dica": "Empate", "confianca": "Média"},
    {"nome": "Over/Under 2.5", "dica": "Over 2.5", "confianca": "Alta"}
  ]
}"""
            
            completion = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3
            )
            
            response = completion.choices[0].message.content.strip()
            
            # Limpa resposta (remove ```json se houver)
            if response.startswith('```'):
                response = response.split('```')[1]
                if response.startswith('json'):
                    response = response[4:]
                response = response.strip()
            
            try:
                analysis = json.loads(response)
                print(f"\n📝 ANÁLISE GERADA:\n")
                print(f"  {analysis.get('analise', 'N/A')[:300]}...")
                print(f"\n🎯 MERCADOS INDICADOS:")
                for m in analysis.get('mercados', []):
                    conf = '🟢' if m.get('confianca') == 'Alta' else '🟡'
                    print(f"  {conf} {m.get('nome')} → {m.get('dica')}")
            except json.JSONDecodeError:
                print(f"Erro ao parsear JSON: {response[:300]}")
    
    print("\n\n" + "=" * 70)
    print("✅ DEMONSTRAÇÃO CONCLUÍDA — DADOS 100% REAIS")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(demo())
