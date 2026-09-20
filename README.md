# Méduse en réalité augmentée (iPhone + Android)

Une méduse 3D animée (ombrelle qui pulse, six tentacules qui ondulent) que l'on pose sur une surface plane
réelle avec la caméra du téléphone.

## Contenu

| Fichier | Rôle |
|---|---|
| `index.html` | La page (utilise la bibliothèque `<model-viewer>` de Google, chargée depuis jsDelivr) |
| `assets/meduse-v4.glb` | Modèle avec animation intégrée, pour Android (WebXR, Scene Viewer) et l'aperçu 3D |
| `assets/meduse-v4.usdz` | Le même modèle et la même animation, pour l'iPhone (AR Quick Look) |
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
- iPhone / iPad / Safari : AR Quick Look avec `meduse-v4.usdz` (modes « Objet » et « AR »).

## Animation intégrée aux modèles

Les deux fichiers contiennent la même animation de 3 s, écrite dans le fichier lui-même (pas ajoutée par la page).
Elle est faite de transformations sur une hiérarchie de pièces : les tentacules sont des chaînes de 4 capsules
articulées qui ondulent, l'ombrelle pulse (changement d'échelle) et le corps entier flotte.

- `meduse-v4.glb` : 26 nœuds animés (animation « Nage »), lus par model-viewer, par la RA WebXR de Chrome
  et par Scene Viewer.
- `meduse-v4.usdz` : les mêmes 26 nœuds animés au format USD, lus par AR Quick Look sur iPhone,
  dans les modes « Objet » et « AR ».

### Pourquoi la méduse restait immobile sur iPhone

Cause trouvée dans les forums développeurs d'Apple (sujet « xform called "Scene" breaks animations on Quicklook
starting with iOS15 », reconnu par un ingénieur Apple) : **depuis iOS 15, AR Quick Look n'anime plus un fichier USDZ
qui contient un nœud (Xform) nommé « Scene »**, même si l'animation est correcte. Toutes les versions précédentes
de ce site avaient un nœud racine appelé « Scene ». Il s'appelle maintenant « Meduse », et `generate_model.py`
refuse les noms réservés. Si vous créez vos propres USDZ, n'utilisez jamais « Scene » (Blender l'ajoute par défaut).

### Autres réglages pour AR Quick Look

- **Animation de transformations** (translation, rotation, échelle), plus fiable que l'animation de squelette.
- **Durée de 3 s, écrite une seule fois.** Au-delà de 10 s, Quick Look affiche un curseur de lecture au lieu de
  boucler seul.
- **Temps entiers, une clé par image** (24 i/s).
- **Mouvements amples** : la pointe d'un tentacule se déplace de plus de 8 cm, l'ombrelle change de hauteur de 4 cm,
  le corps monte et descend de 4 cm.
- Aucune métadonnée exotique dans l'en-tête du fichier.
- Dans la page, l'animation démarre toujours (le bouton « Mettre en pause » permet de l'arrêter).

`generate_model.py` produit les deux fichiers à partir des mêmes données.

## Personnaliser

- Autre objet : remplacez `assets/meduse-v4.glb` (avec animation) et `assets/meduse-v4.usdz`, ou modifiez le
  squelette, la forme et l'animation dans `generate_model.py` puis relancez-le.
- Si vous remplacez les fichiers, gardez un nouveau nom (par exemple `meduse-v5.*`) et mettez à jour `index.html` :
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
