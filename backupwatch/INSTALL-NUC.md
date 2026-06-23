# Installation sur le NUC (kiosque)

Ce guide installe **BackupWatch** sur le NUC qui pilote l'écran, pour que le
tableau de bord des sauvegardes s'affiche tout seul dans la rotation
**wee rotate**, mis à jour **chaque matin à 7h**, sans intervention.

> Résultat : une URL fixe **`http://localhost:8470/`** qui montre l'état du jour.

---

## 0. Pré-requis

- Le NUC sous **Windows**.
- Une connexion **Internet** (le NUC en a déjà puisqu'il affiche des pages web).
- Tes **identifiants Microsoft Graph** (déjà créés) : Tenant ID, Client ID,
  Client Secret, et l'adresse de la boîte qui reçoit les rapports.

---

## 1. Installer Python

1. Télécharge **Python 3.11 ou plus** : <https://www.python.org/downloads/>
2. Pendant l'installation, **coche « Add python.exe to PATH »** (important).
3. Vérifie : ouvre l'invite de commandes (`cmd`) et tape
   ```
   python --version
   ```
   Tu dois voir `Python 3.x`.

---

## 2. Copier BackupWatch

Décompresse **`backupwatch.zip`** dans un dossier simple, par exemple :
```
C:\BackupWatch
```
(évite les espaces et accents dans le chemin si possible.)

---

## 3. Installer les dépendances

Ouvre une invite de commandes **dans ce dossier** (dans l'Explorateur, clique
dans la barre d'adresse, tape `cmd`, Entrée), puis :
```
pip install -r requirements.txt
```

---

## 4. Configurer l'accès à la boîte mail

1. Copie **`.env.example`** en **`.env`** et renseigne tes secrets :
   ```
   GRAPH_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   GRAPH_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   GRAPH_CLIENT_SECRET=ta_valeur_de_secret
   GRAPH_MAILBOX=backups@ton-domaine.fr
   ```
2. Copie **`config.example.yaml`** en **`config.yaml`** et vérifie :
   - `mail_source: graph`
   - `mailbox:` = la même boîte
   - au besoin, ajuste `keywords`, `trusted_senders`, `client_aliases`.

> 🔒 Les secrets restent dans `.env`, jamais ailleurs.

---

## 5. Tester (2 minutes)

- D'abord le **rendu**, sans toucher à la boîte :
  ```
  python -m backupwatch --source demo --open
  ```
  Le tableau de bord d'exemple s'ouvre dans le navigateur.
- Puis **pour de vrai** :
  ```
  python -m backupwatch --source graph --open
  ```
  Tu dois voir tes vraies sauvegardes (succès / avertissements / échecs).

---

## 6. Lancer le serveur (mode kiosque)

Double-clique sur **`Demarrer-Serveur.bat`**.

Tu dois voir :
```
BackupWatch — tableau de bord servi sur http://localhost:8470/
Scraping automatique chaque jour à 07:00. Ctrl+C pour arrêter.
```

Laisse cette fenêtre ouverte : c'est elle qui **sert le dashboard** et **relance
le scraping à 7h** toute seule.

---

## 7. Démarrer automatiquement au boot du NUC

Pour que tout reparte seul après un redémarrage :

1. `Win + R` → tape **`shell:startup`** → Entrée (le dossier *Démarrage* s'ouvre).
2. Clic droit sur **`Demarrer-Serveur.bat`** → **Copier**.
3. Dans le dossier *Démarrage* : clic droit → **« Coller le raccourci »**.

→ À chaque ouverture de session Windows, le serveur démarre tout seul.

---

## 8. Brancher dans wee rotate

Dans la playlist de l'extension **wee rotate** (ou depuis le remote mobile →
ajouter une page), ajoute l'URL :
```
http://localhost:8470/
```
Donne-lui une durée d'affichage (ex. 30 s). Le tableau de bord prend sa place
dans la rotation et reste à jour (la page se rafraîchit toute seule).

---

## ✅ C'est fait

Chaque matin à 7h, BackupWatch relit la boîte, régénère le tableau, et l'écran
affiche l'état du jour — **sans que tu touches à rien**.

---

## Réglages optionnels

| Réglage | Où | Défaut |
|---|---|---|
| Port | `config.yaml` → `serve.port` (ou variable `BACKUPWATCH_PORT`) | `8470` |
| Heure du scraping | `config.yaml` → `serve.hour` (ou `BACKUPWATCH_HOUR`) | `7` |
| Adresse d'écoute | `config.yaml` → `serve.host` (ou `BACKUPWATCH_HOST`) | `127.0.0.1` (local) |

- État du serveur (diagnostic) : <http://localhost:8470/healthz>

---

## En cas de souci

- **`python n'est pas reconnu`** → Python n'est pas dans le PATH. Réinstalle en
  cochant « Add to PATH », ou tape `py` au lieu de `python`.
- **La fenêtre noire se ferme aussitôt** → lance la commande depuis `cmd` pour
  lire le message d'erreur.
- **« Aucun rapport aujourd'hui »** → normal si les mails de la nuit ne sont pas
  encore arrivés ; sinon vérifie `.env` / `config.yaml` (boîte, mots-clés).
- **Erreur d'identifiants** → revérifie les `GRAPH_*` dans `.env`, et que la
  permission **Mail.Read** a bien reçu le *consentement administrateur* dans Azure.
- **L'écran montre l'ancienne page** → la page se rafraîchit toute seule toutes
  les 5 min ; au pire, recharge l'onglet.

---

## Annexe — NUC sous Linux

Le serveur fonctionne pareil (`python3 -m backupwatch --serve --source graph`).
Pour le démarrage auto, crée un service systemd qui lance cette commande au boot
(voir aussi `scripts/schedule.md`). L'URL reste `http://localhost:8470/`.
