#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Veille biodiversité Savoie : nouveautés, dates d’enquêtes publiques et alertes."""

import datetime
import io
import os
import re

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE = "https://www.savoie.gouv.fr"
CSV = "data/tableau_de_bord_veille_biodiversite.csv"
ALERTS = "data/alertes_enquetes_publiques.csv"
TODAY = datetime.date.today()

COLUMNS = [
    "Niveau", "Thème", "Objet", "Type", "Territoire / communes",
    "Date / statut", "Échéance", "Enjeu biodiversité",
    "Action de veille", "Priorité", "Lien officiel"
]

PAGES = {
    "Enquêtes publiques": BASE + "/Publications/Enquetes-publiques/Informations-generales",
    "Rapports de commissaires enquêteurs": BASE + "/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Eau-foret-biodiversite/Rapports-de-commissaires-enqueteurs",
    "Arrêtés environnementaux / loi sur l’eau": BASE + "/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Eau-foret-biodiversite/Arretes-divers-et-declarations-au-titre-de-la-loi-sur-l-eau",
    "APPB": BASE + "/index.php/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Milieux-et-especes-proteges/Arretes-prefectoraux-de-protection-de-biotopes-APPB",
    "Chasse et pêche": BASE + "/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Chasse-et-peche",
    "Lyon-Turin": BASE + "/Actions-de-l-Etat/Transports-deplacements-et-securite-routiere/Transports-et-deplacements/Lyon-Turin-Ferroviaire",
}

KEYWORDS = [
    "enquête publique", "enquete publique", "avis d’enquête", "avis d'enquête",
    "commissaire enquêteur", "autorisation environnementale", "loi sur l’eau",
    "biodiversit", "espèce protégée", "biotope", "zone humide", "tourbière",
    "cours d’eau", "nappe", "natura 2000", "loup", "cormoran", "esod",
    "chasse", "galliforme", "tétras", "bartavelle", "lagopède", "gélinotte",
    "compensation", "erc", "lyon-turin", "telt", "jo 2030", "olympique"
]

MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "févr.": 2, "avr.": 4, "juil.": 7, "sept.": 9,
    "oct.": 10, "nov.": 11, "déc.": 12
}


def absolute_url(url):
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return BASE + url
    return url


def get_soup(url):
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "veille-biodiversite/2.2"}
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_french_date(text):
    text = re.sub(r"\s+", " ", text)

    match = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", text)
    if match:
        try:
            return datetime.date(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1))
            )
        except ValueError:
            pass

    match = re.search(
        r"\b(\d{1,2})(?:er)?\s+([a-zéûôàâèê]+\.?)\s+(\d{4})\b",
        text,
        re.IGNORECASE
    )
    if match:
        month = MONTHS.get(
            match.group(2).lower(),
            MONTHS.get(match.group(2).lower() + ".")
        )
        if month:
            try:
                return datetime.date(
                    int(match.group(3)),
                    month,
                    int(match.group(1))
                )
            except ValueError:
                pass

    return None


def extract_dates_from_text(text):
    start_date = None
    end_date = None

    match = re.search(
        r"(?:du|à compter du|ouverture(?: de l’enquête)?(?: publique)?(?: du)?|à partir du)"
        r"\s*([0-9]{1,2}[^0-9]{0,20}[0-9]{4})",
        text,
        re.IGNORECASE
    )
    if match:
        start_date = parse_french_date(match.group(1))

    match = re.search(
        r"(?:jusqu’au|jusqu'au|clôture(?: de l’enquête)?(?: publique)?(?: le)?|close le)"
        r"\s*([0-9]{1,2}[^0-9]{0,20}[0-9]{4})",
        text,
        re.IGNORECASE
    )
    if match:
        end_date = parse_french_date(match.group(1))

    if start_date is None or end_date is None:
        date_strings = re.findall(
            r"\b\d{1,2}(?:er)?\s+[a-zéûôàâèê]+\.?\s+\d{4}\b"
            r"|\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b",
            text,
            re.IGNORECASE
        )
        dates = sorted(
            {d for d in (parse_french_date(x) for x in date_strings) if d}
        )
        if dates:
            if start_date is None:
                start_date = dates[0]
            if end_date is None and len(dates) > 1:
                end_date = dates[-1]

    return start_date, end_date


def extract_dates_from_pdf(url):
    try:
        response = requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "veille-biodiversite/2.2"}
        )
        response.raise_for_status()
        reader = PdfReader(io.BytesIO(response.content))
        text = "\n".join(
            page.extract_text() or "" for page in reader.pages[:6]
        )
        start_date, end_date = extract_dates_from_text(text)
        return start_date, end_date, None
    except Exception as error:
        return None, None, f"PDF : {error}"


def extract_dates_from_html(url):
    try:
        soup = get_soup(url)
        text = soup.get_text(" ", strip=True)
        start_date, end_date = extract_dates_from_text(text)
        return start_date, end_date, None
    except Exception as error:
        return None, None, f"HTML : {error}"


