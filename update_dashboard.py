#!/usr/bin/env python3
"""Veille juridique biodiversité - moteur d'alertes hebdomadaire (Savoie).

1. Lit le référentiel éditorial (data/enjeux.json) et les dossiers suivis (data/dossiers.csv).
2. Ouvre les nouveaux recueils des actes administratifs (RAA) de la préfecture de la Savoie,
   découpe chaque recueil en actes, et note chaque acte au regard des enjeux.
3. Lit aussi les pages « enquêtes publiques » et « consultations du public ».
4. Pour chaque acte pertinent : enjeux détectés, dossiers liés, communes, action à envisager,
   date butoir (clôture d'enquête/consultation ou fin du délai de recours).
5. Écrit data/alertes.json (onglet Alertes) sans jamais effacer les alertes déjà traitées.
"""
import datetime as dt
import io
import json
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE = "https://www.savoie.gouv.fr"
RAA_INDEX = BASE + "/Publications/Recueils-hebdomadaires-et-speciaux-des-actes-administratifs"
ENV = BASE + "/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement"
EP = BASE + "/Publications/Enquetes-publiques"
EXTRA_PAGES = {
    "Enquête publique - environnement": EP + "/Environnement",
    "Enquête publique - aménagement": EP + "/Amenagement-du-territoire",
    "Enquête publique - DUP": EP + "/Declaration-d-utilite-publique",
    "Enquête publique - communes": EP + "/Enquetes-publiques-initiees-par-les-communes",
    "Enquête publique - agriculture": EP + "/Agriculture",
    "Enquête publique - autres": EP + "/Autres-enquetes",
    "Participation du public": ENV + "/Participation-du-public-a-l-elaboration-des-decisions",
    "ICPE": ENV + "/Installations-classees-pour-la-protection-de-l-environnemen",
    "Loi sur l'eau": ENV + "/Eau-foret-biodiversite/Arretes-divers-et-declarations-au-titre-de-la-loi-sur-l-eau",
    "Chasse et pêche": ENV + "/Chasse-et-peche",
    "Milieux et espèces protégés": ENV + "/Milieux-et-especes-proteges",
    "Circulation milieux naturels": ENV + "/Circulation-dans-les-milieux-naturels",
}
DATA = Path("data")
ENJEUX_F = DATA / "enjeux.json"
DOSSIERS_F = DATA / "dossiers.csv"
ALERTES_F = DATA / "alertes.json"
ETAT_F = DATA / "etat_veille.json"
TODAY = dt.date.today()
START = time.time()
BUDGET_S = 35 * 60      # au-delà, on sauvegarde et on reprend la semaine suivante
MAX_EXTRA_LINKS = 150
FIRST_RUN_RAA = 30       # nombre de recueils analysés à la première exécution
MAX_RAA_PER_RUN = 40
HEADERS = {"User-Agent": "Mozilla/5.0 (veille-juridique-biodiversite; contact via GitHub)"}

MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
          "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}


def norm(s):
    s = unicodedata.normalize("NFD", s or "").lower().replace("’", "'")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def get(url, binary=False, tries=2):
    url = urllib.parse.quote(url, safe=":/?=&%#")
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=(15, 60))
            time.sleep(1.5)  # courtoisie envers le serveur de la préfecture
            if r.status_code == 200 and r.content:
                return r.content if binary else r.text
            print(f"  HTTP {r.status_code} {url}")
        except Exception as e:  # noqa: BLE001
            print(f"  erreur {e} {url}")
        time.sleep(4)
    return None


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------- dates
DATE_RE = re.compile(r"(\d{1,2})(?:er)?\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+(20\d\d)", re.I)
NUM_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b")


def to_date(m):
    try:
        return dt.date(int(m.group(3)), MONTHS[norm(m.group(2))], int(m.group(1)))
    except Exception:  # noqa: BLE001
        return None


