# Méduse en réalité augmentée (iPhone + Android)

Une méduse 3D animée (ombrelle qui pulse, six tentacules qui ondulent) que l'on pose sur une surface plane
réelle avec la caméra du téléphone.

## Contenu

| Fichier | Rôle |
|---|---|
| `index.html` | La page (utilise la bibliothèque `<model-viewer>` de Google, chargée depuis jsDelivr) |
| `assets/meduse-v3.glb` | Modèle avec animation intégrée, pour Android (WebXR, Scene Viewer) et l'aperçu 3D |
| `assets/meduse-v3.usdz` | Le même modèle et la même animation, pour l'iPhone (AR Quick Look) |
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
- iPhone / iPad / Safari : AR Quick Look avec `meduse-v3.usdz` (modes « Objet » et « AR »).

## Animation intégrée aux modèles

Les deux fichiers contiennent la même animation de 3 s, écrite dans le fichier lui-même (pas ajoutée par la page).
Elle est faite de transformations sur une hiérarchie de pièces : les tentacules sont des chaînes de 4 capsules
articulées qui ondulent, l'ombrelle pulse (changement d'échelle) et le corps entier flotte.

- `meduse-v3.glb` : 26 nœuds animés (animation « Nage »), lus par model-viewer, par la RA WebXR de Chrome
  et par Scene Viewer.
- `meduse-v3.usdz` : les mêmes 26 nœuds animés au format USD, lus par AR Quick Look sur iPhone,
  dans les modes « Objet » et « AR ».

Choix faits pour AR Quick Look (c'est le lecteur le plus strict) :

- **Animation de transformations, pas de squelette.** Les versions précédentes utilisaient un squelette (UsdSkel)
  puis une boucle répétée pendant 60 s : la méduse restait immobile sur iPhone. Les transformations d'objets
  sont le type d'animation que Quick Look lit de la façon la plus fiable.
- **Durée de 3 s, écrite une seule fois.** Au-delà de 10 s, Quick Look affiche un curseur de lecture au lieu de
  boucler seul.
- **Temps entiers, une clé par image** (24 i/s) : aucune interpolation n'est nécessaire.
- **Mouvements amples** : la pointe d'un tentacule se déplace de plus de 8 cm, l'ombrelle change de hauteur de 4 cm,
  le corps monte et descend de 4 cm. Rien de subtil qui pourrait passer inaperçu.
- Aucune métadonnée exotique dans l'en-tête du fichier.

`generate_model.py` produit les deux fichiers à partir des mêmes données.

## Personnaliser

- Autre objet : remplacez `assets/meduse-v3.glb` (avec animation) et `assets/meduse-v3.usdz`, ou modifiez le
  squelette, la forme et l'animation dans `generate_model.py` puis relancez-le.
- Si vous remplacez les fichiers, gardez un nouveau nom (par exemple `meduse-v4.*`) et mettez à jour `index.html` :
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
