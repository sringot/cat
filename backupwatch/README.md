# 🛡️ BackupWatch

Surveillance automatique des **rapports de sauvegarde reçus par e-mail**.

BackupWatch lit une boîte mail (Microsoft 365 / Outlook), repère les e-mails de
rapport de sauvegarde de la nuit, en extrait l'état (**succès / avertissement /
échec**) quel que soit le logiciel émetteur, et génère un **tableau de bord web
local** avec les échecs remontés en haut.

> Cas d'usage : chaque matin, voir d'un coup d'œil l'état de toutes les
> sauvegardes clients, sans ouvrir 40 e-mails un par un.

---

## Ce que ça fait

1. **Récupère** les e-mails reçus dans les N dernières heures (16 h par défaut,
   ce qui couvre la nuit).
2. **Filtre** les rapports de sauvegarde (mots-clés + expéditeurs de confiance).
3. **Analyse** chaque e-mail : état, client, tâche, logiciel, volume, durée,
   cause d'échec. Le parser générique gère Veeam, Acronis, Synology, NAKIVO,
   Datto… en français et en anglais, et évite les faux positifs (« 0 erreur »).
4. **Génère** un tableau de bord HTML autonome (`output/dashboard.html`), trié
   par gravité, avec recherche et tri par colonne.

---

## Démarrage rapide (mode démo, sans boîte mail)

```bash
pip install -r requirements.txt
python -m backupwatch --source demo --open
```

Cela utilise des e-mails d'exemple (`fixtures/sample_emails.json`) et ouvre le
tableau de bord dans votre navigateur. Idéal pour voir le rendu immédiatement.

---

## Brancher votre boîte Microsoft 365

BackupWatch lit Microsoft 365 via **Microsoft Graph**, avec une authentification
applicative (« client credentials ») adaptée à une exécution automatique, sans
mot de passe d'utilisateur.

### 1. Enregistrer une application Azure AD

1. Portail Azure → **Microsoft Entra ID** → **App registrations** → *New registration*.
2. Notez l'**Application (client) ID** et le **Directory (tenant) ID**.
3. **Certificates & secrets** → *New client secret* → notez la **valeur** du secret.
4. **API permissions** → *Add a permission* → **Microsoft Graph** →
   **Application permissions** → **Mail.Read** → *Add*, puis **Grant admin consent**.