def find_period(text):
    """Cherche une période d'enquête / consultation : 'du X au Y', 'jusqu'au Y'."""
    t = text.replace("\n", " ")
    d = r"(\d{1,2}(?:er)?\s+\w+\s+20\d\d|\d{1,2}/\d{1,2}/20\d\d)"
    m = re.search(r"du\s+(?:\w+\s+)?" + d + r".{0,60}?(?:au|jusqu'au|jusqu’au)\s+(?:\w+\s+)?" + d, t, re.I)
    start = end = None
    if m:
        start, end = parse_any(m.group(1)), parse_any(m.group(2))
    else:
        m = re.search(r"(?:jusqu'au|jusqu’au|au plus tard le|clôtur\w+ le|close le)\s+(?:\w+\s+)?" + d, t, re.I)
        if m:
            end = parse_any(m.group(1))
    return start, end


def parse_any(s):
    m = DATE_RE.search(s)
    if m:
        return to_date(m)
    m = NUM_DATE_RE.search(s)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- référentiels
def load_enjeux():
    e = load_json(ENJEUX_F, None)
    if not e:
        sys.exit("data/enjeux.json introuvable ou illisible")
    for en in e["enjeux"]:
        en["_kw"] = [(k, norm(k)) for k in en["mots_cles"]]
    e["_excl"] = [norm(x) for x in e.get("exclusions", [])]
    return e


def load_dossiers():
    import csv
    if not DOSSIERS_F.exists():
        return []
    rows = list(csv.DictReader(DOSSIERS_F.open(encoding="utf-8")))
    stop = {"arrete", "autorisation", "savoie", "projet", "enquete", "publique", "rapport", "commissaire",
            "enqueteur", "national", "region", "regional", "suivi", "entretien", "amenagement", "creation",
            "extension", "marais", "lac", "tourbiere", "ruisseau", "zones", "humides", "appb", "plan"}
    for r in rows:
        words = re.findall(r"[a-z0-9'-]{5,}", norm(r.get("Objet", "")))
        r["_terms"] = [w for w in words if w not in stop]
        r["_communes"] = [norm(c.strip()) for c in re.split(r",|;", r.get("Territoire / communes", "")) if len(c.strip()) > 3]
    return rows


def load_communes():
    txt = get("https://geo.api.gouv.fr/departements/73/communes?fields=nom")
    try:
        names = [c["nom"] for c in json.loads(txt)]
    except Exception:  # noqa: BLE001
        names = []
    # communes longues d'abord pour éviter les faux positifs
    return sorted({n for n in names if len(n) > 3}, key=len, reverse=True)


# ---------------------------------------------------------------- analyse d'un acte
def contains(text_n, kw_n):
    if len(kw_n) <= 5:  # sigles courts : mot entier
        return re.search(r"\b" + re.escape(kw_n) + r"\b", text_n) is not None
    return kw_n in text_n


def score_acte(title, body, enjeux):
    tn, bn = norm(title), norm(body)
    if any(x in tn for x in enjeux["_excl"]):
        return 0, [], []
    score, hits, kws = 0, [], set()
    for en in enjeux["enjeux"]:
        s = 0
        for k, kn in en["_kw"]:
            if contains(tn, kn):
                s += 3
                kws.add(k)
            elif contains(bn, kn):
                s += 1
                kws.add(k)
        if s:
            bonus = 2 if en["priorite"] == "Très élevée" else 0
            hits.append({"id": en["id"], "label": en["label"], "score": s + bonus})
            score += s + bonus
    hits.sort(key=lambda h: -h["score"])
    return score, hits, sorted(kws)


def type_acte(title_n, body_n):
    if "enquete publique" in title_n or "ouverture d'une enquete" in body_n[:3000]:
        return "Enquête publique"
    if "participation du public" in title_n or "consultation du public" in title_n:
        return "Consultation du public"
    if "autorisation environnementale" in title_n or "autorisation environnementale" in body_n[:4000]:
        return "Autorisation environnementale"
    if "installation classee" in title_n or "icpe" in title_n:
        return "ICPE"
    if "derogation" in title_n and "espece" in (title_n + body_n[:3000]):
        return "Dérogation espèces protégées"
    if "mise en demeure" in title_n:
        return "Mise en demeure"
    return "Arrêté / décision"


def deadline_for(kind, pub, body, delais):
    start, end = (None, None)
    if kind in ("Enquête publique", "Consultation du public"):
        start, end = find_period(body)
        if end:
            return start, end, "Clôture de la participation : déposer une contribution avant cette date."
    key = {"Autorisation environnementale": "autorisation_environnementale", "ICPE": "icpe"}.get(kind, "recours_general")
    d = delais[key]
    return start, pub + dt.timedelta(days=d["jours"]), d["texte"] + " (date indicative, à vérifier)"


