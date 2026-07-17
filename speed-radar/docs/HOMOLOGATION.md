# Homologation d'un cinémomètre : la procédure réelle, et où en est ce projet

## Ce que « homologué » veut dire

En France, un radar utilisé pour verbaliser est un **instrument de mesure
réglementé** au sens du décret n° 2001-387 du 3 mai 2001. Les cinémomètres de
contrôle routier sont régis par l'**arrêté du 4 juin 2009**, qui s'appuie sur
la recommandation internationale **OIML R 91**. Concrètement :

1. **Examen de type** — le *fabricant* soumet l'instrument complet
   (matériel + logiciel, indissociables et scellés) au **LNE** (Laboratoire
   national de métrologie et d'essais), qui réalise des essais en laboratoire
   et sur route. Le certificat d'examen de type est délivré par décision
   ministérielle.
2. **Exigences de précision (erreurs maximales tolérées)** — en poste fixe :
   **±5 km/h en dessous de 100 km/h, ±5 % au-dessus** (±10 km/h / ±10 % pour
   les mesures en déplacement).
3. **Vérification initiale puis périodique annuelle** — chaque exemplaire est
   vérifié par un organisme agréé, scellé, et porte une vignette.
4. **Exigences logicielles** — le logiciel de mesure doit être identifiable
   (empreinte), protégé contre toute modification, et les résultats doivent
   être inviolables (guide **WELMEC 7.2**).
5. **Usage** — même homologué, seuls les agents assermentés peuvent
   verbaliser. La mesure d'un particulier n'a **jamais** de valeur
   répressive ; elle peut au mieux servir de signalement à la commune ou à
   la gendarmerie.

## Pourquoi ce logiciel ne peut pas être homologué en l'état

| Exigence réglementaire | État du projet | Écart |
|---|---|---|
| Précision ±5 km/h / ±5 % garantie | Auto-calibration statistique : ±10-20 % typique | ❌ Le principe de mesure lui-même est hors tolérance. L'homographie sol mesurée sur place s'en approche, mais sans garantie certifiable |
| Instrument complet scellé (matériel + logiciel) | Logiciel seul, caméra quelconque non maîtrisée | ❌ L'homologation porte sur un couple matériel/logiciel figé ; « n'importe quelle caméra » est par construction inhomologable |
| Base de temps étalonnée | Horloge du système hôte, FPS annoncés par la caméra | ❌ Il faudrait une horloge étalonnée et un capteur à cadence garantie |
| Demandeur = fabricant | Projet open source | ❌ Seule une entité constituée peut déposer un dossier (compter des dizaines de milliers d'euros et 12-24 mois) |
| Identification du logiciel (empreinte) | `software_fingerprint()` dans chaque relevé | ✅ Implémenté |
| Traçabilité des paramètres de mesure | `config_fingerprint()` dans chaque relevé | ✅ Implémenté |
| Inviolabilité des résultats | Journal chaîné + signé HMAC (`SealedEventLog`), vérifiable par `--verifier-journal` | ✅ Implémenté (clé sur disque ; un vrai instrument la met dans un composant scellé) |
| Détection de défaut avant mesure | Autotest bloquant au démarrage (`--autotest`) | ✅ Implémenté |

## Si vous vouliez vraiment aller au bout

1. Figer un **couple matériel + logiciel** : une caméra précise (global
   shutter, cadence garantie), un calculateur dédié, le tout scellable.
2. Remplacer l'auto-calibration statistique par une **calibration
   métrologique** : mire au sol mesurée par un géomètre, homographie
   certifiée à l'installation, revérifiée périodiquement.
3. Démontrer la précision contre un **cinémomètre de référence** (campagnes
   d'essais comparatifs, toutes conditions météo/luminosité).
4. Constituer le **dossier technique** (conception, analyse logicielle
   WELMEC 7.2, résultats d'essais) et contacter le **LNE**
   (lne.fr — certification des cinémomètres).
5. Après certificat d'examen de type : vérification initiale de chaque
   exemplaire, puis vérification annuelle.

## L'alternative réaliste

Pour un usage citoyen (dossier auprès d'une mairie pour demander un
aménagement, étude de trafic), l'homologation n'est pas nécessaire : ce qui
compte est la **crédibilité méthodologique**. C'est exactement ce que les
mécanismes ci-dessus apportent : mesures horodatées, qualité R² affichée,
calibration documentée dans chaque relevé, journal infalsifiable, version du
logiciel identifiée. Présentez les relevés comme des **ordres de grandeur
indicatifs**, jamais comme des constats d'infraction.
