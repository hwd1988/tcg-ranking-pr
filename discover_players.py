#!/usr/bin/env python3
"""Construye candidatos TCG Puerto Rico desde listas públicas con país explícito.
No significa que todos tengan puntos en la temporada actual.
"""
import json
import re
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from bs4 import BeautifulSoup

SOURCES = [
    ('San Juan 2026', 'https://pairings.playlatam.net/roster/SJU26-TCG', None),
    ('Puerto Rico 2025', 'https://pairings.playlatam.net/roster/PR25-TCG', None),
    ('Lima 2026 Masters', 'https://pairings.playlatam.net/roster/LIM26-TCG-MA', 'masters'),
]
DIVISIONS = ('juniors', 'seniors', 'masters')
DIVISION_HEADING = re.compile(r'^\s*(Junior|Senior|Master)s?\s+Division\s*$', re.I)

def normalize(name):
    s = unicodedata.normalize('NFKD', str(name))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', s)).casefold().strip()

def full_name(name):
    tokens = name.strip().split()
    return len(tokens) >= 2 and all(len(part.strip('.')) >= 2 for part in tokens) and not any(part.endswith('.') for part in tokens)

def extract(html, default_division=None):
    soup = BeautifulSoup(html, 'html.parser')
    found = []
    for tr in soup.find_all('tr'):
        # El marcador de división debe ser el texto de encabezado más cercano,
        # no el primer h1-h4: en Play LATAM los encabezados varían de nivel.
        division = default_division
        if not division:
            heading = tr.find_previous(string=lambda x: bool(x and DIVISION_HEADING.fullmatch(x.strip())))
            if heading:
                term = DIVISION_HEADING.fullmatch(str(heading).strip()).group(1).lower()
                division = {'junior':'juniors','senior':'seniors','master':'masters'}[term]
        if division not in DIVISIONS:
            continue
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 2:
            continue
        if not any((im.get('alt') or '').strip().casefold() == 'puerto rico' for im in cells[1].find_all('img')):
            continue
        text = cells[1].get_text(' ', strip=True)
        if ' - ' in text:
            nickname, canonical = text.rsplit(' - ', 1)
        else:
            nickname, canonical = '', text
        canonical, nickname = canonical.strip(), nickname.strip()
        # No atribuir nombres abreviados de menores a personas reales.
        if not full_name(canonical):
            continue
        found.append((division, canonical, nickname))
    return found

def main():
    identities = {}
    success = []
    for label, url, division in SOURCES:
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; PKMNPR-TCG/1.1)'})
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode('utf-8', 'replace')
            players = extract(html, division)
            if not players:
                raise ValueError('No hay registros PR con nombre completo')
            for d, name, alias in players:
                key = (d, normalize(name))
                entry = identities.setdefault(key, {'division':d, 'name':name, 'aliases':set()})
                if alias and normalize(alias) != normalize(name) and len(normalize(alias)) >= 8 and ' ' not in alias:
                    entry['aliases'].add(alias)
            success.append(label)
            print(f'{label}: {len(players)} registros de PR con nombre completo', flush=True)
        except Exception as exc:
            print(f'AVISO: fuente {label} no disponible ({type(exc).__name__})', flush=True)
    if not success:
        raise RuntimeError('Ninguna fuente pudo verificarse; no se publica')
    aliases = defaultdict(set)
    for key, entry in identities.items():
        for alias in entry['aliases']:
            aliases[(entry['division'],normalize(alias))].add(key)
    players = []
    for key, entry in identities.items():
        good = sorted(alias for alias in entry['aliases']
                      if len(aliases[(entry['division'],normalize(alias))]) == 1
                      and (entry['division'],normalize(alias)) not in identities)
        players.append({'division':entry['division'], 'name':entry['name'], 'aliases':good})
    players.sort(key=lambda x: (DIVISIONS.index(x['division']),normalize(x['name'])))
    if len(players) < 5:
        raise RuntimeError('Lista sospechosamente pequeña; no se publica')
    Path('verified_players.json').write_text(json.dumps({'players':players},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Identificaciones por división:', {d:sum(x['division']==d for x in players) for d in DIVISIONS}, flush=True)
    print('Fuentes verificadas:',', '.join(success),flush=True)

if __name__ == '__main__':
    main()