def urgence(deadline, score):
    if deadline is None:
        return "À qualifier"
    j = (deadline - TODAY).days
    if j < 0:
        return "Échue"
    if j <= 7:
        return "J-7"
    if j <= 15:
        return "J-15"
    if j <= 30 or score >= 15:
        return "À traiter"
    return "À surveiller"


def link_dossiers(text_n, communes_n, dossiers, hit_ids):
    out = []
    for d in dossiers:
        term_hits = sum(1 for t in d["_terms"] if t in text_n)
        commune_hit = any(c in communes_n for c in d["_communes"])
        if term_hits >= 2 or (commune_hit and term_hits >= 1):
            out.append(d.get("Objet", "")[:120])
    return out[:6]


def actions_for(kind, hits, enjeux):
    acts = {
        "Enquête publique": "Consulter le dossier et l'avis de l'autorité environnementale ; déposer une contribution argumentée avant la clôture.",
        "Consultation du public": "Déposer un avis sur le projet d'arrêté avant la clôture de la consultation.",
        "Autorisation environnementale": "Analyser les prescriptions et mesures ERC ; recours des tiers possible dans les 4 mois.",
        "ICPE": "Analyser les prescriptions ; recours des tiers possible dans les 4 mois.",
        "Dérogation espèces protégées": "Vérifier les 3 conditions de l'article L.411-2 ; envisager recours gracieux/contentieux, voire référé-suspension.",
        "Mise en demeure": "Suivre l'exécution et l'éventuelle sanction ; signaler les manquements constatés.",
    }
    out = [acts.get(kind, "Lire l'arrêté ; évaluer l'opportunité d'un recours gracieux ou contentieux (2 mois).")]
    by_id = {e["id"]: e for e in enjeux["enjeux"]}
    for h in hits[:2]:
        out += by_id[h["id"]]["actions"][:2]
    seen, res = set(), []
    for a in out:
        if a not in seen:
            seen.add(a)
            res.append(a)
    return res


# ---------------------------------------------------------------- RAA
def list_raa():
    html = get(RAA_INDEX)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    years = sorted({a["href"] for a in soup.find_all("a", href=True)
                    if re.search(r"/Recueils-hebdomadaires-et-speciaux-des-actes-administratifs/20\d\d", a["href"])})
    years = [y for y in years if str(TODAY.year) in y or str(TODAY.year - (TODAY.month == 1)) in y][-2:]
    out = []
    for y in years:
        page = get(BASE + y if y.startswith("/") else y)
        if not page:
            continue
        s = BeautifulSoup(page, "html.parser")
        for a in s.find_all("a", href=True):
            h = a["href"]
            if "/contenu/telechargement/" in h and h.lower().endswith(".pdf"):
                fn = urllib.parse.unquote(h.rsplit("/", 1)[-1])
                m = re.search(r"73-(20\d\d)-(\d{3})", fn)
                dm = re.match(r"(20\d\d)-(\d\d)-(\d\d)", fn)
                try:
                    dfic = dt.date(*map(int, dm.groups())).isoformat() if dm else None
                except ValueError:
                    dfic = None
                out.append({"url": BASE + h if h.startswith("/") else h, "fichier": fn,
                            "numero": f"73-{m.group(1)}-{m.group(2)}" if m else fn,
                            "date_fichier": dfic})
    uniq = {r["url"]: r for r in out}
    return sorted(uniq.values(), key=lambda r: r["numero"])


ACT_ID = re.compile(r"\b(73-20\d\d-\d\d-\d\d-\d{5})\b")


