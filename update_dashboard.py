#!/usr/bin/env python3
"""Veille biodiversité Savoie : nouveautés, dates d’enquêtes publiques et alertes."""
import requests, pandas as pd, os, re, datetime, io
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE="https://www.savoie.gouv.fr"
CSV="data/tableau_de_bord_veille_biodiversite.csv"
ALERTS="data/alertes_enquetes_publiques.csv"
TODAY=datetime.date.today()
COLS=["Niveau","Thème","Objet","Type","Territoire / communes","Date / statut","Échéance","Enjeu biodiversité","Action de veille","Priorité","Lien officiel"]

PAGES={
 "Enquêtes publiques":BASE+"/Publications/Enquetes-publiques/Informations-generales",
 "Rapports de commissaires enquêteurs":BASE+"/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Eau-foret-biodiversite/Rapports-de-commissaires-enqueteurs",
 "Arrêtés environnementaux / loi sur l’eau":BASE+"/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Eau-foret-biodiversite/Arretes-divers-et-declarations-au-titre-de-la-loi-sur-l-eau",
 "APPB":BASE+"/index.php/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Milieux-et-especes-proteges/Arretes-prefectoraux-de-protection-de-biotopes-APPB",
 "Chasse et pêche":BASE+"/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Chasse-et-peche",
 "Lyon-Turin":BASE+"/Actions-de-l-Etat/Transports-deplacements-et-securite-routiere/Transports-et-deplacements/Lyon-Turin-Ferroviaire"}

KEY=["enquête publique","enquete publique","avis d’enquête","avis d'enquête","commissaire enquêteur","autorisation environnementale","loi sur l’eau","biodiversit","espèce protégée","biotope","zone humide","tourbière","cours d’eau","nappe","natura 2000","loup","cormoran","esod","chasse","galliforme","tétras","bartavelle","lagopède","gélinotte","compensation","erc","lyon-turin","telt","jo 2030","olympique"]
MONTHS={"janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,"août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12,"févr.":2,"avr.":4,"juil.":7,"sept.":9,"oct.":10,"nov.":11,"déc.":12}

def absolute(u): return u if u.startswith("http") else (BASE+u if u.startswith("/") else u)
def fetch(u): return requests.get(u,timeout=30,headers={"User-Agent":"veille-biodiversite/2.1"})
def soup(u): return BeautifulSoup(fetch(u).text,"html.parser")

def parse_date(t):
    t=re.sub(r"\s+"," ",t)
    m=re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b",t)
    if m:
        try:return datetime.date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        except ValueError:pass
    m=re.search(r"\b(\d{1,2})(?:er)?\s+([a-zéûôàâèê]+\.?)\s+(\d{4})\b",t,re.I)
    if m:
        mo=MONTHS.get(m.group(2).lower(),MONTHS.get(m.group(2).lower()+"."))
        if mo:
            try:return datetime.date(int(m.group(3)),mo,int(m.group(1)))
            except ValueError:pass
    return None

def dates_from_text(t):
    start=end=None
    m=re.search(r"(?:du|à compter du|ouverture(?: de l’enquête)?(?: publique)?(?: du)?|à partir du)\s*([0-9]{1,2}[^0-9]{0,20}[0-9]{4})",t,re.I)
    if m:start=parse_date(m.group(1))
    m=re.search(r"(?:jusqu’au|jusqu'au|clôture(?: de l’enquête)?(?: publique)?(?: le)?|close le)\s*([0-9]{1,2}[^0-9]{0,20}[0-9]{4})",t,re.I)
    if m:end=parse_date(m.group(1))
    if not start or not end:
        ds=sorted({d for d in (parse_date(x) for x in re.findall(r"\b\d{1,2}(?:er)?\s+[a-zéûôàâèê]+\.?\s+\d{4}\b|\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b",t,re.I)) if d})
        if ds:
            start=start or ds[0]
            end=end or (ds[-1] if len(ds)>1 else None)
    return start,end

def pdf_dates(u):
    try:
        pdf=PdfReader(io.BytesIO(fetch(u).content))
        text="\n".join((p.extract_text() or "") for p in pdf.pages[:6])
        s,e=dates_from_text(text)
        return s,e,None
    except Exception as e:return None,None,f"PDF : {e}"