> 🔒 **Bonne pratique** : limitez l'application à la seule boîte des rapports avec
> une [Application Access Policy](https://learn.microsoft.com/graph/auth-limit-mailbox-access)
> Exchange Online. L'app ne pourra alors lire que cette boîte.

### 2. Renseigner les identifiants

```bash
cp .env.example .env
# éditez .env avec GRAPH_TENANT_ID / CLIENT_ID / CLIENT_SECRET / MAILBOX
cp config.example.yaml config.yaml
```

### 3. Lancer

```bash
python -m backupwatch --source graph --open
```

---

## Configuration

| Réglage | Où | Rôle |
|---|---|---|
| `GRAPH_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` | `.env` | Secrets Microsoft Graph |
| `GRAPH_MAILBOX` / `mailbox` | `.env` / `config.yaml` | Boîte à lire |
| `mail_source` | `config.yaml` ou `--source` | `graph` ou `demo` |
| `lookback_hours` | `config.yaml` ou `--lookback` | Fenêtre analysée (défaut 16 h) |
| `keywords` | `config.yaml` | Mots-clés des rapports de sauvegarde |
| `trusted_senders` | `config.yaml` | Expéditeurs toujours analysés |
| `output.dir` / `output.name` | `config.yaml` | Emplacement du tableau de bord |

Les secrets ne vont **que** dans `.env` (ignoré par git). `config.yaml` ne
contient aucun secret.

---

## Planifier chaque matin

Le script tourne une fois puis s'arrête : c'est le planificateur du système qui
le relance. Voir **[scripts/schedule.md](scripts/schedule.md)** pour cron, les
timers systemd et le Planificateur de tâches Windows.

> Le code de sortie vaut **2** si au moins une sauvegarde a échoué, **0** sinon —
> pratique pour brancher une alerte de supervision.

---

## Affichage permanent (mode kiosque)

Pour afficher le tableau de bord en continu sur un écran — par exemple comme une
page de la rotation **wee rotate** — utilisez le **mode serveur** :

```bash
python -m backupwatch --serve --source graph
```

Il sert alors le tableau de bord sur une **URL fixe** et **relance le scraping
tout seul chaque matin à 7h** (planificateur interne — pas besoin de cron ni du
Planificateur de tâches). La page se rafraîchit déjà d'elle-même : l'écran
montre les données du jour **sans aucune intervention**.

```
BackupWatch — tableau de bord servi sur http://localhost:8470/
Scraping automatique chaque jour à 07:00. Ctrl+C pour arrêter.
```

**Sur Windows**, double-cliquez sur **`Demarrer-Serveur.bat`** au lieu de lancer
la commande à la main.

### Brancher dans wee rotate

Collez simplement l'URL dans la playlist de l'extension :

```
http://localhost:8470/
```

(le PC du kiosque charge sa propre URL locale). Le tableau de bord prend alors sa
place dans la rotation, toujours à jour.

### Démarrer automatiquement au boot du PC

Pour que ce soit **100 % autonome**, lancez le serveur au démarrage de Windows :

1. `Win + R` → `shell:startup` → Entrée (ouvre le dossier Démarrage).
2. Clic droit sur **`Demarrer-Serveur.bat`** → **Copier**, puis **collez un
   raccourci** dans ce dossier.

Le serveur se relancera à chaque ouverture de session, l'URL ne changera jamais.

### Réglages

| Réglage | CLI | `config.yaml` | Variable d'env | Défaut |
|---|---|---|---|---|
| Adresse d'écoute | `--host` | `serve.host` | `BACKUPWATCH_HOST` | `127.0.0.1` |
| Port | `--port` | `serve.port` | `BACKUPWATCH_PORT` | `8470` |
| Heure du scraping | `--hour` | `serve.hour` | `BACKUPWATCH_HOUR` | `7` |

> `127.0.0.1` garde le tableau de bord **local au PC** (recommandé). Mettez
> `0.0.0.0` seulement si vous voulez aussi le consulter depuis une autre machine
> du réseau.

---

## Comment ça marche

```
backupwatch/
├── config.py            Chargement config (.env + config.yaml)
├── models.py            BackupStatus, RawEmail, BackupResult
├── mail/
│   ├── base.py          Interface MailSource
│   ├── graph.py         Microsoft 365 (Microsoft Graph)
│   └── demo.py          Mails d'exemple (mode démo)
├── parsing/
│   ├── base.py          Interface BackupParser + registre
│   └── generic.py       Parser générique (FR/EN, multi-logiciels)
├── report/
│   ├── dashboard.py     Génération du HTML
│   └── template.html    Gabarit du tableau de bord
├── pipeline.py          Orchestration récupérer → filtrer → parser → rapport
└── cli.py               Ligne de commande
```

## Ajouter un parser spécialisé

Le parser générique suffit pour démarrer. Pour une extraction fine d'un
logiciel précis (ex. découper un rapport Veeam multi-VM en une ligne par VM) :

1. Créez une classe héritant de `BackupParser` dans `backupwatch/parsing/`.
2. Implémentez `can_parse(email)` et `parse(email) -> list[BackupResult]`.
3. Ajoutez-en une instance à `PARSERS` dans `parsing/base.py`.

Les parsers spécialisés sont essayés avant le générique.

---

## Sécurité & confidentialité

- Le tableau de bord est **100 % local** : aucune donnée n'est envoyée à
  l'extérieur.
- Accès **en lecture seule** à la boîte (`Mail.Read`).
- Les secrets restent dans `.env` (hors du dépôt git).
- Restriction recommandée de l'app à une seule boîte (voir plus haut).

---

## Tests

```bash
pip install pytest
pytest -q
```

---

## Prochaines étapes possibles

- Parsers dédiés par logiciel (à préciser selon vos outils).
- Export Excel (`.xlsx`) en plus du tableau de bord web.
- Historique jour par jour (tendances, taux de réussite par client).
- Alerte e-mail / Teams si une sauvegarde échoue.
- Mapping explicite « expéditeur → nom de client ».