def split_raa(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:  # noqa: BLE001
            pages.append("")
    full_head = "\n".join(pages[:3])
    pub = None
    m = re.search(r"PUBLI[ÉE]\s+LE\s+(\d{1,2}(?:er)?\s+\w+\s+20\d\d)", full_head, re.I)
    if m:
        pub = parse_any(m.group(1))
    # titres depuis le sommaire
    titles = {}
    som = re.sub(r"\s+", " ", full_head)
    for mm in re.finditer(r"(73-20\d\d-\d\d-\d\d-\d{5})\s*-\s*(.+?)\(\d+\s*pages?\)", som):
        titles[mm.group(1)] = mm.group(2).strip()
    actes, cur = {}, None
    for i, txt in enumerate(pages):
        if i < 1:
            continue
        ids = ACT_ID.findall(txt)
        if i < 8 and re.search(r"\(\d+\s*pages?\)", txt) and re.search(r"Page\s*\d+", txt):
            continue  # page de sommaire
        if ids:
            cur = ids[0]
        if cur:
            a = actes.setdefault(cur, {"id": cur, "page": i + 1, "texte": []})
            a["texte"].append(txt)
    for a in actes.values():
        a["texte"] = "\n".join(a["texte"])
        a["titre"] = titles.get(a["id"]) or first_title(a["texte"], a["id"])
    return pub, list(actes.values())


def first_title(text, aid):
    for line in text.splitlines():
        if aid in line and len(line) > len(aid) + 10:
            return line.split(aid, 1)[1].strip(" -")[:250]
    return text.strip().splitlines()[0][:200] if text.strip() else aid


def communes_in(text, communes):
    found = []
    for c in communes:
        if re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", text):
            found.append(c)
            if len(found) >= 8:
                break
    return found


def build_alert(src, titre, texte, url, pub, enjeux, dossiers, communes, acte_id=None, page=None):
    score, hits, kws = score_acte(titre, texte, enjeux)
    if score < enjeux.get("seuil_alerte", 4) or not hits:
        return None
    tn, bn = norm(titre), norm(texte)
    kind = type_acte(tn, bn)
    if src.startswith("Enquête publique") and kind == "Arrêté / décision":
        kind = "Enquête publique"
    if src.startswith("Participation") and kind == "Arrêté / décision":
        kind = "Consultation du public"
    start, deadline, regle = deadline_for(kind, pub or TODAY, texte, enjeux["delais"])
    coms = communes_in(titre + "\n" + texte[:6000], communes)
    dos = link_dossiers(bn[:20000] + " " + tn, [norm(c) for c in coms], dossiers, [h["id"] for h in hits])
    if dos:
        score += 5
    extrait = re.sub(r"\s+", " ", texte)
    k0 = next((norm(k) for k in kws), "")
    pos = norm(extrait).find(k0) if k0 else -1
    extrait = extrait[max(0, pos - 200): pos + 400] if pos >= 0 else extrait[:500]
    return {
        "uid": acte_id or url,
        "source": src,
        "acte": acte_id or "",
        "titre": re.sub(r"\s+", " ", titre).strip(),
        "type": kind,
        "date_publication": (pub or TODAY).isoformat(),
        "debut": start.isoformat() if start else "",
        "date_butoir": deadline.isoformat() if deadline else "",
        "regle_delai": regle,
        "urgence": urgence(deadline, score),
        "score": score,
        "enjeux": [h["label"] for h in hits[:4]],
        "mots_cles": kws[:12],
        "communes": coms,
        "dossiers_lies": dos,
        "actions": actions_for(kind, hits, enjeux),
        "extrait": extrait.strip(),
        "lien": url + (f"#page={page}" if page else ""),
        "detecte_le": TODAY.isoformat(),
        "statut": "Nouveau",
    }


def page_links(html, prefix):
    main = BeautifulSoup(html, "html.parser").find("main")
    if not main:
        return [], [], ""
    kids, pdfs = [], []
    for a in main.find_all("a", href=True):
        h = a["href"]
        full = BASE + h if h.startswith("/") else h
        if "(offset)" in full or "Partager" in a.get_text():
            continue
        if full.startswith(prefix + "/") and full not in kids:
            kids.append(full)
        elif "/contenu/telechargement/" in full and full not in pdfs:
            pdfs.append(full)
    return kids, pdfs, main.get_text(" ", strip=True)


def scan_extra_pages(enjeux, dossiers, communes, known, baseline):
    """Parcourt les rubriques (2 niveaux) ; une page « feuille » = un dossier publié."""
    out, visited = [], 0
    for src, root in EXTRA_PAGES.items():
        queue = [(root, 0)]
        while queue:
            url, depth = queue.pop(0)
            if visited > MAX_EXTRA_LINKS or time.time() - START > BUDGET_S + 600:
                print("Plafond de pages atteint")
                return out
            html = get(url)
            visited += 1
            if not html:
                continue
            kids, pdfs, text = page_links(html, url)
            if kids and depth < 2:
                queue += [(k, depth + 1) for k in kids if k not in known]
                if depth == 0:
                    continue
            if depth == 0 or url in known:
                continue
            known.add(url)
            title = BeautifulSoup(html, "html.parser").find("h1")
            title = title.get_text(" ", strip=True) if title else url.rsplit("/", 1)[-1].replace("-", " ")
            for pdf in pdfs[:2]:
                bts = get(pdf, binary=True)
                if bts:
                    try:
                        text += "\n" + "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(bts)).pages[:5])
                    except Exception:  # noqa: BLE001
                        pass
            al = build_alert(src, title, text[:60000], url, TODAY, enjeux, dossiers, communes)
            if not al:
                continue
            if baseline and not (al["type"] in ("Enquête publique", "Consultation du public") and al["date_butoir"] >= TODAY.isoformat()
                                 and "Clôture" in al["regle_delai"]):
                continue  # 1re passe : on n'alerte que sur les participations encore ouvertes
            out.append(al)
    return out


def main():
    DATA.mkdir(exist_ok=True)
    enjeux, dossiers = load_enjeux(), load_dossiers()
    communes = load_communes()
    print(f"{len(enjeux['enjeux'])} enjeux, {len(dossiers)} dossiers, {len(communes)} communes")
    etat = load_json(ETAT_F, {"raa_traites": [], "pages_vues": []})
    alertes = load_json(ALERTES_F, {"alertes": []})
    by_uid = {a["uid"]: a for a in alertes["alertes"]}
    first_run = not etat["raa_traites"]
    done = set(etat["raa_traites"])

    raa = [r for r in list_raa() if r["url"] not in done]
    if first_run:
        raa = raa[-FIRST_RUN_RAA:]  # rattrapage : derniers recueils (~6 semaines)
    raa = raa[-MAX_RAA_PER_RUN:]
    print(f"{len(raa)} RAA à analyser")
    new = 0
    for n, r in enumerate(raa, 1):
        if time.time() - START > BUDGET_S:
            print("Budget de temps atteint : reprise à la prochaine exécution")
            break
        print(f"[{n}/{len(raa)}] {r['fichier']}", flush=True)
        b = get(r["url"], binary=True)
        if not b:
            continue  # réessayé la semaine suivante
        try:
            pub, actes = split_raa(b)
        except Exception as e:  # noqa: BLE001
            print(f"  PDF illisible {r['fichier']}: {e}")
            done.add(r["url"])
            continue
        if not pub and r["date_fichier"]:
            pub = dt.date.fromisoformat(r["date_fichier"])
        kept = 0
        for a in actes:
            al = build_alert(f"RAA {r['numero']}", a["titre"], a["texte"], r["url"], pub, enjeux, dossiers,
                             communes, a["id"], a["page"])
            if al and al["uid"] not in by_uid:
                by_uid[al["uid"]] = al
                kept += 1
        new += kept
        print(f"  {r['numero']} : {len(actes)} actes, {kept} alertes")
        done.add(r["url"])

    known = set(etat.get("pages_vues", []))
    for al in scan_extra_pages(enjeux, dossiers, communes, known, baseline=not etat.get("pages_vues")):
        if al["uid"] not in by_uid:
            by_uid[al["uid"]] = al
            new += 1
    etat["pages_vues"] = sorted(known)[-3000:]

    # recalcul des urgences (les dates avancent) ; les statuts saisis sont conservés
    for a in by_uid.values():
        if a.get("date_butoir"):
            a["urgence"] = urgence(dt.date.fromisoformat(a["date_butoir"]), a["score"])
    lst = sorted(by_uid.values(), key=lambda a: (a["detecte_le"], a["score"]), reverse=True)
    alertes = {"mise_a_jour": dt.datetime.now().isoformat(timespec="minutes"),
               "nb_raa_analyses": len(done), "alertes": lst}
    ALERTES_F.write_text(json.dumps(alertes, ensure_ascii=False, indent=1), encoding="utf-8")
    etat["raa_traites"] = sorted(done)
    ETAT_F.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{new} nouvelles alertes ; {len(lst)} alertes au total")


if __name__ == "__main__":
    main()
