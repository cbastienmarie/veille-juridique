#!/usr/bin/env python3
"""Convertit les réponses du formulaire de signalement en data/signalements.json.

Usage : python3 outils/extraire_signalements.py reponses.json [data/signalements.json]

reponses.json = liste des réponses telle que renvoyée par l'API Google Forms
(réponses de l'automatisation hebdomadaire). Chaque signalement est marqué
« à l'étude pour le groupe juridique ». Les tests techniques sont ignorés.
"""
import datetime as dt
import json
import sys
from pathlib import Path

FORM_ID = "1TJGpJ3Dzz2L3YtQChjRvK8u4QrhXgJGFXTVrBfkfzv0"
VIEW = "https://docs.google.com/forms/d/e/1FAIpQLSejE8yXHist2mBKFsIb7-d7S9dSmq9ij8s7ZPhp5IV7xcnANw/viewform"
# identifiants des questions du formulaire
Q = {"prenom": "557b7682", "nom": "3844882e", "coordonnees": "1238a545",
     "date_alerte": "3d6c808f", "titre": "554441c3", "communes": "30108fca",
     "lien": "0017ea2e", "description": "42aaf0a4"}
IGNORE = ("test de fonctionnement", "test technique")  # signalements de test


def val(ans, key):
    a = ans.get(Q[key]) or {}
    for v in a.get("textAnswers", {}).get("answers", []):
        if v.get("value"):
            return v["value"].strip()
    return ""


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/signalements.json")
    rep = json.loads(src.read_text(encoding="utf-8"))
    if isinstance(rep, dict):
        rep = rep.get("responses") or rep.get("result") or []
    out = []
    for r in rep:
        ans = r.get("answers", {})
        titre = val(ans, "titre")
        if not titre or any(t in (titre + val(ans, "description")).lower() for t in IGNORE):
            continue
        # Le site et le dépôt sont publics : ne pas y publier les coordonnées
        # complètes. Elles restent consultables dans les réponses du formulaire.
        nom = val(ans, "nom")
        out.append({
            "uid": r.get("responseId", ""),
            "prenom": val(ans, "prenom"), "nom": (nom[:1] + ".") if nom else "",
            "coordonnees": "transmises au groupe juridique",
            "date_alerte": val(ans, "date_alerte"),
            "titre": titre, "communes": val(ans, "communes"),
            "lien": val(ans, "lien"), "description": val(ans, "description"),
            "recu_le": (r.get("lastSubmittedTime") or r.get("createTime") or "")[:10],
            "statut": "À l'étude — groupe juridique",
            "formulaire": VIEW,
        })
    out.sort(key=lambda s: s["recu_le"], reverse=True)
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(json.dumps({
        "mise_a_jour": dt.datetime.now().isoformat(timespec="minutes"),
        "note": "Signalements envoyés via le formulaire du site, en attente d'étude par le groupe juridique.",
        "signalements": out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} signalement(s) enregistrés dans {dst}")


if __name__ == "__main__":
    main()
