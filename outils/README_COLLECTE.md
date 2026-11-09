# Collecte hebdomadaire

Le site de la préfecture bloque les téléchargements depuis les serveurs GitHub.
La tâche hebdomadaire Perplexity :
1. lance `python3 update_dashboard.py --hors-ligne CACHE` ;
2. collecte les adresses listées dans `CACHE/manquants.txt` (pages HTML et PDF des RAA), les dépose dans `CACHE/in/N.txt` (1re ligne = URL) ;
3. lance `python3 outils/importer_cache.py CACHE`, puis recommence jusqu'à ce qu'il n'y ait plus de manquants ;
4. pousse `data/` sur GitHub, ce qui republie le site.
