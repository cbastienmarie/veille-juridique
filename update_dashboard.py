#!/usr/bin/env python3
import requests, pandas as pd, os, re, datetime
from bs4 import BeautifulSoup
BASE="https://www.savoie.gouv.fr"
PAGES={
 "Arrêtés environnementaux / loi sur l’eau":BASE+"/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Eau-foret-biodiversite/Arretes-divers-et-declarations-au-titre-de-la-loi-sur-l-eau",
 "Rapports de commissaires enquêteurs":BASE+"/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Eau-foret-biodiversite/Rapports-de-commissaires-enqueteurs",
 "APPB":BASE+"/index.php/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Milieux-et-especes-proteges/Arretes-prefectoraux-de-protection-de-biotopes-APPB",
 "Chasse et pêche":BASE+"/Actions-de-l-Etat/Paysages-environnement-risques-naturels-et-technologiques/Environnement/Chasse-et-peche",
 "Lyon-Turin":BASE+"/Actions-de-l-Etat/Transports-deplacements-et-securite-routiere/Transports-et-deplacements/Lyon-Turin-Ferroviaire",
 "Enquêtes publiques":BASE+"/Publications/Enquetes-publiques/Informations-generales"}
KEY=["biodiversit","espèce","biotope","zone humide","tourbière","cours d’eau","nappe","natura 2000","loup","cormoran","esod","dégâts","chasse","galliforme","tétras","bartavelle","lagopède","gélinotte","enquête publique","autorisation environnementale","loi sur l’eau","compensation","erc","lyon-turin","telt","jo 2030","olympique"]
def fetch(url):
 r=requests.get(url,timeout=30,headers={"User-Agent":"veille-biodiversite/1.0"});r.raise_for_status();return BeautifulSoup(r.text,"html.parser")
def items():
 out=[];today=datetime.date.today().isoformat()
 for theme,url in PAGES.items():
  try:s=fetch(url)
  except Exception as e:print("ERREUR",theme,e);continue
  for a in s.select("a[href]"):
   t=re.sub(r"\s+"," ",a.get_text(" ",strip=True));h=a.get("href","")
   if not t or len(t)<12:continue
   if not any(k in t.lower() for k in KEY):continue
   if h.startswith("/"):h=BASE+h
   elif not h.startswith("http"):continue
   out.append({"Niveau":"Savoie","Thème":theme,"Objet":t,"Type":"Publication officielle","Territoire / communes":"Savoie","Date / statut":today,"Échéance":"À vérifier dans le document","Enjeu biodiversité":"À qualifier après lecture du document","Action de veille":"Consulter le document et qualifier l’enjeu","Priorité":"Élevée","Lien officiel":h})
 return out
def main():
 csv="data/tableau_de_bord_veille_biodiversite.csv"
 df=pd.read_csv(csv) if os.path.exists(csv) else pd.DataFrame()
 new=pd.DataFrame(items())
 if not new.empty and not df.empty:
  new=new[~new["Lien officiel"].isin(set(df["Lien officiel"].astype(str)))]
 if not new.empty:
  df=pd.concat([df,new],ignore_index=True);df.to_csv(csv,index=False);print(f"{len(new)} nouveaux objets ajoutés")
 else:print("Aucun nouvel objet détecté")
if __name__=="__main__":main()
