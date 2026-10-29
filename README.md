# Tableau de bord — Veille juridique biodiversité

Déploiement recommandé : GitHub Pages.

1. Créez un dépôt GitHub `veille-biodiversite`.
2. Copiez `index.html`, `update_dashboard.py`, le dossier `.github/` et `data/`.
3. Dans GitHub : Settings → Pages → Source : GitHub Actions.
4. Le workflow s’exécute chaque lundi à 07 h UTC ; il peut aussi être lancé manuellement.

L’automatisation consulte les pages Savoie de la préfecture (arrêtés environnementaux, enquêtes publiques, APPB, chasse et pêche, Lyon-Turin), détecte les publications liées à la biodiversité, ajoute les nouveautés au CSV et publie le tableau actualisé.

Mots-clés : biodiversité, espèce, biotope, zone humide, tourbière, cours d’eau, nappe, Natura 2000, loup, cormoran, ESOD, chasse, galliforme, tétras, bartavelle, lagopède, gélinotte, enquête publique, autorisation environnementale, loi sur l’eau, compensation, ERC, Lyon-Turin, TELT, JO 2030.