def find_avis_link(url):
    try:
        soup = get_soup(url)
    except Exception:
        return None

    for link in soup.select("a[href]"):
        href = absolute_url(link.get("href", ""))
        label = (link.get_text(" ", strip=True) + " " + href).lower()

        if not any(word in label for word in ["avis", "enquête", "enquete", "pdf", "dossier", "registre"]):
            continue

        if href.lower().endswith(".pdf") or "enquete" in href or "avis" in label:
            return href

    return None


def alert_label(end_date):
    if end_date is None:
        return "Échéance inconnue"

    days_left = (end_date - TODAY).days

    if days_left < 0:
        return "Clôturée"
    if days_left == 0:
        return "ALERTE J-0 : contribution possible aujourd’hui"
    if days_left <= 1:
        return "ALERTE J-1"
    if days_left <= 7:
        return "ALERTE J-7"
    if days_left <= 15:
        return "ALERTE J-15"
    return f"À surveiller — J-{days_left}"


def scrape_publications():
    results = []

    for theme, url in PAGES.items():
        try:
            soup = get_soup(url)
        except Exception as error:
            print(f"AVERTISSEMENT : page inaccessible ({theme}) : {error}")
            continue

        for link in soup.select("a[href]"):
            title = re.sub(r"\s+", " ", link.get_text(" ", strip=True))
            href = absolute_url(link.get("href", ""))

            if not title or len(title) < 12:
                continue
            if not href.startswith("http"):
                continue

            searchable = (title + " " + href).lower()
            if not any(keyword in searchable for keyword in KEYWORDS):
                continue

            item_type = (
                "Enquête publique"
                if "enquêt" in searchable
                else "Publication officielle"
            )

            results.append({
                "Thème": theme,
                "Objet": title,
                "Lien": href,
                "Type": item_type
            })

    return results


def main():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(CSV):
        try:
            dataframe = pd.read_csv(CSV)
        except Exception as error:
            print(f"AVERTISSEMENT : CSV illisible, création d’un nouveau fichier : {error}")
            dataframe = pd.DataFrame(columns=COLUMNS)
    else:
        dataframe = pd.DataFrame(columns=COLUMNS)

    for column in COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = None

    existing_links = set(
        dataframe["Lien officiel"].dropna().astype(str)
    )

    alerts = []
    added_items = 0

    for item in scrape_publications():
        link = item["Lien"]

        if link in existing_links:
            continue

        if link.lower().endswith(".pdf"):
            start_date, end_date, error = extract_dates_from_pdf(link)
        else:
            start_date, end_date, error = extract_dates_from_html(link)

            if start_date is None or end_date is None:
                avis_link = find_avis_link(link)
                if avis_link:
                    if avis_link.lower().endswith(".pdf"):
                        start2, end2, error2 = extract_dates_from_pdf(avis_link)
                    else:
                        start2, end2, error2 = extract_dates_from_html(avis_link)

                    start_date = start_date or start2
                    end_date = end_date or end2
                    error = error or error2

        if end_date:
            deadline = end_date.isoformat()
        else:
            deadline = "À vérifier dans le document"
            if error:
                deadline += f" ({error})"

        priority = "Élevée"
        action = "Consulter le document"

        if end_date and end_date >= TODAY:
            action = "Contribuer avant la clôture"
            if (end_date - TODAY).days <= 15:
                priority = "Très élevée"

        new_row = {
            "Niveau": "Savoie",
            "Thème": item["Thème"],
            "Objet": item["Objet"],
            "Type": item["Type"],
            "Territoire / communes": "Savoie",
            "Date / statut": TODAY.isoformat(),
            "Échéance": deadline,
            "Enjeu biodiversité": "À qualifier après lecture du document",
            "Action de veille": action,
            "Priorité": priority,
            "Lien officiel": link
        }

        dataframe = pd.concat(
            [dataframe, pd.DataFrame([new_row])],
            ignore_index=True
        )
        existing_links.add(link)
        added_items += 1

        if item["Type"] == "Enquête publique":
            alerts.append({
                "Objet": item["Objet"],
                "Lien": link,
                "Début": start_date.isoformat() if start_date else "",
                "Clôture": end_date.isoformat() if end_date else "",
                "Alerte": alert_label(end_date),
                "Date de contrôle": TODAY.isoformat()
            })

    dataframe.to_csv(CSV, index=False)

    alerts_dataframe = pd.DataFrame(
        alerts,
        columns=["Objet", "Lien", "Début", "Clôture", "Alerte", "Date de contrôle"]
    )
    alerts_dataframe.to_csv(ALERTS, index=False)

    print(f"{added_items} nouveaux objets ajoutés.")
    print(f"{len(alerts)} enquêtes publiques analysées.")


if __name__ == "__main__":
    main()
