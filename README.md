# Orbe en réalité augmentée (iPhone + Android)

Un objet 3D animé (cristal, deux anneaux, deux satellites) que l'on pose sur une surface plane réelle
avec la caméra du téléphone.

## Contenu

| Fichier | Rôle |
|---|---|
| `index.html` | La page (utilise la bibliothèque `<model-viewer>` de Google, chargée depuis jsDelivr) |
| `assets/objet-v2.glb` | Modèle animé pour Android (WebXR, Scene Viewer) et l'aperçu 3D |
| `assets/objet-v2.usdz` | Le même modèle animé pour l'iPhone (AR Quick Look) |
| `musique.js` | Les deux musiques de fond, synthétisées dans le navigateur (Web Audio) : aucun fichier audio |
| `generate_model.py` | Régénère les deux modèles (Python 3, aucune dépendance) |
| `_headers` | Types MIME corrects sur Netlify et Cloudflare Pages |

## Mettre en ligne (HTTPS obligatoire)

La caméra et la RA ne fonctionnent qu'en HTTPS. Le plus simple : glisser-déposer le dossier sur
Netlify Drop, Cloudflare Pages, Vercel, ou le pousser sur GitHub Pages. Ouvrez ensuite l'adresse sur le téléphone.

## Tester en local

    python3 -m http.server 8000

- Android : branchez le téléphone en USB (débogage USB activé), lancez `adb reverse tcp:8000 tcp:8000`,
  puis ouvrez `http://localhost:8000` dans Chrome (localhost est considéré comme sécurisé).
- iPhone : utilisez un tunnel HTTPS (par exemple `cloudflared tunnel --url http://localhost:8000`).

## Comment ça marche selon l'appareil

- Android / Chrome : session WebXR dans la page (détection du sol, réticule, toucher pour poser).
  Sinon, bascule automatique sur Google Scene Viewer.
- iPhone / iPad / Safari : AR Quick Look avec `objet.usdz`.

## Animation dans la réalité augmentée iPhone

AR Quick Look ne lit que les images clés écrites dans le fichier USDZ ; il n'interpole pas une rotation
« 0° puis 360° », qui donnerait deux orientations identiques donc un objet immobile. Le générateur écrit
donc 64 orientations par tour (une toutes les 3 images à 24 i/s, soit au plus 17° d'écart) et met 24 boucles
de 8 s bout à bout : l'animation dure plus de 3 minutes même si Quick Look ne la relance pas.
La lévitation de l'objet est aussi plus ample (±1,8 cm), pour que le mouvement se voie dès la pose.

## Personnaliser

- Autre objet : remplacez `assets/objet-v2.glb` (avec animation) et `assets/objet-v2.usdz`, ou modifiez la
  scène dans `generate_model.py` puis relancez-le.
- Si vous remplacez les fichiers, gardez un nouveau nom (par exemple `objet-v3.*`) et mettez à jour `index.html` :
  Safari met les fichiers en cache et afficherait sinon l'ancienne version.
- Pour ne pas dépendre d'un CDN, téléchargez `model-viewer.min.js` et changez l'attribut `src` de la balise `<script>`.

## Musique de fond

Deux boutons (« Musique calme » et « Musique rythmée ») en haut à gauche de la scène. Un seul son à la fois :
toucher l'autre bouton change de musique, toucher le bouton actif l'arrête. Le son démarre au toucher
(obligatoire sur iPhone).

- Les pistes sont générées en direct : nappes et cloches pour la calme, 100 BPM avec basse et arpège pour la rythmée.
  Pour changer les accords ou le tempo, modifiez `ACCORDS` et `bpm` dans `musique.js`.
- Pour utiliser vos propres fichiers MP3, remplacez les deux fonctions `pisteCalme` et `pisteRythmee`
  par un `new Audio("assets/ma-musique.mp3")` avec `loop = true`.
- iPhone : le mode silencieux peut couper le son sur les anciennes versions d'iOS.
- Le son continue dans la RA intégrée à la page (Chrome Android). Il peut s'interrompre dans les vues
  système AR Quick Look (iPhone) et Scene Viewer (Android), qui remplacent la page.
