# Ranking TCG Puerto Rico (proyecto independiente)

Generador autónomo sin dependencias externas: Play! Pokémon → filtrado **exclusivo PR** → ranking separado Junior/Senior/Master → página estática para GitHub Pages. **No incluye ni reutiliza el código de Pocolip**.

## Preparación
1. Crea un repositorio GitHub **tuyo** y sube estos archivos conservando sus rutas.
2. En `Settings > Pages`, selecciona **GitHub Actions**.
3. En `Settings > Secrets and variables > Actions > Variables`, crea `LEADERBOARD_PERIOD` con el identificador de la temporada vigente obtenido de la consulta oficial de Play! Pokémon. La API no ofrece un listado de temporadas; **nunca** uses un identificador antiguo sin verificarlo.
4. Ejecuta `Actions > Actualizar ranking TCG Puerto Rico > Run workflow`. Se actualizará todos los días a las 11:23 UTC, mientras las acciones programadas estén habilitadas.
5. Cuando se publique, inserta la URL resultante dentro de un iframe en la página WordPress. No se requiere Python en WordPress.

## Solo Puerto Rico
El filtro admite `player_country = PR`, `PRI` o `Puerto Rico`. Cuando `player_country` venga vacío, admite un nombre solamente si aparece **expresamente verificado** en `verified_players.json`. Si el país indica otro territorio, se excluye incluso si el nombre aparece en la lista. **La lista está vacía por defecto**: la web no inventará que alguien es puertorriqueño. Revisar nombres por división y privacidad, especialmente menores de edad, antes de incorporarlos a la lista.

Si la API no proporciona país en sus resultados, necesitarás una lista verificada o cambiar el método de obtención de datos. Sin ella, se mostrarán tablas vacías en lugar de identificar personas incorrectamente.

## Prueba local
`python generate.py --sample --output demo.html` genera una demo **ficticia y marcada**. Para datos reales: `LEADERBOARD_PERIOD=... python generate.py --output site/index.html`.

## Limitaciones
- API pública no documentada y susceptible de cambiar. Falla la actualización si cambia la estructura.
- No prueba que el país de residencia coincida con el país asignado al perfil competitivo.
- Depende de la información pública de Play! Pokémon y del período configurado.
- Antes de publicar confirma que `product=tcg`, las divisiones, la clasificación por país y los valores de puntos coincidan con la página oficial.
- El ranking local se ordena por Championship Points; no sustituye el rango oficial de Norteamérica.
- La última publicación correcta seguirá en GitHub Pages si un trabajo posterior falla; revisa el estado del workflow.
