"""Range les contenus collectés (in/N.txt : 1re ligne = URL) dans le cache du moteur."""
import sys, hashlib, urllib.parse
from pathlib import Path
c = Path(sys.argv[1]); n = 0
for f in sorted((c / "in").glob("*.txt")):
    url, _, body = f.read_text(encoding="utf-8").partition("\n")
    (c / (hashlib.sha1(urllib.parse.unquote(url.strip()).encode()).hexdigest() + ".txt")).write_text(body, encoding="utf-8")
    f.unlink(); n += 1
(c / "manquants.txt").unlink(missing_ok=True)
print(n, "contenus importés")
