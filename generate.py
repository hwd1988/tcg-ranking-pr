#!/usr/bin/env python3
"""Ranking de Pokémon TCG en Puerto Rico, basado en la API pública de Play! Pokémon.

Usa COMPETITORS_JSON (secreto de GitHub Actions) con una lista de jugadores verificados
por división, nombres y alias. No revela el listado privado en los registros.
"""
import argparse
import datetime as dt
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://api.play.pokemon.com/services/spar/leaderboards/'
DIVISIONS = ('juniors', 'seniors', 'masters')
PR_CODES = {'PR', 'PRI', 'PUERTO RICO'}
PAGE_SIZE = 300


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^\w\s]', '', text)
    return re.sub(r'\s+', ' ', text).strip().casefold()


def load_competitors(path):
    raw = os.environ.get('COMPETITORS_JSON')
    if raw:
        cfg = json.loads(raw)
    elif path.exists():
        cfg = json.loads(path.read_text(encoding='utf-8'))
    else:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError('Configuración de competidores inválida')
    lookup = {division: {} for division in DIVISIONS}
    entries = cfg.get('players', [])
    if not isinstance(entries, list):
        raise ValueError('players debe ser una lista')
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Cada jugador debe ser un objeto')
        division = str(entry.get('division', '')).lower().strip()
        if division not in DIVISIONS:
            raise ValueError('Cada jugador debe indicar juniors, seniors o masters')
        name = str(entry.get('name', '')).strip()
        if not name:
            raise ValueError('Jugador sin nombre')
        aliases = entry.get('aliases', [])
        if not isinstance(aliases, list):
            raise ValueError('aliases debe ser una lista')
        for variant in [name, *aliases]:
            key = normalize(variant)
            if not key:
                raise ValueError('Nombre o alias vacío')
            prior = lookup[division].get(key)
            if prior is not None and prior != name:
                raise ValueError('Un mismo alias corresponde a dos jugadores en la misma división')
            lookup[division][key] = name
    # Archivo anterior: nombres públicos verificados, sin división. Por seguridad,
    # no los asignamos a una división automáticamente.
    if cfg.get('verified_public_names') and not entries:
        raise ValueError('Migra verified_public_names a players con su división antes de publicar')
    return lookup


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={
                'Accept': 'application/json', 'User-Agent': 'PKMNPR-TCG-Leaderboard/1.1'
            })
            with urllib.request.urlopen(request, timeout=35) as response:
                return json.load(response)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_division(division, period, region, region_type):
    params = {
        'product': 'tcg', 'division': division,
        'region': region, 'region_type': region_type,
        'period': period, 'point_type': 'championship',
        'page_size': PAGE_SIZE, 'sort_by': 'ranking_order:asc'
    }
    rows = []
    page = 1
    while True:
        response = fetch(API + '?' + urllib.parse.urlencode({**params, 'page': page}))
        batch = response.get('results')
        if not isinstance(batch, list):
            raise ValueError('La API no devolvió results[]')
        rows.extend(batch)
        total = int(response.get('count', len(rows)))
        if not batch or len(rows) >= total:
            break
        if len(batch) < PAGE_SIZE:
            raise ValueError('Paginación incompleta: la API devolvió menos registros de lo esperado')
        page += 1
        time.sleep(0.3)
    return rows


def build_rankings(division, results, approved):
    found = []
    for player in results:
        display = str(player.get('display_name') or '').strip()
        country = str(player.get('player_country') or player.get('country') or '').strip().upper()
        canonical = approved.get(normalize(display))
        # Listado verificado por división es la fuente primaria, como en el enfoque
        # de Pocolip. También se acepta país explícitamente PR en la API.
        if not canonical and country not in PR_CODES:
            continue
        if not display:
            continue
        try:
            cp = int(player.get('primary_point_total', 0))
            regional = int(player.get('rank', 0))
        except (ValueError, TypeError):
            continue
        found.append({'name': canonical or display, 'cp': cp, 'region_rank': regional})
    # Nombres homónimos o múltiples alias de un mismo jugador son posibles:
    # si duplican nombres canónicos, evitar posiciones ambiguas en vez de adivinar.
    names = [normalize(row['name']) for row in found]
    if len(names) != len(set(names)):
        raise ValueError(f'{division}: coincidencias duplicadas; revisar alias del listado verificado')
    found.sort(key=lambda r: (-r['cp'], r['region_rank'], normalize(r['name'])))
    previous = None
    local_rank = 0
    for position, row in enumerate(found, 1):
        if row['cp'] != previous:
            local_rank = position
        row['rank'] = local_rank
        previous = row['cp']
    return found


def render(data):
    data_json = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = Path(__file__).with_name('template.html').read_text(encoding='utf-8')
    marker = '/*__RANKING_DATA__*/null'
    if marker not in template:
        raise ValueError('Falta marcador de datos en template.html')
    return template.replace(marker, data_json, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--period', default=os.environ.get('LEADERBOARD_PERIOD', ''))
    parser.add_argument('--region', default=os.environ.get('LEADERBOARD_REGION', 'NA'))
    parser.add_argument('--region-type', default=os.environ.get('LEADERBOARD_REGION_TYPE', 'zone'))
    parser.add_argument('--verified', type=Path, default=Path('verified_players.json'))
    parser.add_argument('--output', type=Path, default=Path('site/index.html'))
    args = parser.parse_args()
    if not args.period:
        parser.error('Falta LEADERBOARD_PERIOD')
    lookup = load_competitors(args.verified)
    groups = {}
    for division in DIVISIONS:
        source = fetch_division(division, args.period, args.region, args.region_type)
        groups[division] = build_rankings(division, source, lookup[division])
        print(f'{division}: consultados {len(source)}; Puerto Rico: {len(groups[division])}', flush=True)
    if not any(groups.values()):
        raise ValueError('No se verificó ningún jugador de Puerto Rico; no se reemplazará el ranking publicado')
    data = {
        'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'),
        'period': args.period, 'sample': False, 'divisions': groups
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(data), encoding='utf-8')
    print('Página generada correctamente:', args.output)


if __name__ == '__main__':
    main()
