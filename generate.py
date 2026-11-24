#!/usr/bin/env python3
"""Ranking TCG PR, nombres identificados en fuentes públicas y puntos de Play! Pokémon."""
import argparse
import datetime as dt
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

API = 'https://api.play.pokemon.com/services/spar/leaderboards/'
DIVISIONS = ('juniors', 'seniors', 'masters')
PR_CODES = {'PR', 'PRI', 'PUERTO RICO'}
PAGE_SIZE = 300

def normalize(value):
    s = unicodedata.normalize('NFKD', str(value or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', s)).casefold().strip()

def load_competitors(path):
    raw = os.environ.get('COMPETITORS_JSON')
    cfg = json.loads(raw) if raw else json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(cfg,dict) or not isinstance(cfg.get('players',[]),list):
        raise ValueError('Lista de competidores incorrecta')
    lookup = {d:{} for d in DIVISIONS}
    for p in cfg.get('players',[]):
        if not isinstance(p,dict):
            raise ValueError('Registro de jugador incorrecto')
        div,name = str(p.get('division','')).strip().lower(),str(p.get('name','')).strip()
        if div not in DIVISIONS or not name or not isinstance(p.get('aliases',[]),list):
            raise ValueError('Jugador sin división, nombre o lista válida de aliases')
        for item in [name,*p.get('aliases',[])]:
            key=normalize(item)
            if not key:
                raise ValueError('Nombre vacío')
            old=lookup[div].get(key)
            if old and old != name:
                raise ValueError('Conflicto de alias entre jugadores')
            lookup[div][key]=name
    return lookup

def fetch(url,retries=3):
    for i in range(retries):
        try:
            req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'PKMNPR-TCG-Leaderboard/1.2'})
            with urllib.request.urlopen(req,timeout=35) as res:
                return json.load(res)
        except Exception:
            if i==retries-1: raise
            time.sleep(2*(i+1))

def fetch_division(division,period,region,region_type):
    params={'product':'tcg','division':division,'region':region,'region_type':region_type,
            'period':period,'point_type':'championship','page_size':PAGE_SIZE,'sort_by':'ranking_order:asc'}
    rows=[]; page=1
    while True:
        doc=fetch(API+'?'+urllib.parse.urlencode({**params,'page':page}))
        batch=doc.get('results')
        if not isinstance(batch,list):
            raise ValueError('API no devolvió results[]')
        rows.extend(batch)
        total=int(doc.get('count',len(rows)))
        if not batch or len(rows)>=total: break
        if len(batch)<PAGE_SIZE: raise ValueError('Paginación incompleta')
        page+=1
        time.sleep(.3)
    return rows

def build_rankings(division,results,approved):
    by_name=defaultdict(list)
    for player in results:
        display=str(player.get('display_name') or '').strip()
        if not display:continue
        country=str(player.get('player_country') or player.get('country') or '').strip().upper()
        canonical=approved.get(normalize(display))
        if not canonical and country not in PR_CODES: continue
        try:
            cp=int(player.get('primary_point_total',0))
            rank=int(player.get('rank',0))
        except (ValueError,TypeError):continue
        if rank<=0:continue
        name=canonical or display
        by_name[normalize(name)].append({'name':name,'cp':cp,'region_rank':rank,'display':display})
    found=[]; ambiguous=0; identical=0
    for entries in by_name.values():
        # Se eliminan registros idénticos de la API; si hay varios puntajes o
        # posiciones diferentes para el mismo nombre, se excluye ese nombre.
        distinct={(r['cp'],r['region_rank']) for r in entries}
        if len(distinct)!=1:
            ambiguous+=1
            continue
        if len(entries)>1:identical+=len(entries)-1
        row=entries[0]
        found.append({'name':row['name'],'cp':row['cp'],'region_rank':row['region_rank']})
    if ambiguous or identical:
        print(f'{division}: {identical} registros repetidos idénticos y {ambiguous} nombres ambiguos excluidos',flush=True)
    found.sort(key=lambda r:(-r['cp'],r['region_rank'],normalize(r['name'])))
    prev=None; local=0
    for i,row in enumerate(found,1):
        if row['cp']!=prev:local=i
        row['rank']=local;prev=row['cp']
    return found

def render(data):
    payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=Path(__file__).with_name('template.html').read_text(encoding='utf-8')
    marker='/*__RANKING_DATA__*/null'
    if marker not in template:raise ValueError('Marcador de datos ausente en template.html')
    return template.replace(marker,payload,1)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--period',default=os.environ.get('LEADERBOARD_PERIOD',''))
    p.add_argument('--region',default=os.environ.get('LEADERBOARD_REGION','NA'))
    p.add_argument('--region-type',default=os.environ.get('LEADERBOARD_REGION_TYPE','zone'))
    p.add_argument('--verified',type=Path,default=Path('verified_players.json'))
    p.add_argument('--output',type=Path,default=Path('site/index.html'))
    a=p.parse_args()
    if not a.period:p.error('Falta LEADERBOARD_PERIOD')
    approved=load_competitors(a.verified)
    groups={}
    for division in DIVISIONS:
        source=fetch_division(division,a.period,a.region,a.region_type)
        groups[division]=build_rankings(division,source,approved[division])
        print(f'{division}: consultados {len(source)}; Puerto Rico {len(groups[division])}',flush=True)
    if not any(groups.values()):
        raise ValueError('Ningún jugador verificado coincide con la clasificación actual; se conserva la página anterior')
    data={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'),
          'period':a.period,'sample':False,'divisions':groups}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(render(data),encoding='utf-8')
    print('Página generada:',a.output)

if __name__=='__main__':main()