def html_dates(u):
    try:
        text=soup(u).get_text(" ",strip=True)
        s,e=dates_from_text(text)
        return s,e,None
    except Exception as e:return None,None,f"HTML : {e}"

def find_avis(u):
    try:s=soup(u)
    except Exception:return None
    for a in s.select("a[href]"):
        h=absolute(a.get("href",""))
        lab=(a.get_text(" ",strip=True)+" "+h).lower()
        if any(k in lab for k in ["avis","enquête","enquete","pdf","dossier","registre"]):
            if h.lower().endswith(".pdf") or "enquete" in h or "avis" in lab:return h
    return None

def alert(end):
    if not end:return "Échéance inconnue"
    d=(end-TODAY).days
    if d<0:return "Clôturée"
    if d==0:return "ALERTE J-0 : contribution possible aujourd’hui"
    if d<=1:return "ALERTE J-1"
    if d<=7:return "ALERTE J-7"
    if d<=15:return "ALERTE J-15"
    return f"À surveiller — J-{d}"

def scrape():
    rows=[]
    for theme,url in PAGES.items():
        try:page=soup(url)
        except Exception as e:
            print(f"AVERTISSEMENT : page inaccessible ({theme}) : {e}")
            continue
        for a in page.select("a[href]"):
            t=re.sub(r"\s+"," ",a.get_text(" ",strip=True))
            h=absolute(a.get("href",""))
            if not t or len(t)<12 or not h.startswith("http"):continue
            low=(t+" "+h).lower()
            if not any(k in low for k in KEY):continue
            rows.append({"Thème":theme,"Objet":t,"Lien":h,"Type":"Enquête publique" if "enquêt" in low else "Publication officielle"})
    return rows

def main():
    os.makedirs("data",exist_ok=True)
    if os.path.exists(CSV):
        try:df=pd.read_csv(CSV)
        except Exception as e:
            print(f"AVERTISSEMENT : CSV illisible, création d’un nouveau fichier ({e})")
            df=pd.DataFrame(columns=COLS)
    else:
        df=pd.DataFrame(columns=COLS)
    for c in COLS:
        if c not in df.columns:df[c]=None
    existing=set(df["Lien officiel"].dropna().astype(str))
    alerts=[];added=0
    for item in scrape():
        link=item["Lien"]
        if link in existing:continue
        start=end=err=None
        if link.lower().endswith(".pdf"):start,end,err=pdf_dates(link)
        else:
            start,end,err=html_dates(link)
            if not start or not end:
                avis=find_avis(link)
                if avis:
                    s2,e2,e3=pdf_dates(avis) if avis.lower().endswith(".pdf") else html_dates(avis)
                    start=start or s2;end=end or e2;err=err or e3
        echeance=end.isoformat() if end else "À vérifier dans le document"+(f" ({err})" if err else "")
        row={"Niveau":"Savoie","Thème":item["Thème"],"Objet":item["Objet"],"Type":item["Type"],"Territoire / communes":"Savoie","Date / statut":TODAY.isoformat(),"Échéance":echeance,"Enjeu biodiversité":"À qualifier après lecture du document","Action de veille":"Contribuer avant la clôture" if end and end>=TODAY else "Consulter le document","Priorité":"Très élevée" if end and 0<=(end-TODAY).days<=15 else "Élevée","Lien officiel":link}
        df=pd.concat([df,pd.DataFrame([row])],ignore_index=True)
        existing.add(link);added+=1
        if item["Type"]=="Enquête publique":
            alerts.append({"Objet":item["Objet"],"Lien":link,"Début":start.isoformat() if start else "","Clôture":end.isoformat() if end else "","Alerte":alert(end),"Date de contrôle":TODAY.isoformat()})
    df.to_csv(CSV,index=False)
    pd.DataFrame(alerts,columns=["Objet","Lien","Début","Clôture","Alerte","Date de contrôle"]).to_csv(ALERTS,index=False)
    print(f"{added} nouveaux objets ajoutés ; {len(alerts)} enquêtes analysées.")

if __name__=="__main__":main()

  df=pd.concat([df,new],ignore_index=True);df.to_csv(csv,index=False);print(f"{len(new)} nouveaux objets ajoutés")
 else:print("Aucun nouvel objet détecté")
if __name__=="__main__":main()
