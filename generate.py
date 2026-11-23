#!/usr/bin/env python3
"""Rankings TCG de Puerto Rico: API pública Play! Pokémon; sin dependencias externas."""
import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

API = 'https://api.play.pokemon.com/services/spar/leaderboards/'
DIVISIONS = ('juniors', 'seniors', 'masters')
PR_CODES = {'PR', 'PRI', 'PUERTO RICO'}
PAGE_SIZE = 300


def normalize(v):
    return str(v or '').strip().casefold()


def verified_names(path):
    if not path.exists():
        return set()
    obj = json.loads(path.read_text(encoding='utf-8'))
    return {normalize(s) for s in obj.get('verified_public_names', []) if normalize(s)}


def is_pr(row, approved):
    # Nunca asignar PR por pertenecer a NA/US. Los nombres verificados se usan
    # únicamente si el campo de país viene vacío; las contradicciones se excluyen.
    country = str(row.get('player_country') or row.get('country') or '').strip().upper()
    if country:
        return country in PR_CODES
    return normalize(row.get('display_name')) in approved


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'Accept':'application/json', 'User-Agent':'PKMNPR-TCG-Leaderboard/1.0'})
            with urllib.request.urlopen(req, timeout=35) as resp:
                return json.load(resp)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_division(division, period, region, region_type):
    params = {'product':'tcg','division':division,'region':region,
              'region_type':region_type,'period':period,'point_type':'championship',
              'page_size':PAGE_SIZE, 'sort_by':'ranking_order:asc'}
    rows=[]
    page=1
    while True:
        qs=urllib.parse.urlencode({**params,'page':page})
        body=fetch(API+'?'+qs)
        batch=body.get('results')
        if not isinstance(batch, list):
            raise ValueError('API no devolvió results[]')
        rows.extend(batch)
        count=int(body.get('count', len(rows)))
        if not batch or len(rows)>=count or len(batch)<PAGE_SIZE:
            break
        page+=1
        if page>100: raise ValueError('Límite de paginación excedido')
        time.sleep(.4)
    return rows


def render(data):
    escaped=json.dumps(data, ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=Path(__file__).with_name('template.html').read_text(encoding='utf-8')
    return template.replace('/*__RANKING_DATA__*/null', escaped)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--period', default=os.environ.get('LEADERBOARD_PERIOD', ''))
    p.add_argument('--region', default=os.environ.get('LEADERBOARD_REGION','NA'))
    p.add_argument('--region-type', default=os.environ.get('LEADERBOARD_REGION_TYPE','zone'))
    p.add_argument('--verified', type=Path, default=Path('verified_players.json'))
    p.add_argument('--output', type=Path, default=Path('site/index.html'))
    p.add_argument('--sample', action='store_true', help='Genera demo local claramente etiquetada, nunca usar para publicar')
    args=p.parse_args()
    if not args.period and not args.sample:
        p.error('Configura LEADERBOARD_PERIOD con el identificador de temporada confirmado en Play! Pokémon')
    known=verified_names(args.verified)
    groups={}
    for division in DIVISIONS:
        raw=([{'display_name':'Ejemplo (NO REAL)','player_country':'PR','rank':1,'primary_point_total':0,'secondary_point_total':0}] if args.sample else fetch_division(division,args.period,args.region,args.region_type))
        result=[]
        for player in raw:
            if not is_pr(player,known):continue
            name=str(player.get('display_name') or '').strip()
            if not name:continue
            cp=player.get('primary_point_total',0)
            try: cp=int(cp)
            except (ValueError,TypeError):continue
            try: regional=int(player.get('rank',0))
            except (ValueError,TypeError):regional=0
            result.append({'name':name,'cp':cp,'region_rank':regional})
        result.sort(key=lambda x:(-x['cp'], x['region_rank'], x['name'].casefold()))
        prior=None;local=0
        for i,row in enumerate(result,1):
            if row['cp']!=prior:local=i
            row['rank']=local;prior=row['cp']
        groups[division]=result
    data={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'),
          'period':args.period or 'DEMO', 'sample':args.sample, 'divisions':groups}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(render(data),encoding='utf-8')
    print('Página generada:',args.output,' | ', {x:len(y) for x,y in groups.items()})

if __name__=='__main__': main()
