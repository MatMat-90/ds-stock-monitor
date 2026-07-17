# Base de référence des modèles de véhicules

Déposez ici des images de référence, **un sous-dossier par modèle** :

```
data/vehicles/
├── renault_clio/
│   ├── avant.jpg
│   └── profil.jpg
├── peugeot_208/
│   └── profil.jpg
└── ...
```

Chaque véhicule capturé par le radar est comparé à ces images (appariement de
points d'intérêt ORB). Le nom du dossier correspondant apparaît alors dans le
relevé (`vehicle_model`). Si ce dossier est vide, l'identification du modèle
est simplement omise — le reste du radar fonctionne normalement.

Conseils :
- privilégiez des vues sous le même angle que celui de votre caméra ;
- plusieurs images par modèle améliorent la fiabilité ;
- formats acceptés : jpg, jpeg, png, bmp, webp.
