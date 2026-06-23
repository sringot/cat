# Planifier BackupWatch chaque matin

Le script s'exécute une fois puis s'arrête : c'est le planificateur du système
qui le relance chaque matin. Choisissez la méthode selon votre OS.

## Linux — cron

```bash
crontab -e
```

Ajoutez (exécution tous les jours à 7h30) :

```cron
30 7 * * * /chemin/vers/wee-tech/scripts/run.sh >> /var/log/backupwatch.log 2>&1
```

## Linux — systemd timer

`/etc/systemd/system/backupwatch.service` :

```ini
[Unit]
Description=BackupWatch - rapport des sauvegardes

[Service]
Type=oneshot
WorkingDirectory=/chemin/vers/wee-tech
ExecStart=/chemin/vers/wee-tech/scripts/run.sh
```

`/etc/systemd/system/backupwatch.timer` :

```ini
[Unit]
Description=Lancer BackupWatch chaque matin

[Timer]
OnCalendar=*-*-* 07:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Activation :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now backupwatch.timer
```

## Windows — Planificateur de tâches

1. Ouvrez « Planificateur de tâches » → « Créer une tâche… ».
2. Onglet **Déclencheurs** : quotidien à 07:30.
3. Onglet **Actions** : démarrer un programme
   - Programme/script : `python`
   - Arguments : `-m backupwatch --source graph`
   - Commencer dans : `C:\chemin\vers\wee-tech`
4. Cochez « Exécuter même si l'utilisateur n'est pas connecté ».

> Astuce : le code de sortie est `2` si au moins une sauvegarde a échoué, `0`
> sinon. Pratique pour brancher une alerte sur votre outil de supervision.
