#!/usr/bin/env python3
"""Discover publicly country-tagged Puerto Rico TCG competitors from Play LATAM rosters.

This is a *candidate identity list*, not proof of participation in the current season.
The ranking generator obtains points and ranking only from the Play! Pokemon API.
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


def normalize(name):
    s = unicodedata.normalize('NFKD', name)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', s)).casefold().strip()


def full_name(name):
    tokens = name.strip().split()
    return len(tokens) >= 2 and all(len(part.strip('.')) >= 2 for part in tokens) and not any(part.endswith('.') for part in tokens)


def extract(html, default_division=None):
    soup = BeautifulSoup(html, 'html.parser')
    found = []
    for tr in soup.find_all('tr'):
        imgs = tr.find_all('img')
        if not any((im.get('alt') or '').strip().casefold() == 'puerto rico' for im in imgs):
            continue
        division = default_division
        if not division:
            heading = tr.find_previous(lambda t: t.name in ('h1', 'h2', 'h3', 'h4')
                                       and any(d[:-1] in t.get_text(' ', strip=True).casefold() for d in DIVISIONS))
            if heading:
                heading_text = heading.get_text(' ', strip=True).casefold()
                division = next((d for d in DIVISIONS if d[:-1] in heading_text), None)
        if division not in DIVISIONS:
            continue
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 2:
            continue
        text = cells[1].get_text(' ', strip=True)
        if ' - ' in text:
            nickname, canonical = text.rsplit(' - ', 1)
        else:
            canonical = text
            nickname = ''
        canonical = canonical.strip()
        nickname = nickname.strip()
        # Partial names of minors (e.g. "Amaia M.") cannot safely be matched
        # to the official leaderboard and are intentionally excluded.
        if not full_name(canonical):
            continue
        found.append((division, canonical, nickname))
    return found


def main():
    identities = {}
    success = []
    for label, url, division in SOURCES:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; PKMNPR-TCG/1.0)'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode('utf-8', 'replace')
            players = extract(html, division)
            if not players:
                raise ValueError('No se pudieron extraer registros identificados como Puerto Rico')
            for d, name, alias in players:
                identities.setdefault((d, normalize(name)), {'division': d, 'name': name, 'aliases': set(), 'sources': set()})
                row = identities[(d, normalize(name))]
                row['sources'].add(url)
                # Restrict aliases to distinctive IDs, not first names like "Alex".
                if alias and normalize(alias) != normalize(name) and len(normalize(alias)) >= 8 and ' ' not in alias:
                    row['aliases'].add(alias)
            success.append(label)
            print(f'{label}: {len(players)} PR con nombres completos', flush=True)
        except Exception as exc:
            print(f'AVISO: fuente {label} no disponible ({type(exc).__name__})', flush=True)
    if not success:
        raise RuntimeError('No fue posible verificar ninguna fuente de jugadores; se cancela publicación')
    # Prevent nickname collisions within a division.
    alias_owners = defaultdict(set)
    for entry in identities.values():
        for alias in entry['aliases']:
            alias_owners[(entry['division'], normalize(alias))].add(normalize(entry['name']))
    reserved_names = {(d, key) for d, key in identities}
    players = []
    for entry in identities.values():
        aliases = sorted(alias for alias in entry['aliases']
                         if len(alias_owners[(entry['division'], normalize(alias))]) == 1
                         and (entry['division'], normalize(alias)) not in reserved_names)
        players.append({'division': entry['division'], 'name': entry['name'], 'aliases': aliases})
    players.sort(key=lambda p: (DIVISIONS.index(p['division']), normalize(p['name'])))
    if len(players) < 5:
        raise RuntimeError('Extracción sospechosamente pequeña; no se publica')
    result = {'players': players}
    Path('verified_players.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    counts = {d: sum(p['division'] == d for p in players) for d in DIVISIONS}
    print('Jugadores identificados por división (no implica CP activos):', counts, flush=True)
    print('Fuente(s) usada(s):', ', '.join(success), flush=True)


if __name__ == '__main__':
    main()
