# Méduse en réalité augmentée (iPhone + Android)

Une méduse 3D animée (ombrelle qui pulse, six tentacules qui ondulent) que l'on pose sur une surface plane
réelle avec la caméra du téléphone.

## Contenu

| Fichier | Rôle |
|---|---|
| `index.html` | La page (utilise la bibliothèque `<model-viewer>` de Google, chargée depuis jsDelivr) |
| `assets/meduse-v2.glb` | Modèle avec squelette et animation intégrée, pour Android (WebXR, Scene Viewer) et l'aperçu 3D |
| `assets/meduse-v2.usdz` | Le même modèle, même squelette et même animation, pour l'iPhone (AR Quick Look) |
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
- iPhone / iPad / Safari : AR Quick Look avec `meduse-v2.usdz` (modes « Objet » et « AR »).

## Animation intégrée aux modèles

Les deux fichiers contiennent une vraie animation squelettique, pas un simple mouvement ajouté par la page :

- `meduse-v2.glb` : squelette de 20 os (`skin`) et animation « Nage » de 3 s (`animation`), lue par model-viewer,
  par la RA WebXR de Chrome et par Scene Viewer.
- `meduse-v2.usdz` : le même squelette et la même animation au format USD (`UsdSkel`), lus nativement par
  AR Quick Look sur iPhone, dans les modes « Objet » et « AR ».

Réglages du fichier iPhone, d'après la documentation d'Apple :

- **Durée de 3 s, écrite une seule fois.** Au-delà de 10 s, Quick Look affiche un curseur de lecture au lieu de
  boucler tout seul. Une version précédente répétait la boucle 20 fois (60 s) : c'est probablement pour cela
  que la méduse restait immobile. Quick Look relance lui-même une animation courte.
- **Une clé par image** (24 par seconde), pour ne dépendre d'aucune interpolation.
- **Métadonnées `autoPlay = true` et `playbackMode = "loop"`** dans l'en-tête : lecture dès le chargement, en boucle.
- **Lévitation portée par le nœud `SkelRoot`** (mouvement du corps entier), en plus de l'animation des os :
  même si une partie de l'animation n'était pas lue, la méduse resterait en mouvement.

Les deux animations sont générées à partir des mêmes données par `generate_model.py`.

## Personnaliser

- Autre objet : remplacez `assets/meduse-v2.glb` (avec animation) et `assets/meduse-v2.usdz`, ou modifiez le
  squelette, la forme et l'animation dans `generate_model.py` puis relancez-le.
- Si vous remplacez les fichiers, gardez un nouveau nom (par exemple `meduse-v3.*`) et mettez à jour `index.html` :
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
